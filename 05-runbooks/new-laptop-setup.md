# Runbook: New Laptop / Workstation Deployment Checklist

| | |
|---|---|
| **Typical ticket** | New hire, hardware refresh, replacement for a failed device |
| **Priority** | P4 (planned) · P3 if replacing a broken device |
| **Tools** | Imaging tool (e.g. MDT / Autopilot / Intune), asset tracker, `01-endpoint-health-check` |

## Before the user arrives
- [ ] Record **asset tag, serial number, model** in the asset tracker and link it to the ticket
- [ ] Image the device with the standard build (or confirm Autopilot enrollment)
- [ ] Rename to the naming standard and join the domain / Entra ID
- [ ] Run Windows Update until no updates remain, reboot
- [ ] Confirm BitLocker is on and the recovery key is escrowed
- [ ] Confirm antivirus / EDR is running and reporting
- [ ] Install department software from the approved list
- [ ] Add required printers (check the right printer for the user's area)
- [ ] Run the health check - everything should be PASS:
  ```powershell
  .\Get-EndpointHealth.ps1 -OpenReport
  ```

## With the user
- [ ] User signs in, sets up MFA, changes the temporary password
- [ ] Email, Teams, and line-of-business applications open
- [ ] Test print, test VPN (if remote), test camera/mic for meetings
- [ ] Migrate files from the old device (if replacement), confirm nothing is missing
- [ ] Show where to get help (help desk portal / phone number)

## After
- [ ] Old device: wipe, update asset status (spare / repair / e-waste), keep chain of custody
- [ ] Close the ticket with asset tag, serial, and user sign-off
