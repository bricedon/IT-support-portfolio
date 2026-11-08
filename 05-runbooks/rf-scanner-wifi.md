# Runbook: RF / Handheld Scanner Not Connecting

| | |
|---|---|
| **Typical ticket** | "My scanner says no network", "scanner keeps disconnecting" |
| **Priority** | P3 for one device (spare available) · P2 if several devices in one area |
| **Tools** | Device settings, `02-network-device-checker` (access points), spare device |
| **Escalate to** | Network team (AP / controller), device management team (profile push) |

## 1. Get the associate working first
- Hand them a **spare scanner** so the work does not stop. Fix the broken one after.

## 2. One device or many?
- **Several scanners in the same aisle/area** → likely an **access point** problem. Check APs:
  ```bash
  python device_checker.py check aps_aisle12.csv
  ```
  If an AP is DOWN: check the PoE switch port / cable and escalate to Network.
- **One scanner only** → continue below.

## 3. Check the device
1. Battery charged? Swap battery. Clean the charging contacts on the battery and cradle.
2. Wi-Fi turned on, airplane mode off.
3. Connected to the **correct SSID**? Old or wrong Wi-Fi profiles are a common cause after a password or certificate change.
4. Signal strength in that location; does it work next to the AP?
5. Date and time correct? A wrong clock breaks certificate-based Wi-Fi (802.1X).

## 4. Fix
- Forget the network and re-join, or **re-push the Wi-Fi profile** from the device management tool.
- Reboot the device (warm boot, then cold boot if needed).
- Still failing: re-enroll / re-provision the device, or send for repair and track the asset tag.

## 5. Close the ticket
- Confirm the device scans and sends data in the user's work area.
- Note the asset tag, root cause and fix. If the same AP area generates repeated tickets, report it as a Wi-Fi coverage problem.
