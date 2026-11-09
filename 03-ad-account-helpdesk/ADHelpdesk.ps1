<#
.SYNOPSIS
    Help desk tool for the most common Active Directory tickets: account lockouts and password resets.

.DESCRIPTION
    "I'm locked out" and "I forgot my password" are among the most frequent tickets a help desk
    receives. This tool handles them in a consistent, auditable way:

      1. Look up a user  - enabled?, locked?, bad password count, password age / expiry,
                           last logon, groups - with a plain-English diagnosis
      2. Unlock account  - requires a ticket number, asks for confirmation, writes an audit log
      3. Reset password  - generates a strong temporary password, forces change at next logon,
                           unlocks the account, writes an audit log (the password is NEVER logged)
      4. Lockout source  - reads event 4740 on the PDC Emulator to find which computer keeps
                           locking the account (old phone Wi-Fi profile, mapped drive, saved credential...)
      5. Audit log       - shows the last actions taken with this tool

    -DemoMode uses built-in sample users, so the tool can be shown without a domain controller.

.PARAMETER DemoMode
    Use sample users instead of Active Directory.

.PARAMETER Action
    Run one action without the menu: Lookup, Unlock, Reset, LockoutSource, AuditLog.

.PARAMETER User
    The sAMAccountName (logon name) for -Action.

.PARAMETER Ticket
    Ticket number, required for Unlock and Reset.

.PARAMETER Force
    Skip the "Are you sure?" prompt (for use with -Action).

.EXAMPLE
    .\ADHelpdesk.ps1 -DemoMode
    Opens the interactive menu with sample users.

.EXAMPLE
    .\ADHelpdesk.ps1 -Action Lookup -User jsmith
    Shows the account status of jsmith from Active Directory.

.EXAMPLE
    .\ADHelpdesk.ps1 -Action Unlock -User jsmith -Ticket INC-10452

.NOTES
    Author  : Brice Albert Donfack
    Requires: RSAT Active Directory module (Get-ADUser) and help desk delegated rights,
              except in -DemoMode. Reading event 4740 requires rights on the domain controller.
#>
[CmdletBinding()]
param(
    [switch]$DemoMode,
    [ValidateSet('Lookup', 'Unlock', 'Reset', 'LockoutSource', 'AuditLog')]
    [string]$Action,
    [string]$User,
    [string]$Ticket,
    [switch]$Force,
    [string]$AuditLogPath
)

$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 does not fill $PSScriptRoot inside param() defaults, so set the default here.
if (-not $AuditLogPath) {
    $scriptFolder = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
    $AuditLogPath = Join-Path $scriptFolder 'helpdesk_audit_log.csv'
}
$MaxPasswordAgeDays = 90   # used in demo mode; in AD the real policy value is used

# ============================================================== demo data
$script:DemoUsers = @{
    'jsmith' = [pscustomobject]@{
        SamAccountName = 'jsmith'; Name = 'John Smith'; Title = 'Ship Dock Associate'; Department = 'Outbound'
        Enabled = $true; LockedOut = $true; BadLogonCount = 5
        LastBadPasswordAttempt = (Get-Date).AddMinutes(-7); PasswordLastSet = (Get-Date).AddDays(-31)
        PasswordNeverExpires = $false; PasswordExpired = $false; LastLogonDate = (Get-Date).AddDays(-1)
        PasswordExpiryDate = (Get-Date).AddDays(59); MemberOf = @('Outbound-Users', 'Printers-ShipDock', 'VPN-Users')
    }
    'mgarcia' = [pscustomobject]@{
        SamAccountName = 'mgarcia'; Name = 'Maria Garcia'; Title = 'Process Assistant'; Department = 'Inbound'
        Enabled = $true; LockedOut = $false; BadLogonCount = 0
        LastBadPasswordAttempt = $null; PasswordLastSet = (Get-Date).AddDays(-92)
        PasswordNeverExpires = $false; PasswordExpired = $true; LastLogonDate = (Get-Date).AddDays(-3)
        PasswordExpiryDate = (Get-Date).AddDays(-2); MemberOf = @('Inbound-Users', 'Leads')
    }
    'tnguyen' = [pscustomobject]@{
        SamAccountName = 'tnguyen'; Name = 'Tam Nguyen'; Title = 'Seasonal Associate'; Department = 'Pack'
        Enabled = $false; LockedOut = $false; BadLogonCount = 0
        LastBadPasswordAttempt = $null; PasswordLastSet = (Get-Date).AddDays(-120)
        PasswordNeverExpires = $false; PasswordExpired = $true; LastLogonDate = (Get-Date).AddDays(-75)
        PasswordExpiryDate = (Get-Date).AddDays(-30); MemberOf = @('Pack-Users')
    }
    'kpatel' = [pscustomobject]@{
        SamAccountName = 'kpatel'; Name = 'Kiran Patel'; Title = 'Area Manager'; Department = 'Operations'
        Enabled = $true; LockedOut = $false; BadLogonCount = 1
        LastBadPasswordAttempt = (Get-Date).AddHours(-5); PasswordLastSet = (Get-Date).AddDays(-84)
        PasswordNeverExpires = $false; PasswordExpired = $false; LastLogonDate = (Get-Date).AddHours(-1)
        PasswordExpiryDate = (Get-Date).AddDays(6); MemberOf = @('Managers', 'Operations-Users', 'VPN-Users')
    }
}

$script:DemoLockoutEvents = @{
    'jsmith' = @(
        [pscustomobject]@{ TimeCreated = (Get-Date).AddMinutes(-7);  User = 'jsmith'; CallerComputer = 'MOBILE-JSMITH-IPHONE' }
        [pscustomobject]@{ TimeCreated = (Get-Date).AddMinutes(-52); User = 'jsmith'; CallerComputer = 'MOBILE-JSMITH-IPHONE' }
        [pscustomobject]@{ TimeCreated = (Get-Date).AddHours(-3);    User = 'jsmith'; CallerComputer = 'SHIPDOCK-PC07' }
    )
}

# ============================================================== backend (AD or demo)
function Assert-ADModule {
    if ($DemoMode) { return }
    if (-not (Get-Module -ListAvailable -Name ActiveDirectory)) {
        throw 'The ActiveDirectory module is not installed. Install RSAT, or run with -DemoMode.'
    }
    Import-Module ActiveDirectory -Verbose:$false
}

function Get-HdUser {
    param([Parameter(Mandatory)][string]$SamAccountName)
    if ($DemoMode) {
        $u = $script:DemoUsers[$SamAccountName.ToLower()]
        if (-not $u) { throw "User '$SamAccountName' not found." }
        return $u
    }
    $props = 'DisplayName', 'Title', 'Department', 'Enabled', 'LockedOut', 'BadLogonCount', 'LastBadPasswordAttempt',
             'PasswordLastSet', 'PasswordNeverExpires', 'PasswordExpired', 'LastLogonDate', 'MemberOf',
             'msDS-UserPasswordExpiryTimeComputed'
    try { $u = Get-ADUser -Identity $SamAccountName -Properties $props }
    catch { throw "User '$SamAccountName' not found in Active Directory." }

    $expiry = $null
    $raw = $u.'msDS-UserPasswordExpiryTimeComputed'
    if ($raw -and $raw -ne 0 -and $raw -ne 9223372036854775807) { $expiry = [datetime]::FromFileTime($raw) }

    [pscustomobject]@{
        SamAccountName = $u.SamAccountName; Name = $u.DisplayName; Title = $u.Title; Department = $u.Department
        Enabled = $u.Enabled; LockedOut = $u.LockedOut; BadLogonCount = $u.BadLogonCount
        LastBadPasswordAttempt = $u.LastBadPasswordAttempt; PasswordLastSet = $u.PasswordLastSet
        PasswordNeverExpires = $u.PasswordNeverExpires; PasswordExpired = $u.PasswordExpired
        LastLogonDate = $u.LastLogonDate; PasswordExpiryDate = $expiry
        MemberOf = @($u.MemberOf | ForEach-Object { ($_ -split ',')[0] -replace '^CN=' })
    }
}

function Invoke-HdUnlock {
    param([string]$SamAccountName)
    if ($DemoMode) { $script:DemoUsers[$SamAccountName.ToLower()].LockedOut = $false; $script:DemoUsers[$SamAccountName.ToLower()].BadLogonCount = 0; return }
    Unlock-ADAccount -Identity $SamAccountName
}

function Invoke-HdPasswordReset {
    param([string]$SamAccountName, [securestring]$NewPassword)
    if ($DemoMode) {
        $u = $script:DemoUsers[$SamAccountName.ToLower()]
        $u.PasswordLastSet = Get-Date; $u.PasswordExpired = $false; $u.LockedOut = $false; $u.BadLogonCount = 0
        $u.PasswordExpiryDate = (Get-Date).AddDays($MaxPasswordAgeDays)
        return
    }
    Set-ADAccountPassword -Identity $SamAccountName -Reset -NewPassword $NewPassword
    Set-ADUser -Identity $SamAccountName -ChangePasswordAtLogon $true
    Unlock-ADAccount -Identity $SamAccountName
}

function Get-HdLockoutEvent {
    param([string]$SamAccountName, [int]$Hours = 24)
    if ($DemoMode) { return @($script:DemoLockoutEvents[$SamAccountName.ToLower()]) | Where-Object { $_ } }

    $pdc = (Get-ADDomain).PDCEmulator
    $filter = @{ LogName = 'Security'; Id = 4740; StartTime = (Get-Date).AddHours(-$Hours) }
    $events = Get-WinEvent -ComputerName $pdc -FilterHashtable $filter -ErrorAction SilentlyContinue
    foreach ($e in $events) {
        $xml = [xml]$e.ToXml()
        $data = @{}
        foreach ($d in $xml.Event.EventData.Data) { $data[$d.Name] = $d.'#text' }
        if ($data['TargetUserName'] -eq $SamAccountName) {
            [pscustomobject]@{ TimeCreated = $e.TimeCreated; User = $data['TargetUserName']; CallerComputer = $data['TargetDomainName'] }
        }
    }
}

# ============================================================== helpers
function New-TempPassword {
    # 14 characters, at least one upper, lower, digit and symbol; no look-alike characters (O/0, l/1/I).
    $upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ'; $lower = 'abcdefghijkmnopqrstuvwxyz'
    $digit = '23456789';                $symbol = '!@#$%*?-+'
    $all = $upper + $lower + $digit + $symbol
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $pick = {
        param($set)
        $bytes = New-Object byte[] 4
        $rng.GetBytes($bytes)
        $set[[BitConverter]::ToUInt32($bytes, 0) % $set.Length]
    }
    $chars = @((& $pick $upper), (& $pick $lower), (& $pick $digit), (& $pick $symbol))
    while ($chars.Count -lt 14) { $chars += (& $pick $all) }
    # shuffle (Fisher-Yates) so the required characters are not always first
    for ($i = $chars.Count - 1; $i -gt 0; $i--) {
        $bytes = New-Object byte[] 4; $rng.GetBytes($bytes)
        $j = [BitConverter]::ToUInt32($bytes, 0) % ($i + 1)
        $tmp = $chars[$i]; $chars[$i] = $chars[$j]; $chars[$j] = $tmp
    }
    $rng.Dispose()
    -join $chars
}

function Write-AuditLog {
    param([string]$ActionName, [string]$Target, [string]$TicketNumber, [string]$Result)
    $entry = [pscustomobject]@{
        Timestamp  = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        Technician = [Environment]::UserName
        Computer   = [Environment]::MachineName
        Action     = $ActionName
        TargetUser = $Target
        Ticket     = $TicketNumber
        Result     = $Result
        Mode       = $(if ($DemoMode) { 'DEMO' } else { 'LIVE' })
    }
    $entry | Export-Csv -Path $AuditLogPath -Append -NoTypeInformation -Encoding UTF8
}

function Get-Diagnosis {
    param($u)
    $notes = New-Object System.Collections.Generic.List[string]
    if (-not $u.Enabled) { $notes.Add('DISABLED: account is disabled - check with HR / manager before enabling (do not enable on a password ticket).') }
    if ($u.LockedOut) { $notes.Add("LOCKED OUT after $($u.BadLogonCount) bad attempt(s). Verify identity, then unlock. If it repeats, run 'Lockout source'.") }
    if ($u.PasswordExpired) { $notes.Add('PASSWORD EXPIRED: user must reset. Verify identity, then use Reset password.') }
    elseif ($u.PasswordExpiryDate -and -not $u.PasswordNeverExpires) {
        $days = [math]::Floor(($u.PasswordExpiryDate - (Get-Date)).TotalDays)
        if ($days -le 7) { $notes.Add("Password expires in $days day(s) - remind the user to change it (Ctrl+Alt+Del > Change a password).") }
    }
    if ($u.Enabled -and -not $u.LockedOut -and $u.BadLogonCount -gt 0 -and -not $u.PasswordExpired) {
        $notes.Add("$($u.BadLogonCount) recent bad attempt(s) but not locked - user may be typing the old password or Caps Lock is on.")
    }
    if ($u.LastLogonDate -and ((Get-Date) - $u.LastLogonDate).TotalDays -gt 60) { $notes.Add('No logon in 60+ days - account may be stale.') }
    if ($notes.Count -eq 0) { $notes.Add('OK: account is healthy. Problem is likely elsewhere (keyboard layout, workstation, network, application).') }
    $notes
}

function Show-User {
    param([string]$SamAccountName)
    $u = Get-HdUser $SamAccountName
    $fmt = { param($d) if ($d) { ([datetime]$d).ToString('yyyy-MM-dd HH:mm') } else { '-' } }
    Write-Host ''
    Write-Host "  $($u.Name)  ($($u.SamAccountName))" -ForegroundColor Cyan
    Write-Host "  $($u.Title) - $($u.Department)"
    Write-Host ('  {0,-26}{1}' -f 'Enabled:', $u.Enabled)
    Write-Host ('  {0,-26}{1}' -f 'Locked out:', $u.LockedOut) -ForegroundColor $(if ($u.LockedOut) { 'Red' } else { 'Gray' })
    Write-Host ('  {0,-26}{1}' -f 'Bad password count:', $u.BadLogonCount)
    Write-Host ('  {0,-26}{1}' -f 'Last bad password:', (& $fmt $u.LastBadPasswordAttempt))
    Write-Host ('  {0,-26}{1}' -f 'Password last set:', (& $fmt $u.PasswordLastSet))
    Write-Host ('  {0,-26}{1}' -f 'Password expires:', $(if ($u.PasswordNeverExpires) { 'Never' } else { & $fmt $u.PasswordExpiryDate }))
    Write-Host ('  {0,-26}{1}' -f 'Last logon:', (& $fmt $u.LastLogonDate))
    Write-Host ('  {0,-26}{1}' -f 'Groups:', ($u.MemberOf -join ', '))
    Write-Host "`n  Diagnosis:" -ForegroundColor Yellow
    foreach ($n in Get-Diagnosis $u) { Write-Host "   - $n" }
    Write-Host ''
}

function Confirm-Step {
    param([string]$Message)
    if ($Force) { return $true }
    (Read-Host "$Message (Y/N)") -match '^(y|yes)$'
}

function Get-TicketNumber {
    if ($Ticket) { return $Ticket }
    do { $t = Read-Host 'Ticket number (required)' } while (-not $t.Trim())
    $t.Trim()
}

# ============================================================== actions
function Start-Unlock {
    param([string]$SamAccountName)
    $u = Get-HdUser $SamAccountName
    if (-not $u.LockedOut) { Write-Host "  $SamAccountName is not locked out - nothing to do." -ForegroundColor Green; return }
    if (-not $u.Enabled) { Write-Host '  Account is DISABLED. Unlocking will not help - escalate to the account owner / HR.' -ForegroundColor Red; return }
    $t = Get-TicketNumber
    Write-Host '  Reminder: verify the user identity (badge / employee ID / manager) before unlocking.' -ForegroundColor Yellow
    if (-not (Confirm-Step "  Unlock $SamAccountName for ticket $t?")) { Write-Host '  Cancelled.'; return }
    try {
        Invoke-HdUnlock $SamAccountName
        Write-AuditLog 'Unlock' $SamAccountName $t 'Success'
        Write-Host "  Account $SamAccountName unlocked. Logged to audit file." -ForegroundColor Green
    }
    catch {
        Write-AuditLog 'Unlock' $SamAccountName $t "Failed: $($_.Exception.Message)"
        throw
    }
}

function Start-PasswordReset {
    param([string]$SamAccountName)
    $u = Get-HdUser $SamAccountName
    if (-not $u.Enabled) { Write-Host '  Account is DISABLED. Do not reset - escalate to the account owner / HR.' -ForegroundColor Red; return }
    $t = Get-TicketNumber
    Write-Host '  Reminder: verify the user identity before resetting a password.' -ForegroundColor Yellow
    if (-not (Confirm-Step "  Reset the password for $SamAccountName (ticket $t)?")) { Write-Host '  Cancelled.'; return }

    $plain = New-TempPassword
    # The temporary password is generated in memory and shown once to the technician, so a plain-text conversion is expected here.
    $secure = ConvertTo-SecureString $plain -AsPlainText -Force
    try {
        Invoke-HdPasswordReset $SamAccountName $secure
        Write-AuditLog 'PasswordReset' $SamAccountName $t 'Success (must change at next logon)'
    }
    catch {
        Write-AuditLog 'PasswordReset' $SamAccountName $t "Failed: $($_.Exception.Message)"
        throw
    }
    Write-Host "  Temporary password: $plain" -ForegroundColor Green
    Write-Host '  Give it to the user verbally or through an approved channel - never by email/chat.'
    Write-Host '  The user must change it at next logon. (The password is not written to any log.)'
    $plain = $null
}

function Show-LockoutSource {
    param([string]$SamAccountName)
    $null = Get-HdUser $SamAccountName
    $events = @(Get-HdLockoutEvent $SamAccountName)
    if (-not $events) { Write-Host "  No lockout events (4740) for $SamAccountName in the last 24 hours." -ForegroundColor Green; return }
    Write-Host "`n  Lockout events for $SamAccountName (last 24h):" -ForegroundColor Cyan
    $events | Sort-Object TimeCreated -Descending | Format-Table TimeCreated, CallerComputer -AutoSize | Out-String -Width 220 | Write-Host
    $top = $events | Group-Object CallerComputer | Sort-Object Count -Descending | Select-Object -First 1
    Write-Host "  Most frequent source: $($top.Name) ($($top.Count) lockout(s))" -ForegroundColor Yellow
    if ($top.Name -match 'MOBILE|PHONE|IPHONE|ANDROID') {
        Write-Host '  Likely cause: a phone still using the OLD password (Wi-Fi / email profile). Ask the user to update or forget that network on the phone.'
    }
    else {
        Write-Host "  Likely cause: a saved credential, mapped drive, scheduled task or open session on $($top.Name). Check Credential Manager on that computer."
    }
}

function Show-AuditLog {
    if (-not (Test-Path $AuditLogPath)) { Write-Host '  Audit log is empty.'; return }
    Import-Csv $AuditLogPath | Select-Object -Last 15 | Format-Table -AutoSize | Out-String -Width 220 | Write-Host
}

function Invoke-Action {
    param([string]$Name, [string]$SamAccountName)
    switch ($Name) {
        'Lookup'        { Show-User $SamAccountName }
        'Unlock'        { Start-Unlock $SamAccountName }
        'Reset'         { Start-PasswordReset $SamAccountName }
        'LockoutSource' { Show-LockoutSource $SamAccountName }
        'AuditLog'      { Show-AuditLog }
    }
}

# ============================================================== main
Assert-ADModule

if ($Action) {
    try {
        if ($Action -ne 'AuditLog' -and -not $User) { throw '-User is required for this action.' }
        Invoke-Action $Action $User
    }
    catch {
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
    return
}

$modeText = if ($DemoMode) { 'DEMO MODE - sample users: jsmith, mgarcia, tnguyen, kpatel' } else { "LIVE - domain $env:USERDNSDOMAIN" }
while ($true) {
    Write-Host "`n=== AD Help Desk Tool ===  ($modeText)" -ForegroundColor Cyan
    Write-Host '  1) Look up user'
    Write-Host '  2) Unlock account'
    Write-Host '  3) Reset password'
    Write-Host '  4) Find lockout source'
    Write-Host '  5) View audit log'
    Write-Host '  Q) Quit'
    $choice = (Read-Host 'Choose').Trim().ToUpper()
    if ($choice -eq 'Q') { break }
    $map = @{ '1' = 'Lookup'; '2' = 'Unlock'; '3' = 'Reset'; '4' = 'LockoutSource'; '5' = 'AuditLog' }
    if (-not $map.ContainsKey($choice)) { Write-Host '  Invalid choice.' -ForegroundColor Red; continue }
    try {
        $name = ''
        if ($map[$choice] -ne 'AuditLog') { $name = (Read-Host 'User logon name (sAMAccountName)').Trim() }
        Invoke-Action $map[$choice] $name
    }
    catch {
        Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
    }
}
