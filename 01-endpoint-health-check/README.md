# 01 · Endpoint Health Check (PowerShell)

**Problem:** at the start of a support call, a technician opens Task Manager, Disk Management, `ipconfig`, Services, Event Viewer... one by one. That takes time and steps get skipped.

**Solution:** one script runs every first-line check and saves a **color-coded HTML report** (PASS / WARN / FAIL / INFO), so you see immediately where to look.

## What it checks
| Category | Checks | Example of a FAIL / WARN |
|---|---|---|
| System | Model, serial, OS build, user, uptime | Uptime > 14 days → restart recommended |
| Storage | Free space on every fixed drive | < 15 % WARN, < 5 % FAIL |
| Performance | Memory %, CPU load, top 3 processes | Memory ≥ 85 % WARN |
| Network | IP, gateway, DNS, DHCP, MAC per adapter | `169.254.x.x` (APIPA) → DHCP not reachable |
| Connectivity | Ping gateway, DNS lookup, ping internet, HTTPS 443 | Gateway no reply → local network / VLAN issue |
| Maintenance | Pending reboot (Windows Update, CBS, file rename) | Reboot required |
| Services | Print Spooler, DNS Client, DHCP Client, Time, Defender, Windows Update | Spooler stopped → can't print |
| Security | Registered antivirus (Security Center), Defender real-time protection, signature age | No antivirus with real-time ON; signatures > 7 days old |
| Events | System log critical/error count in last 24 h | ≥ 25 errors, with top sources |

Every check is wrapped in `try/catch`, so one failing check never stops the report.

## Usage
```powershell
# Save the report to the Desktop and open it
powershell -ExecutionPolicy Bypass -File .\Get-EndpointHealth.ps1 -OpenReport

# Custom folder and test hosts
.\Get-EndpointHealth.ps1 -OutputFolder C:\Temp -TestHosts 1.1.1.1, www.microsoft.com
```
- Works on Windows PowerShell 5.1 and PowerShell 7
- No admin rights needed (some checks give more detail as admin)
- Read-only: the script changes nothing on the computer

## Example console output
```text
Running endpoint health check on SHIPDOCK-PC07...

[WARN] System - Uptime: 21d 4h 12m (last boot 10/18/2026 06:02) - consider a restart
[FAIL] Services - Print Spooler: Stopped - try: Start-Service Spooler
[WARN] Maintenance - Pending reboot: Reboot required: Windows Update

Overall: FAIL  (PASS 17 / WARN 2 / FAIL 1 / INFO 6)
Report saved: C:\Users\tech\Desktop\EndpointHealth_SHIPDOCK-PC07_20261108_101530.html
```

## How I would use it on the job
- First step on any "my computer is slow / can't print / no network" ticket
- Attach the HTML report to the ticket as evidence of what was checked
- Run after a new laptop build: everything should be PASS ([deployment checklist](../05-runbooks/new-laptop-setup.md))
