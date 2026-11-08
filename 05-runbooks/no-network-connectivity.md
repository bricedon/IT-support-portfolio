# Runbook: No Network / No Internet on a Workstation

| | |
|---|---|
| **Typical ticket** | "No internet", "can't reach the application", "network cable unplugged" |
| **Priority** | P1 if a whole area is down · P3 for one workstation |
| **Tools** | `01-endpoint-health-check`, `ipconfig`, `ping`, `nslookup`, `Test-NetConnection` |
| **Escalate to** | Network team (switch, VLAN, DHCP scope, firewall) |

Work **bottom-up through the OSI model** - each step proves the layer below works.

## Quick start
```powershell
.\Get-EndpointHealth.ps1 -OpenReport
```
The report shows the IP, gateway, DNS and connectivity results in one page. Then use the table below.

## Step by step
| # | Check | Command | If it fails |
|---|---|---|---|
| 1 | **Physical** - link light, cable, Wi-Fi on | look at the port / adapter | Reseat or swap cable, try another wall/switch port |
| 2 | **IP address** | `ipconfig /all` | `169.254.x.x` = no DHCP → `ipconfig /release` then `ipconfig /renew`; still failing → DHCP scope / VLAN issue, escalate |
| 3 | **Gateway** | `ping <default gateway>` | Local network / VLAN / switch port problem |
| 4 | **Outside IP** | `ping 8.8.8.8` | Routing / firewall upstream (ICMP may be blocked - try step 6) |
| 5 | **DNS** | `nslookup www.microsoft.com` | `ipconfig /flushdns`; check DNS servers in `ipconfig /all` |
| 6 | **Application port** | `Test-NetConnection <server> -Port 443` | Firewall / proxy / application server down |

## Common fixes
```powershell
ipconfig /release
ipconfig /renew
ipconfig /flushdns
netsh winsock reset          # then reboot - fixes corrupted network stack
Get-NetAdapter | Restart-NetAdapter
```

## Is it just this PC?
- Neighbor's PC works on the same switch → the problem is this PC (driver, cable, settings).
- Whole area is down → stop troubleshooting the PC, raise **P1**, and notify the Network team with: area, number of users, time it started, what you already checked.

## Close the ticket
Write what layer failed and why, e.g. *"APIPA address - switch port was in the wrong VLAN after move. Network team corrected VLAN, DHCP lease received."*
