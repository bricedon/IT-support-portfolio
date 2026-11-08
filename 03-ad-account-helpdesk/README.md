# 03 · AD Account Help Desk Tool (PowerShell)

**Problem:** "I'm locked out" and "my password expired" are among the most common help desk tickets. Done by hand, technicians sometimes skip identity verification, forget to force a password change, or don't document what they did. And when an account **keeps** locking, unlocking it again does not fix anything.

**Solution:** a menu-driven tool that handles these tickets the same safe way every time.

| Feature | What it does |
|---|---|
| **Look up user** | Enabled, locked, bad password count, password age / expiry, last logon, groups - plus a plain-English **diagnosis** |
| **Unlock** | Requires a ticket number, reminds to verify identity, asks for confirmation, writes to the audit log |
| **Reset password** | Generates a strong 14-character temporary password (no look-alike characters), forces change at next logon, unlocks the account. **The password is never written to a log.** |
| **Lockout source** | Reads event **4740** on the PDC Emulator to find which device keeps locking the account (phone with old Wi-Fi password, saved credential, mapped drive...) |
| **Audit log** | CSV of every action: time, technician, computer, action, user, ticket, result |
| **Safety rules** | Refuses to unlock or reset a **disabled** account (could be a terminated employee) and says to escalate |

## Usage
```powershell
# Interactive menu with sample users (no domain controller needed)
powershell -ExecutionPolicy Bypass -File .\ADHelpdesk.ps1 -DemoMode

# Real Active Directory (requires RSAT AD module + delegated help desk rights)
.\ADHelpdesk.ps1
.\ADHelpdesk.ps1 -Action Lookup        -User jsmith
.\ADHelpdesk.ps1 -Action Unlock        -User jsmith -Ticket INC-10452
.\ADHelpdesk.ps1 -Action Reset         -User jsmith -Ticket INC-10453
.\ADHelpdesk.ps1 -Action LockoutSource -User jsmith
```

Demo users: `jsmith` (locked out by his phone), `mgarcia` (password expired), `tnguyen` (disabled), `kpatel` (password expires soon).

## Example
```text
  John Smith  (jsmith)
  Ship Dock Associate - Outbound
  Enabled:                  True
  Locked out:               True
  Bad password count:       5
  Password expires:         2027-01-06 14:20
  Groups:                   Outbound-Users, Printers-ShipDock, VPN-Users

  Diagnosis:
   - LOCKED OUT after 5 bad attempt(s). Verify identity, then unlock. If it repeats, run 'Lockout source'.

  Lockout events for jsmith (last 24h):
TimeCreated         CallerComputer
-----------         --------------
11/08/2026 14:13:24 MOBILE-JSMITH-IPHONE
11/08/2026 13:28:24 MOBILE-JSMITH-IPHONE
11/08/2026 11:20:24 SHIPDOCK-PC07

  Most frequent source: MOBILE-JSMITH-IPHONE (2 lockout(s))
  Likely cause: a phone still using the OLD password (Wi-Fi / email profile).
```

## Cmdlets used in live mode
`Get-ADUser`, `Unlock-ADAccount`, `Set-ADAccountPassword -Reset`, `Set-ADUser -ChangePasswordAtLogon`, `Get-ADDomain` (PDC Emulator), `Get-WinEvent` (Security log, event ID 4740).

Procedure: [account-lockout-password-reset.md](../05-runbooks/account-lockout-password-reset.md)
