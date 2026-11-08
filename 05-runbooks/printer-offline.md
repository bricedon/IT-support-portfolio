# Runbook: Label Printer Offline / Not Printing

| | |
|---|---|
| **Typical ticket** | "Printer on the ship dock is offline", "labels are not coming out" |
| **Priority** | P2 if a line or station is blocked · P3 if a backup printer is available |
| **Tools** | `02-network-device-checker`, `01-endpoint-health-check`, printer config label |
| **Escalate to** | Network team (switch port / VLAN), vendor (hardware failure) |

## 1. Scope the problem (1 minute)
- **One printer or many?** Many printers in the same area offline → treat it as a **network** issue, see [no-network-connectivity.md](no-network-connectivity.md).
- **One user or everyone?** If only one PC cannot print, the problem is on that PC (queue / driver / spooler), not the printer.
- Ask what changed: power outage, printer moved, new label roll, Windows update.

## 2. Check the printer itself
1. Power on? Status light? Any error light (media, ribbon, head open)?
2. Head closed and latched, labels and ribbon loaded the right way.
3. Print the **configuration label** (on many Zebra desktop models: hold FEED until the light flashes once). Read the **IP address**, subnet and gateway.

## 3. Check the network path
```powershell
ping <printer-ip>
Test-NetConnection <printer-ip> -Port 9100     # raw print port
```
Or run the checker for the whole area:
```bash
python device_checker.py check shipdock_devices.csv
```
| Result | Meaning | Action |
|---|---|---|
| Ping fails, 9100 closed | Printer not on the network | Check cable / Wi-Fi, switch port link light, IP on config label |
| Ping OK, 9100 closed | Printer reachable, print service off | Power-cycle printer, check printer network settings |
| Ping OK, 9100 open | Network is fine | Problem is the print queue on the PC/server → step 4 |
| IP on label ≠ IP in queue | Printer got a new DHCP address | Update the port in the queue **and** request a DHCP reservation |

## 4. Check the print queue (Windows)
```powershell
Get-Printer | Where-Object Name -like '*ship*' | Format-Table Name, PortName, PrinterStatus
Get-PrintJob -PrinterName '<printer name>'
Restart-Service Spooler          # clears a stuck queue (requires admin)
```
- Remove stuck jobs, confirm the port points to the correct IP.
- Print a test label.

## 5. Calibration problems (labels blank, skipping, misaligned)
- Blank labels: ribbon missing or installed inside-out (for thermal-transfer media).
- Skipping / misaligned: run media calibration (on many Zebra desktop models: hold FEED until the light flashes twice).

## 6. Close the ticket
- Test print **with the user** watching.
- Resolution note must say **root cause + fix**, e.g. *"Printer received new DHCP IP after power outage. Updated queue port, requested DHCP reservation."*
- If this printer had **3+ tickets** this month (`python tickets.py report`), open a problem ticket for a permanent fix (reservation, replacement, UPS).
