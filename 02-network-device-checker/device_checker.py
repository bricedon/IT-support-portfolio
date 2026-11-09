#!/usr/bin/env python3
"""
Network Device Checker
======================

Checks a list of network devices (label printers, RF scanners, access points,
switches, servers) and tells the technician which ones are UP, DEGRADED or DOWN,
with a troubleshooting hint for each problem.

Two modes:

  1. Inventory check - read devices from a CSV file:
       python device_checker.py check devices.csv
       python device_checker.py check devices.csv --report report.html --csv results.csv

  2. Subnet sweep - find live hosts in a range (discovery / IP conflict hunting):
       python device_checker.py sweep 192.168.1.0/24

For each device the tool:
  * resolves the hostname with DNS (if a name was given instead of an IP)
  * pings it (ICMP)
  * tests the TCP ports that matter for that device type
    (e.g. printer -> 9100 raw print, 80 web page; switch -> 22 SSH, 443 HTTPS)

Status rules:
  UP        ping replies and every expected port is open
  DEGRADED  device answers but something is wrong (a port is closed, or ICMP is
            blocked but a port is open)
  DOWN      no reply to ping and no port open
  DNS FAIL  the hostname could not be resolved

Standard library only - runs on any machine with Python 3.8+ (Windows, macOS, Linux).
Exit code is 0 when every device is UP and 1 otherwise, so it can run from
Task Scheduler / cron and alert on failure.

Author: Brice Albert Donfack
"""

from __future__ import annotations

import argparse
import csv
import html
import ipaddress
import platform
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

# Ports checked for each device type when the CSV does not list any.
DEFAULT_PORTS: Dict[str, List[int]] = {
    "printer": [9100, 80],        # 9100 = raw/JetDirect printing, 80 = printer web page
    "scanner": [80, 443],         # RF handheld / fixed scanner management
    "access_point": [80, 443],
    "switch": [22, 443],          # SSH and web management
    "server": [3389, 445],        # RDP and SMB file sharing
    "workstation": [3389, 445],
    "dns": [53],
    "web": [80, 443],
}

# Human-readable troubleshooting hints.
HINTS = {
    ("DOWN", "printer"): "Check power and cable; print the printer config page and compare the IP; confirm DHCP reservation.",
    ("DOWN", "scanner"): "Check battery / dock; confirm the scanner is joined to the right Wi-Fi SSID; reboot the device.",
    ("DOWN", "access_point"): "Check the PoE switch port and cable; look at the AP LEDs; check the controller for the AP status.",
    ("DOWN", "switch"): "Check power / uplink; console in if remote management is down; escalate to Network team.",
    ("DOWN", "*"): "No response: check power, cable / Wi-Fi, IP address, and switch port. Escalate if a whole area is down.",
    ("DEGRADED", "printer"): "Printer answers but a port is closed: check the print queue / port 9100 setting, restart the Print Spooler, power-cycle the printer.",
    ("DEGRADED", "*"): "Device answers but a service is closed: check the service, firewall rules, or a pending reboot.",
    ("DNS FAIL", "*"): "Hostname did not resolve: check the DNS record, try the IP directly, run ipconfig /flushdns.",
}


@dataclass
class Device:
    name: str
    host: str
    device_type: str = "workstation"
    location: str = ""
    ports: List[int] = field(default_factory=list)


@dataclass
class Result:
    device: Device
    ip: Optional[str] = None
    ping_ok: bool = False
    ping_ms: Optional[float] = None
    open_ports: List[int] = field(default_factory=list)
    closed_ports: List[int] = field(default_factory=list)
    status: str = "DOWN"
    hint: str = ""


# --------------------------------------------------------------------------- checks

def resolve(host: str) -> Optional[str]:
    """Return the IPv4 address for a hostname or IP, or None if DNS fails."""
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        return socket.gethostbyname(host)
    except (socket.gaierror, UnicodeError):
        return None


def ping(ip: str, timeout_s: float = 1.0) -> Optional[float]:
    """Ping once. Return the round-trip time in ms, or None if there is no reply."""
    windows = platform.system().lower() == "windows"
    if windows:
        cmd = ["ping", "-n", "1", "-w", str(int(timeout_s * 1000)), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout_s))), ip]
    start = time.perf_counter()
    try:
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   timeout=timeout_s + 2)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
    return parse_ping_output(completed.returncode, completed.stdout.decode(errors="ignore"), windows, elapsed_ms)


def parse_ping_output(returncode: int, output: str, windows: bool, fallback_ms: float) -> Optional[float]:
    """Read the real round-trip time from the ping output.

    Windows quirk: 'ping' returns exit code 0 even for "Destination host unreachable"
    (a reply from the router, not from the device). A real reply always contains "TTL=",
    so on Windows that is required too.
    """
    if returncode != 0:
        return None
    if windows and "ttl=" not in output.lower():
        return None
    match = re.search(r"(?:time|temps|zeit|tiempo)\s*[=<]\s*([\d.,]+)\s*ms", output, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(",", "."))
    return fallback_ms


def port_open(ip: str, port: int, timeout_s: float = 1.5) -> bool:
    """Return True if a TCP connection to ip:port succeeds."""
    try:
        with socket.create_connection((ip, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def classify(result: Result) -> None:
    """Set the status and the troubleshooting hint from the raw check results."""
    if result.ip is None:
        result.status = "DNS FAIL"
    elif result.ping_ok and not result.closed_ports:
        result.status = "UP"
    elif result.ping_ok or result.open_ports:
        result.status = "DEGRADED"
    else:
        result.status = "DOWN"

    if result.status != "UP":
        dtype = result.device.device_type
        result.hint = HINTS.get((result.status, dtype)) or HINTS.get((result.status, "*"), "")
        if result.status == "DEGRADED" and not result.ping_ok and result.open_ports:
            result.hint = "Ports answer but ping does not - ICMP is probably blocked by a firewall. Device is likely fine."


def check_device(device: Device, timeout_s: float = 1.5) -> Result:
    result = Result(device=device)
    result.ip = resolve(device.host)
    if result.ip:
        result.ping_ms = ping(result.ip, timeout_s)
        result.ping_ok = result.ping_ms is not None
        ports = device.ports or DEFAULT_PORTS.get(device.device_type, [])
        for port in ports:
            (result.open_ports if port_open(result.ip, port, timeout_s) else result.closed_ports).append(port)
    classify(result)
    return result


# --------------------------------------------------------------------------- input

def load_devices(csv_path: str) -> List[Device]:
    """Read devices from a CSV with columns: name, host, type, location, ports.

    'ports' is optional and uses ';' between ports, e.g. "9100;80".
    """
    devices: List[Device] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"name", "host"}
        if not reader.fieldnames or not required.issubset({f.strip().lower() for f in reader.fieldnames}):
            raise ValueError(f"CSV must have at least these columns: {', '.join(sorted(required))}")
        for line_no, raw in enumerate(reader, start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            if not row.get("name") or not row.get("host"):
                print(f"  skipping line {line_no}: missing name or host", file=sys.stderr)
                continue
            ports: List[int] = []
            for p in row.get("ports", "").replace(",", ";").split(";"):
                if p.strip().isdigit():
                    ports.append(int(p))
            devices.append(Device(
                name=row["name"],
                host=row["host"],
                device_type=(row.get("type") or "workstation").lower(),
                location=row.get("location", ""),
                ports=ports,
            ))
    return devices


# --------------------------------------------------------------------------- output

COLORS = {"UP": "\033[92m", "DEGRADED": "\033[93m", "DOWN": "\033[91m", "DNS FAIL": "\033[95m"}
RESET = "\033[0m"


def use_color() -> bool:
    if not sys.stdout.isatty():
        return False
    if platform.system().lower() == "windows":
        os_system = getattr(__import__("os"), "system")
        os_system("")  # enables ANSI colors in the Windows console
    return True


def print_table(results: List[Result]) -> None:
    color = use_color()
    header = f"{'STATUS':<9} {'DEVICE':<30} {'TYPE':<13} {'IP':<16} {'PING':<9} {'OPEN':<12} {'CLOSED':<12} LOCATION"
    print(header)
    print("-" * len(header))
    for r in results:
        status = f"{r.status:<9}"
        if color:
            status = f"{COLORS.get(r.status, '')}{status}{RESET}"
        ping_txt = f"{r.ping_ms} ms" if r.ping_ok else "-"
        print(f"{status} {r.device.name[:30]:<30} {r.device.device_type[:13]:<13} {(r.ip or '-'):<16} "
              f"{ping_txt:<9} {','.join(map(str, r.open_ports)) or '-':<12} "
              f"{','.join(map(str, r.closed_ports)) or '-':<12} {r.device.location}")
    problems = [r for r in results if r.status != "UP"]
    if problems:
        print("\nWhat to check:")
        for r in problems:
            print(f"  - {r.device.name} ({r.status}): {r.hint}")


def summary(results: List[Result]) -> Dict[str, int]:
    counts = {"UP": 0, "DEGRADED": 0, "DOWN": 0, "DNS FAIL": 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return counts


def write_csv(results: List[Result], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["checked_at", "name", "host", "ip", "type", "location", "status",
                         "ping_ms", "open_ports", "closed_ports", "hint"])
        stamp = datetime.now().isoformat(timespec="seconds")
        for r in results:
            writer.writerow([stamp, r.device.name, r.device.host, r.ip or "", r.device.device_type,
                             r.device.location, r.status, r.ping_ms if r.ping_ok else "",
                             ";".join(map(str, r.open_ports)), ";".join(map(str, r.closed_ports)), r.hint])


def write_html(results: List[Result], path: str) -> None:
    counts = summary(results)
    css_class = {"UP": "up", "DEGRADED": "deg", "DOWN": "down", "DNS FAIL": "dns"}
    rows = []
    for r in results:
        e = html.escape
        rows.append(
            f"<tr><td class='s {css_class[r.status]}'>{e(r.status)}</td><td>{e(r.device.name)}</td>"
            f"<td>{e(r.device.device_type)}</td><td>{e(r.device.location)}</td><td>{e(r.ip or '-')}</td>"
            f"<td>{e(str(r.ping_ms) + ' ms') if r.ping_ok else '-'}</td>"
            f"<td>{e(', '.join(map(str, r.open_ports)) or '-')}</td>"
            f"<td>{e(', '.join(map(str, r.closed_ports)) or '-')}</td><td>{e(r.hint)}</td></tr>"
        )
    cards = "".join(f"<div class='card {css_class[k]}'><b>{v}</b>{k}</div>" for k, v in counts.items())
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Network Device Report</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#f4f6f8;color:#1f2937}}
.cards{{display:flex;gap:12px;margin:12px 0 18px;flex-wrap:wrap}}
.card{{background:#fff;border-radius:8px;padding:10px 16px;min-width:90px;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
.card b{{display:block;font-size:22px}}
table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}}
th,td{{padding:8px 10px;border-bottom:1px solid #e5e7eb;font-size:14px;text-align:left;vertical-align:top}}
th{{background:#111827;color:#fff}} .s{{font-weight:700;text-align:center}}
.up{{background:#d1fae5;color:#047857}} .deg{{background:#fef3c7;color:#92400e}}
.down{{background:#fee2e2;color:#991b1b}} .dns{{background:#ede9fe;color:#5b21b6}}
</style></head><body>
<h1>Network Device Report</h1>
<div>Generated {datetime.now():%Y-%m-%d %H:%M:%S} &middot; {len(results)} device(s)</div>
<div class="cards">{cards}</div>
<table><tr><th>Status</th><th>Device</th><th>Type</th><th>Location</th><th>IP</th><th>Ping</th>
<th>Open ports</th><th>Closed ports</th><th>What to check</th></tr>
{''.join(rows)}
</table></body></html>"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)


# --------------------------------------------------------------------------- commands

def run_check(args: argparse.Namespace) -> int:
    devices = load_devices(args.csv_file)
    if not devices:
        print("No devices found in the CSV.")
        return 1
    print(f"Checking {len(devices)} device(s)...\n")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda d: check_device(d, args.timeout), devices))

    print_table(results)
    counts = summary(results)
    print("\nSummary: " + " | ".join(f"{k} {v}" for k, v in counts.items()))
    if args.csv:
        write_csv(results, args.csv)
        print(f"CSV saved: {args.csv}")
    if args.report:
        write_html(results, args.report)
        print(f"HTML report saved: {args.report}")
    return 0 if counts["UP"] == len(results) else 1


def run_sweep(args: argparse.Namespace) -> int:
    try:
        network = ipaddress.ip_network(args.subnet, strict=False)
    except ValueError as exc:
        print(f"Invalid subnet: {exc}")
        return 2
    hosts = [str(h) for h in network.hosts()]
    if len(hosts) > 1024:
        print("Subnet too large for a sweep (max /22 = 1022 hosts).")
        return 2
    print(f"Sweeping {len(hosts)} address(es) in {network}...")

    def probe(ip: str):
        ms = ping(ip, args.timeout)
        if ms is None:
            return None
        try:
            name = socket.gethostbyaddr(ip)[0]
        except (socket.herror, socket.gaierror, OSError):
            name = ""
        return ip, ms, name

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        live = [r for r in pool.map(probe, hosts) if r]

    print(f"\n{'IP':<16} {'PING':<10} HOSTNAME")
    for ip, ms, name in live:
        print(f"{ip:<16} {str(ms) + ' ms':<10} {name}")
    print(f"\n{len(live)} live host(s) of {len(hosts)} scanned.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check network devices and find live hosts.")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="check devices listed in a CSV file")
    check.add_argument("csv_file", help="CSV with columns: name, host, type, location, ports")
    check.add_argument("--report", help="save an HTML report to this path")
    check.add_argument("--csv", help="save results to this CSV path")
    check.add_argument("--timeout", type=float, default=1.5, help="seconds per check (default 1.5)")
    check.add_argument("--workers", type=int, default=32, help="parallel checks (default 32)")
    check.set_defaults(func=run_check)

    sweep = sub.add_parser("sweep", help="ping every address in a subnet, e.g. 192.168.1.0/24")
    sweep.add_argument("subnet")
    sweep.add_argument("--timeout", type=float, default=1.0)
    sweep.add_argument("--workers", type=int, default=64)
    sweep.set_defaults(func=run_sweep)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"File not found: {exc.filename}")
        return 2
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
