#!/usr/bin/env python3
"""
Help Desk Ticket Tracker
========================

A small command-line ticket system backed by SQLite. It shows how I work a ticket
queue: log the issue, prioritize it, track it against an SLA, document the fix,
and use the data to find recurring problems (root cause) instead of fixing the
same thing every day.

Commands
--------
  python tickets.py new --title "Printer offline" --category Printer --priority P2 --location "Ship Dock"
  python tickets.py list                    # open tickets, highest priority first, with SLA status
  python tickets.py list --all              # include resolved tickets
  python tickets.py show 12                 # one ticket with its full work log
  python tickets.py note 12 "Replaced network cable, printer back online"
  python tickets.py assign 12 bdonfack
  python tickets.py resolve 12 "Root cause: damaged patch cable. Replaced and tested a print."
  python tickets.py report                  # SLA compliance, recurring issues, workload
  python tickets.py export tickets.csv
  python tickets.py seed                    # load ~40 realistic sample tickets for a demo

SLA targets (time to resolve):  P1 = 4h   P2 = 8h   P3 = 24h   P4 = 72h

Standard library only (Python 3.8+). The database is a single file: tickets.db

Author: Brice Albert Donfack
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from typing import List, Optional

DB_PATH = os.environ.get("TICKETS_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tickets.db"))

SLA_HOURS = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}
PRIORITY_MEANING = {
    "P1": "Site / line down - many users blocked",
    "P2": "One area or critical device down",
    "P3": "Single user impacted, workaround exists",
    "P4": "Request / low impact",
}
CATEGORIES = ["Printer", "Scanner", "Network", "Account", "Hardware", "Software", "Other"]

# Link each category to the matching runbook in this portfolio.
RUNBOOKS = {
    "Printer": "05-runbooks/printer-offline.md",
    "Scanner": "05-runbooks/rf-scanner-wifi.md",
    "Network": "05-runbooks/no-network-connectivity.md",
    "Account": "05-runbooks/account-lockout-password-reset.md",
    "Hardware": "05-runbooks/new-laptop-setup.md",
}

TIME_FMT = "%Y-%m-%d %H:%M"


# --------------------------------------------------------------------------- database

def connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            category    TEXT NOT NULL,
            priority    TEXT NOT NULL,
            location    TEXT DEFAULT '',
            requester   TEXT DEFAULT '',
            assignee    TEXT DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'Open',
            created_at  TEXT NOT NULL,
            resolved_at TEXT,
            resolution  TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS notes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id  INTEGER NOT NULL REFERENCES tickets(id),
            created_at TEXT NOT NULL,
            author     TEXT NOT NULL,
            text       TEXT NOT NULL
        );
        """
    )
    return conn


def now() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def parse(ts: Optional[str]) -> Optional[datetime]:
    return datetime.strptime(ts, TIME_FMT) if ts else None


def current_user() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "tech"


def get_ticket(conn: sqlite3.Connection, ticket_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        raise SystemExit(f"Ticket #{ticket_id} not found.")
    return row


def add_note(conn, ticket_id: int, text: str, author: Optional[str] = None, at: Optional[datetime] = None) -> None:
    conn.execute(
        "INSERT INTO notes (ticket_id, created_at, author, text) VALUES (?, ?, ?, ?)",
        (ticket_id, (at or now()).strftime(TIME_FMT), author or current_user(), text),
    )


# --------------------------------------------------------------------------- SLA

def sla_status(row: sqlite3.Row, at: Optional[datetime] = None) -> str:
    """Return 'Met', 'Breached', 'At risk' (less than 25% of the time left) or 'On track'."""
    created = parse(row["created_at"])
    due = created + timedelta(hours=SLA_HOURS[row["priority"]])
    if row["status"] == "Resolved":
        return "Met" if parse(row["resolved_at"]) <= due else "Breached"
    at = at or now()
    if at > due:
        return "Breached"
    remaining = (due - at).total_seconds()
    total = SLA_HOURS[row["priority"]] * 3600
    return "At risk" if remaining < total * 0.25 else "On track"


def hours_between(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 3600, 1)


# --------------------------------------------------------------------------- commands

def cmd_new(conn, args) -> None:
    category = args.category.capitalize()
    if category not in CATEGORIES:
        raise SystemExit(f"Category must be one of: {', '.join(CATEGORIES)}")
    cur = conn.execute(
        "INSERT INTO tickets (title, category, priority, location, requester, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (args.title, category, args.priority, args.location, args.requester, now().strftime(TIME_FMT)),
    )
    ticket_id = cur.lastrowid
    add_note(conn, ticket_id, f"Ticket opened: {args.title}")
    conn.commit()
    due = now() + timedelta(hours=SLA_HOURS[args.priority])
    print(f"Created ticket #{ticket_id} [{args.priority} - {PRIORITY_MEANING[args.priority]}]")
    print(f"SLA due: {due.strftime(TIME_FMT)}")
    if category in RUNBOOKS:
        print(f"Runbook: {RUNBOOKS[category]}")


def cmd_list(conn, args) -> None:
    query = "SELECT * FROM tickets"
    if not args.all:
        query += " WHERE status != 'Resolved'"
    query += " ORDER BY CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END, priority, created_at"
    rows = conn.execute(query).fetchall()
    if not rows:
        print("No tickets.")
        return
    print(f"{'ID':>4}  {'PRI':<3}  {'STATUS':<11} {'SLA':<9} {'CATEGORY':<9} {'ASSIGNEE':<10} {'AGE':>6}  TITLE")
    print("-" * 100)
    for r in rows:
        end = parse(r["resolved_at"]) or now()
        age = f"{hours_between(parse(r['created_at']), end)}h"
        print(f"{r['id']:>4}  {r['priority']:<3}  {r['status']:<11} {sla_status(r):<9} {r['category']:<9} "
              f"{(r['assignee'] or '-'):<10} {age:>6}  {r['title']} ({r['location']})")


def cmd_show(conn, args) -> None:
    r = get_ticket(conn, args.id)
    print(f"Ticket #{r['id']}: {r['title']}")
    print(f"  Priority : {r['priority']} - {PRIORITY_MEANING[r['priority']]}")
    print(f"  Category : {r['category']}    Location: {r['location'] or '-'}    Requester: {r['requester'] or '-'}")
    print(f"  Status   : {r['status']}    Assignee: {r['assignee'] or '-'}    SLA: {sla_status(r)}")
    print(f"  Opened   : {r['created_at']}    Resolved: {r['resolved_at'] or '-'}")
    if r["resolution"]:
        print(f"  Resolution: {r['resolution']}")
    if r["category"] in RUNBOOKS:
        print(f"  Runbook  : {RUNBOOKS[r['category']]}")
    print("  Work log:")
    for n in conn.execute("SELECT * FROM notes WHERE ticket_id = ? ORDER BY id", (r["id"],)):
        print(f"    {n['created_at']}  {n['author']:<10} {n['text']}")


def cmd_note(conn, args) -> None:
    get_ticket(conn, args.id)
    add_note(conn, args.id, args.text)
    conn.commit()
    print(f"Note added to #{args.id}.")


def cmd_assign(conn, args) -> None:
    r = get_ticket(conn, args.id)
    status = "In Progress" if r["status"] == "Open" else r["status"]
    conn.execute("UPDATE tickets SET assignee = ?, status = ? WHERE id = ?", (args.tech, status, args.id))
    add_note(conn, args.id, f"Assigned to {args.tech}")
    conn.commit()
    print(f"#{args.id} assigned to {args.tech}.")


def cmd_resolve(conn, args) -> None:
    r = get_ticket(conn, args.id)
    if r["status"] == "Resolved":
        raise SystemExit(f"#{args.id} is already resolved.")
    if len(args.resolution.strip()) < 15:
        raise SystemExit("Please write a real resolution (what was wrong and what fixed it) - at least 15 characters.")
    conn.execute("UPDATE tickets SET status = 'Resolved', resolved_at = ?, resolution = ? WHERE id = ?",
                 (now().strftime(TIME_FMT), args.resolution, args.id))
    add_note(conn, args.id, f"Resolved: {args.resolution}")
    conn.commit()
    r = get_ticket(conn, args.id)
    print(f"#{args.id} resolved in {hours_between(parse(r['created_at']), parse(r['resolved_at']))}h - SLA {sla_status(r)}.")


def build_report(conn) -> List[str]:
    rows = conn.execute("SELECT * FROM tickets").fetchall()
    if not rows:
        return ["No tickets yet."]
    lines: List[str] = []
    resolved = [r for r in rows if r["status"] == "Resolved"]
    open_ = [r for r in rows if r["status"] != "Resolved"]

    lines.append("=== Help Desk Report ===")
    lines.append(f"Total tickets: {len(rows)}  |  Open: {len(open_)}  |  Resolved: {len(resolved)}")

    if resolved:
        met = sum(1 for r in resolved if sla_status(r) == "Met")
        lines.append(f"SLA compliance (resolved): {met}/{len(resolved)} = {round(100 * met / len(resolved))}%")

    breached_open = [r for r in open_ if sla_status(r) == "Breached"]
    at_risk = [r for r in open_ if sla_status(r) == "At risk"]
    lines.append(f"Open tickets breached: {len(breached_open)}  |  at risk: {len(at_risk)}")
    for r in sorted(breached_open + at_risk, key=lambda x: x["priority"]):
        lines.append(f"   ! #{r['id']} {r['priority']} {sla_status(r):<8} {r['title']} ({r['location']})")

    lines.append("")
    lines.append("Tickets and average resolution time by category:")
    for cat in CATEGORIES:
        cat_rows = [r for r in rows if r["category"] == cat]
        if not cat_rows:
            continue
        done = [r for r in cat_rows if r["status"] == "Resolved"]
        avg = (sum(hours_between(parse(r["created_at"]), parse(r["resolved_at"])) for r in done) / len(done)) if done else 0
        bar = "#" * len(cat_rows)
        lines.append(f"   {cat:<9} {len(cat_rows):>3}  avg {avg:>5.1f}h  {bar}")

    lines.append("")
    lines.append("Recurring issues (same title + location 3+ times) - candidates for root-cause fix:")
    recurring = conn.execute(
        "SELECT title, location, COUNT(*) AS n FROM tickets GROUP BY lower(title), lower(location) "
        "HAVING n >= 3 ORDER BY n DESC"
    ).fetchall()
    if recurring:
        for r in recurring:
            lines.append(f"   {r['n']}x  {r['title']} @ {r['location']}")
    else:
        lines.append("   none")

    lines.append("")
    lines.append("Open workload by technician:")
    workload = {}
    for r in open_:
        workload[r["assignee"] or "(unassigned)"] = workload.get(r["assignee"] or "(unassigned)", 0) + 1
    for tech, n in sorted(workload.items(), key=lambda kv: -kv[1]):
        lines.append(f"   {tech:<14} {n}")
    return lines


def cmd_report(conn, args) -> None:
    print("\n".join(build_report(conn)))


def cmd_export(conn, args) -> None:
    rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
    with open(args.path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(list(rows[0].keys()) + ["sla"] if rows else ["id"])
        for r in rows:
            writer.writerow(list(r) + [sla_status(r)])
    print(f"Exported {len(rows)} ticket(s) to {args.path}")


SAMPLE_ISSUES = [
    ("Label printer offline", "Printer", "P2", "Ship Dock", "Printer IP changed after power outage; set DHCP reservation and re-added to queue."),
    ("Label printer printing blank labels", "Printer", "P3", "Pack Line 4", "Ribbon installed inside-out; reinstalled ribbon and ran calibration."),
    ("Labels printing misaligned", "Printer", "P3", "Pack Line 2", "Media sensor out of calibration; ran auto-calibration and printed test label."),
    ("RF scanner not connecting to Wi-Fi", "Scanner", "P3", "Receive", "Scanner was on old SSID profile; re-provisioned Wi-Fi profile."),
    ("RF scanner will not charge", "Scanner", "P3", "Pick Mod B", "Dirty charging contacts on cradle; cleaned contacts and swapped battery."),
    ("Area has no network", "Network", "P1", "Ship Dock", "Access switch lost uplink; reseated uplink SFP with Network team."),
    ("Wi-Fi dead zone in aisle", "Network", "P2", "Aisle 12", "AP on PoE port shut down; re-enabled port and confirmed AP online."),
    ("Account locked out", "Account", "P3", "Outbound", "Phone had old password in Wi-Fi profile; updated phone and unlocked account."),
    ("Password expired", "Account", "P3", "Inbound", "Verified identity, reset password with change at next logon."),
    ("New hire needs access", "Account", "P4", "HR Office", "Created account from template and added to department groups."),
    ("Laptop will not boot", "Hardware", "P3", "Ops Office", "Failed SSD; reimaged replacement laptop and restored user data."),
    ("Monitor flickering", "Hardware", "P4", "Ops Office", "Loose DisplayPort cable; replaced cable."),
    ("Conference room video not working", "Hardware", "P2", "Training Room", "HDMI switcher on wrong input; reset switcher and tested call."),
    ("Outlook keeps asking for password", "Software", "P3", "Ops Office", "Stale cached credential; cleared Credential Manager entry and re-signed in."),
    ("Application crash on startup", "Software", "P3", "Problem Solve", "Corrupted cache; cleared app cache and reinstalled latest version."),
]


def cmd_seed(conn, args) -> None:
    if conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] and not args.force:
        raise SystemExit("Database already has tickets. Use 'seed --force' to add sample data anyway.")
    rng = random.Random(args.seed)
    techs = ["bdonfack", "alee", "rjohnson"]
    base = now() - timedelta(days=14)
    count = 0
    for i in range(args.count):
        # make the Ship Dock printer a recurring problem on purpose (root-cause story)
        issue = SAMPLE_ISSUES[0] if i % 6 == 0 else rng.choice(SAMPLE_ISSUES)
        title, cat, pri, loc, fix = issue
        if rng.random() < 0.25:   # about a quarter of the tickets arrived today
            created = now() - timedelta(minutes=rng.randint(20, 10 * 60))
        else:
            created = base + timedelta(hours=rng.randint(0, 14 * 24 - 12))
        cur = conn.execute(
            "INSERT INTO tickets (title, category, priority, location, requester, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (title, cat, pri, loc, f"user{rng.randint(100, 999)}", created.strftime(TIME_FMT)),
        )
        tid = cur.lastrowid
        add_note(conn, tid, f"Ticket opened: {title}", author="system", at=created)
        tech = rng.choice(techs)
        recent = created > now() - timedelta(hours=10)
        if recent:
            if rng.random() < 0.7:
                conn.execute("UPDATE tickets SET assignee = ?, status = 'In Progress' WHERE id = ?", (tech, tid))
                add_note(conn, tid, f"Assigned to {tech}", author="system", at=created + timedelta(minutes=10))
        else:
            sla = SLA_HOURS[pri]
            duration = timedelta(minutes=rng.randint(15, int(sla * 60 * (1.4 if rng.random() < 0.12 else 0.9))))
            resolved = min(created + duration, now())
            conn.execute(
                "UPDATE tickets SET assignee = ?, status = 'Resolved', resolved_at = ?, resolution = ? WHERE id = ?",
                (tech, resolved.strftime(TIME_FMT), fix, tid),
            )
            add_note(conn, tid, f"Resolved: {fix}", author=tech, at=resolved)
        count += 1
    conn.commit()
    print(f"Added {count} sample tickets. Try: python tickets.py report")


# --------------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Help desk ticket tracker (SQLite).")
    p.add_argument("--db", default=DB_PATH, help="database file (default: tickets.db next to this script)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("new", help="open a ticket")
    s.add_argument("--title", required=True)
    s.add_argument("--category", required=True, help="/".join(CATEGORIES))
    s.add_argument("--priority", required=True, choices=list(SLA_HOURS))
    s.add_argument("--location", default="")
    s.add_argument("--requester", default="")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("list", help="list tickets")
    s.add_argument("--all", action="store_true", help="include resolved tickets")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("show", help="show one ticket and its work log")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("note", help="add a work note")
    s.add_argument("id", type=int)
    s.add_argument("text")
    s.set_defaults(func=cmd_note)

    s = sub.add_parser("assign", help="assign to a technician")
    s.add_argument("id", type=int)
    s.add_argument("tech")
    s.set_defaults(func=cmd_assign)

    s = sub.add_parser("resolve", help="resolve with a root-cause / fix description")
    s.add_argument("id", type=int)
    s.add_argument("resolution")
    s.set_defaults(func=cmd_resolve)

    s = sub.add_parser("report", help="SLA, recurring issues and workload report")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("export", help="export all tickets to CSV")
    s.add_argument("path")
    s.set_defaults(func=cmd_export)

    s = sub.add_parser("seed", help="load realistic sample tickets for a demo")
    s.add_argument("--count", type=int, default=40)
    s.add_argument("--seed", type=int, default=7, help="random seed (same data every time)")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_seed)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    conn = connect(args.db)
    try:
        args.func(conn, args)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
