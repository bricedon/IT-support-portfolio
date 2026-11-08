# 04 · Help Desk Ticket Tracker (Python + SQLite)

**Problem:** fixing tickets one by one is not enough. A good support team tracks **priority and SLA**, documents **root cause + fix**, and uses the data to stop the same problem from coming back.

**Solution:** a small command-line ticket system backed by SQLite that does exactly that.

## Features
- Priorities with SLA targets: **P1 = 4h · P2 = 8h · P3 = 24h · P4 = 72h**
- SLA status for every ticket: *On track · At risk (< 25 % time left) · Breached · Met*
- Work log with timestamped notes and assignment history
- A resolution must explain **what was wrong and what fixed it** (short "fixed" notes are refused)
- Each category links to its runbook in [05-runbooks](../05-runbooks)
- **Report:** SLA compliance, breached / at-risk tickets, average resolution time per category, **recurring issues** (same problem at the same place 3+ times → root-cause candidate), workload per technician
- CSV export, and a `seed` command that loads 40 realistic sample tickets for a demo

## Usage
```bash
python tickets.py seed                     # sample data
python tickets.py list                     # open queue, highest priority first
python tickets.py new --title "Label printer offline" --category Printer --priority P2 --location "Ship Dock"
python tickets.py assign 41 bdonfack
python tickets.py note 41 "Config label shows new IP 10.20.5.77 - DHCP lease changed"
python tickets.py resolve 41 "Printer got new DHCP IP after outage. Updated queue port, requested reservation."
python tickets.py show 41
python tickets.py report
python tickets.py export tickets.csv
```

## Example report
```text
=== Help Desk Report ===
Total tickets: 40  |  Open: 12  |  Resolved: 28
SLA compliance (resolved): 27/28 = 96%
Open tickets breached: 3  |  at risk: 1
   ! #33 P1 Breached Area has no network (Ship Dock)
   ! #37 P2 Breached Label printer offline (Ship Dock)
   ! #19 P2 At risk  Label printer offline (Ship Dock)

Tickets and average resolution time by category:
   Printer    15  avg   7.8h  ###############
   Scanner     5  avg  13.1h  #####
   ...

Recurring issues (same title + location 3+ times) - candidates for root-cause fix:
   8x  Label printer offline @ Ship Dock
   ...
```
The report shows the **Ship Dock printer** failing 8 times: instead of re-fixing it every day, the next step is a permanent fix (DHCP reservation, UPS, or replacement).

## Tests
```bash
python -m unittest -v      # 6 tests: full ticket lifecycle, SLA rules, validation, report, export
```
Standard library only - Python 3.8+.
