# 05 · Runbooks (Standard Operating Procedures)

Clear, repeatable procedures for the most common IT support tickets in a warehouse / operations site. Each runbook follows the same structure: **scope → diagnose → fix → verify with the user → document root cause**.

| Runbook | Typical ticket |
|---|---|
| [Label printer offline](printer-offline.md) | "Printer on the ship dock is offline", blank or misaligned labels |
| [RF scanner Wi-Fi](rf-scanner-wifi.md) | "Scanner says no network", keeps disconnecting |
| [No network connectivity](no-network-connectivity.md) | "No internet", APIPA address, can't reach an application |
| [Account lockout / password reset](account-lockout-password-reset.md) | "I'm locked out", "password expired", repeated lockouts |
| [New laptop deployment](new-laptop-setup.md) | New hire, hardware refresh, replacement device |

Principles used in every runbook:
- **Get the user working first** (spare device, workaround), then fix the root cause
- **One device or many?** - many devices in one area means a network problem, not a device problem
- **Verify identity** before any account change
- **Close the ticket with root cause + fix**, and escalate recurring problems
