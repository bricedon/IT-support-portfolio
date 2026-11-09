# 02 · Network Device Checker (Python)

**Problem:** in a warehouse, one offline label printer, RF scanner dock or Wi-Fi access point can stop a whole station. Checking devices one by one with `ping` is slow, and `ping` alone does not tell you if the *service* (for example the printer's port 9100) is working.

**Solution:** keep the devices in a simple CSV inventory. The tool checks every device in parallel (DNS → ping → TCP ports for that device type), labels each one **UP / DEGRADED / DOWN / DNS FAIL**, and prints **what to check next**.

## Usage
```bash
# Check an inventory (console table + optional HTML and CSV)
python device_checker.py check devices.sample.csv
python device_checker.py check devices.sample.csv --report report.html --csv results.csv

# Find live hosts in a subnet (discovery, IP conflict hunting)
python device_checker.py sweep 192.168.1.0/24
```
Exit code is `0` when all devices are UP and `1` otherwise, so it can run from Task Scheduler and alert on failure.

## Inventory format
```csv
name,host,type,location,ports
Zebra Printer - Ship Dock 01,10.20.5.21,printer,Ship Dock,9100;80
Wi-Fi AP - Aisle 12,10.20.8.60,access_point,Aisle 12,
```
`ports` is optional. If empty, the default ports for the type are used:

| Type | Default ports | Why |
|---|---|---|
| printer | 9100, 80 | raw / JetDirect printing, printer web page |
| scanner, access_point, web | 80, 443 | management / web |
| switch | 22, 443 | SSH and HTTPS management |
| server, workstation | 3389, 445 | RDP and SMB |
| dns | 53 | DNS |

## How the status is decided
| Ping | Ports | Status | Meaning |
|---|---|---|---|
| ✅ | all open | **UP** | healthy |
| ✅ | some closed | **DEGRADED** | device is on the network but a service is down |
| ❌ | some open | **DEGRADED** | ICMP blocked by a firewall, device is probably fine |
| ❌ | none open | **DOWN** | power / cable / Wi-Fi / IP problem |
| – | – | **DNS FAIL** | hostname does not resolve |

## Example output
```text
STATUS    DEVICE                         TYPE          IP               PING      OPEN         CLOSED       LOCATION
--------------------------------------------------------------------------------------------------------------------
UP        Google Public DNS              dns           8.8.8.8          14.2 ms   53           -            Internet
DOWN      Zebra Printer - Ship Dock 01   printer       192.0.2.21       -         -            9100,80      Ship Dock
DEGRADED  Zebra Printer - Pack 04        printer       192.0.2.22       3.1 ms    80           9100         Pack Line 4
DOWN      Wi-Fi AP - Aisle 12            access_point  192.0.2.60       -         -            80,443       Aisle 12
DNS FAIL  Old print server               server        -                -         -            -            Server Room

What to check:
  - Zebra Printer - Ship Dock 01 (DOWN): Check power and cable; print the printer config page and compare the IP; confirm DHCP reservation.
  - Zebra Printer - Pack 04 (DEGRADED): Printer answers but a port is closed: check the print queue / port 9100 setting, restart the Print Spooler, power-cycle the printer.
  - Wi-Fi AP - Aisle 12 (DOWN): Check the PoE switch port and cable; look at the AP LEDs; check the controller for the AP status.
  - Old print server (DNS FAIL): Hostname did not resolve: check the DNS record, try the IP directly, run ipconfig /flushdns.

Summary: UP 3 | DEGRADED 2 | DOWN 3 | DNS FAIL 1
```
*(The sample inventory uses `192.0.2.x`, an address range reserved for documentation, so those devices show as DOWN on purpose.)*

## Tests
```bash
python -m unittest -v      # 18 tests: status rules, ping parsing (incl. Windows "unreachable" quirk), CSV parsing, real TCP port test, HTML escaping
```

Standard library only - Python 3.8+ on Windows, macOS or Linux.
