# Runbook: Account Locked Out / Password Reset

| | |
|---|---|
| **Typical ticket** | "I'm locked out", "my password expired", "it keeps locking me" |
| **Priority** | P3 (single user) · P2 if a manager / critical role is blocked |
| **Tools** | `03-ad-account-helpdesk` (ADHelpdesk.ps1), Active Directory Users and Computers |
| **Escalate to** | Security team if lockouts look like an attack (many accounts, unknown sources) |

## 1. Verify identity - ALWAYS first
Never unlock or reset based only on a name. Verify with the approved method (badge, employee ID, manager confirmation, callback). This is the most important step: social engineering often targets the help desk.

## 2. Diagnose
```powershell
.\ADHelpdesk.ps1 -Action Lookup -User <logon name>
```
| What the tool shows | Action |
|---|---|
| Locked out | Unlock (step 3) |
| Password expired | Reset (step 4) |
| Disabled | **Do not enable.** Check with manager / HR - disabled can mean the person left |
| Healthy, bad attempts > 0 | Caps Lock, keyboard layout, old password - coach the user |

## 3. Unlock
```powershell
.\ADHelpdesk.ps1 -Action Unlock -User <logon name> -Ticket <ticket #>
```

## 4. Reset password
```powershell
.\ADHelpdesk.ps1 -Action Reset -User <logon name> -Ticket <ticket #>
```
- A strong temporary password is generated and the user **must change it at next logon**.
- Give the temporary password verbally or through an approved channel. Never by email or chat.

## 5. Account keeps locking? Find the source
```powershell
.\ADHelpdesk.ps1 -Action LockoutSource -User <logon name>
```
Reads event **4740** on the PDC Emulator and shows which device caused the lockouts. Common causes:
- Phone still using the old password for Wi-Fi or email
- Saved credential in Windows Credential Manager
- Mapped drive or scheduled task running with old credentials
- Still logged in on another computer

## 6. Close the ticket
Every action is written to `helpdesk_audit_log.csv` (who, when, what, ticket number; passwords are never logged). Resolution example: *"Identity verified by badge. Lockouts from user's iPhone (old Wi-Fi password). User updated phone, account unlocked, no new lockouts after 30 min."*
