<div align="center">

# 🛠️ IT Support Portfolio

**Hands-on tools and runbooks for the work an IT Support Engineer does every day:**
**troubleshooting workstations, networks, printers and scanners, managing user accounts, and working a ticket queue.**

![PowerShell](https://img.shields.io/badge/PowerShell-5391FE?style=flat-square&logo=powershell&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.8+-3776AB?style=flat-square&logo=python&logoColor=white)
![Windows](https://img.shields.io/badge/Windows-0078D6?style=flat-square&logo=windows&logoColor=white)
![Active Directory](https://img.shields.io/badge/Active_Directory-0078D4?style=flat-square&logo=microsoft&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white)
![Tests](https://img.shields.io/badge/unit_tests-24_passing-2EA44F?style=flat-square)

</div>

---

## 📂 Projects

| # | Project | What it solves | Tech |
|---|---|---|---|
| 01 | [**Endpoint Health Check**](01-endpoint-health-check) | One command gives a color-coded report of a Windows PC: disk, memory, network, DNS, gateway, pending reboot, services, Defender, event log errors | PowerShell, CIM/WMI |
| 02 | [**Network Device Checker**](02-network-device-checker) | Checks label printers, scanners, access points and switches from a CSV inventory (ping + DNS + TCP ports), with a troubleshooting hint for each failure; subnet sweep mode | Python, sockets |
| 03 | [**AD Account Help Desk Tool**](03-ad-account-helpdesk) | Account lookup with diagnosis, unlock, password reset, and **lockout source** tracing (event 4740) - with ticket numbers and an audit log | PowerShell, Active Directory |
| 04 | [**Ticket Tracker**](04-ticket-tracker) | Command-line ticket queue with priorities, **SLA tracking**, work notes, and a report that finds **recurring issues** for root-cause fixes | Python, SQLite |
| 05 | [**Runbooks**](05-runbooks) | Step-by-step procedures: printer offline, RF scanner Wi-Fi, no network, account lockout, new laptop deployment | Markdown / SOPs |

The projects work together: a ticket in the tracker links to its runbook, and the runbooks use the tools for diagnosis.

---

## 🎯 Skills demonstrated

| IT Support skill | Where |
|---|---|
| Windows troubleshooting & diagnostics | 01, 05 |
| TCP/IP, DHCP, DNS, OSI-model troubleshooting | 01, 02, 05 |
| Printer, scanner and Wi-Fi device support | 02, 05 |
| Active Directory: lockouts, password resets, identity verification | 03, 05 |
| Ticketing, prioritization, SLA management | 04 |
| Root cause analysis (recurring issue detection) | 04, 05 |
| Scripting & automation (PowerShell, Python) | 01–04 |
| Documentation / SOP writing | 05, every README |
| Security habits: audit logging, no passwords in logs, least surprise | 03 |

---

## ⚡ Quick start

```powershell
git clone https://github.com/bricedon/it-support-portfolio
cd it-support-portfolio

# 01 - health report of this PC
powershell -ExecutionPolicy Bypass -File .\01-endpoint-health-check\Get-EndpointHealth.ps1 -OpenReport

# 02 - check devices from the sample inventory
python .\02-network-device-checker\device_checker.py check .\02-network-device-checker\devices.sample.csv --report report.html

# 03 - AD help desk tool with sample users (no domain needed)
powershell -ExecutionPolicy Bypass -File .\03-ad-account-helpdesk\ADHelpdesk.ps1 -DemoMode

# 04 - ticket tracker with sample data
python .\04-ticket-tracker\tickets.py seed
python .\04-ticket-tracker\tickets.py report
```

No installs needed: PowerShell 5.1 (built into Windows) and Python 3.8+ standard library only.

Run the tests:
```bash
cd 02-network-device-checker && python -m unittest -v
cd ../04-ticket-tracker && python -m unittest -v
```

---

<div align="center">

Built by **Brice Albert Donfack** · CompTIA CySA+, PenTest+, Security+, Network+ · [GitHub profile](https://github.com/bricedon)

</div>
