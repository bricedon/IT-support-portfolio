<#
.SYNOPSIS
    Runs a first-line health check on a Windows workstation and saves a color-coded HTML report.

.DESCRIPTION
    Built for the first 5 minutes of a desk-side or remote support call. Instead of opening
    ten different tools, the technician runs one script and gets a single report covering:

      - System info (model, serial, OS build, uptime)
      - Disk space on every fixed drive
      - Memory and CPU load
      - Network adapters (IP, gateway, DNS, DHCP) with APIPA (169.254.x.x) detection
      - Connectivity: gateway ping, DNS resolution, internet ping, HTTPS port 443
      - Pending reboot (Windows Update, servicing stack, file rename)
      - Critical services (Print Spooler, DNS Client, DHCP Client, Time, Defender, Windows Update)
      - Microsoft Defender status
      - Count of System log errors in the last 24 hours

    Every check returns PASS, WARN, FAIL or INFO, so the technician knows where to look first.
    Every check is wrapped in try/catch: one failed check never stops the report.

.PARAMETER OutputFolder
    Folder where the HTML report is saved. Default: the current user's Desktop (or current folder).

.PARAMETER TestHosts
    External hosts used for the internet connectivity test.

.PARAMETER OpenReport
    Opens the HTML report in the default browser when finished.

.EXAMPLE
    .\Get-EndpointHealth.ps1 -OpenReport

.EXAMPLE
    .\Get-EndpointHealth.ps1 -OutputFolder C:\Temp -TestHosts 1.1.1.1,microsoft.com

.NOTES
    Author : Brice Albert Donfack
    Runs on: Windows PowerShell 5.1 and PowerShell 7+. No admin rights required
             (a few checks show more detail when run as administrator).
#>
[CmdletBinding()]
param(
    [string]$OutputFolder,
    [string[]]$TestHosts = @('8.8.8.8', 'www.microsoft.com'),
    [switch]$OpenReport
)

$ErrorActionPreference = 'Stop'
$onWindows = ($PSVersionTable.PSEdition -eq 'Desktop') -or ($IsWindows -eq $true)

if (-not $OutputFolder) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $OutputFolder = if ($desktop -and (Test-Path $desktop)) { $desktop } else { (Get-Location).Path }
}

$results = New-Object System.Collections.Generic.List[object]

function Add-Result {
    param(
        [string]$Category,
        [string]$Check,
        [ValidateSet('PASS', 'WARN', 'FAIL', 'INFO')][string]$Status,
        [string]$Detail
    )
    $results.Add([pscustomobject]@{
        Category = $Category
        Check    = $Check
        Status   = $Status
        Detail   = $Detail
    })
}

function Invoke-Check {
    # Runs one check; if it throws, records a WARN instead of crashing the whole report.
    param([string]$Category, [string]$Name, [scriptblock]$Script)
    try {
        & $Script
    }
    catch {
        Add-Result $Category $Name 'WARN' "Check could not run: $($_.Exception.Message)"
    }
}

function Test-Ping {
    param([string]$Target, [int]$TimeoutMs = 2000)
    try {
        $reply = (New-Object System.Net.NetworkInformation.Ping).Send($Target, $TimeoutMs)
        return [pscustomobject]@{ Success = ($reply.Status -eq 'Success'); Ms = $reply.RoundtripTime }
    }
    catch {
        return [pscustomobject]@{ Success = $false; Ms = $null }
    }
}

function Test-TcpPort {
    param([string]$Target, [int]$Port, [int]$TimeoutMs = 3000)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($Target, $Port, $null, $null)
        if ($async.AsyncWaitHandle.WaitOne($TimeoutMs) -and $client.Connected) {
            $client.EndConnect($async)
            return $true
        }
        return $false
    }
    catch { return $false }
    finally { $client.Close() }
}

Write-Host "Running endpoint health check on $([Environment]::MachineName)..." -ForegroundColor Cyan

# ---------------------------------------------------------------- System
Invoke-Check 'System' 'Computer info' {
    if (-not $onWindows) { Add-Result 'System' 'Computer info' 'INFO' "Non-Windows host: $([Environment]::OSVersion.VersionString)"; return }
    $cs   = Get-CimInstance Win32_ComputerSystem
    $os   = Get-CimInstance Win32_OperatingSystem
    $bios = Get-CimInstance Win32_BIOS
    Add-Result 'System' 'Computer' 'INFO' "$($cs.Manufacturer) $($cs.Model) | Serial: $($bios.SerialNumber)"
    Add-Result 'System' 'Operating system' 'INFO' "$($os.Caption) | Build $($os.BuildNumber)"
    Add-Result 'System' 'Logged-on user' 'INFO' "$($cs.UserName) | Domain: $($cs.Domain)"

    $uptime = (Get-Date) - $os.LastBootUpTime
    $uptimeText = '{0}d {1}h {2}m (last boot {3})' -f $uptime.Days, $uptime.Hours, $uptime.Minutes, $os.LastBootUpTime
    $status = if ($uptime.TotalDays -ge 14) { 'WARN' } else { 'PASS' }
    $hint = if ($status -eq 'WARN') { ' - consider a restart' } else { '' }
    Add-Result 'System' 'Uptime' $status ($uptimeText + $hint)
}

# ---------------------------------------------------------------- Disk
Invoke-Check 'Storage' 'Disk space' {
    if (-not $onWindows) { Add-Result 'Storage' 'Disk space' 'INFO' 'Skipped (Windows only)'; return }
    $disks = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'
    foreach ($d in $disks) {
        if (-not $d.Size) { continue }
        $freePct = [math]::Round(($d.FreeSpace / $d.Size) * 100, 1)
        $freeGB  = [math]::Round($d.FreeSpace / 1GB, 1)
        $sizeGB  = [math]::Round($d.Size / 1GB, 1)
        $status  = if ($freePct -lt 5) { 'FAIL' } elseif ($freePct -lt 15) { 'WARN' } else { 'PASS' }
        Add-Result 'Storage' "Drive $($d.DeviceID)" $status "$freeGB GB free of $sizeGB GB ($freePct% free)"
    }
}

# ---------------------------------------------------------------- Performance
Invoke-Check 'Performance' 'Memory and CPU' {
    if (-not $onWindows) { Add-Result 'Performance' 'Memory and CPU' 'INFO' 'Skipped (Windows only)'; return }
    $os = Get-CimInstance Win32_OperatingSystem
    $usedPct = [math]::Round((1 - ($os.FreePhysicalMemory / $os.TotalVisibleMemorySize)) * 100, 1)
    $totalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
    $status  = if ($usedPct -ge 95) { 'FAIL' } elseif ($usedPct -ge 85) { 'WARN' } else { 'PASS' }
    Add-Result 'Performance' 'Memory usage' $status "$usedPct% used of $totalGB GB"

    $cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    $status = if ($cpu -ge 95) { 'FAIL' } elseif ($cpu -ge 80) { 'WARN' } else { 'PASS' }
    Add-Result 'Performance' 'CPU load' $status "$cpu% (snapshot)"

    $top = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 3 |
        ForEach-Object { '{0} ({1} MB)' -f $_.ProcessName, [math]::Round($_.WorkingSet64 / 1MB) }
    Add-Result 'Performance' 'Top memory processes' 'INFO' ($top -join ', ')
}

# ---------------------------------------------------------------- Network
$gateways = @()
Invoke-Check 'Network' 'Adapters' {
    if (-not $onWindows) { Add-Result 'Network' 'Adapters' 'INFO' 'Skipped (Windows only)'; return }
    $adapters = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=True'
    if (-not $adapters) { Add-Result 'Network' 'Adapters' 'FAIL' 'No adapter has an IP address - check cable / Wi-Fi'; return }

    foreach ($a in $adapters) {
        $ipv4 = @($a.IPAddress | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' })
        $gw   = @($a.DefaultIPGateway | Where-Object { $_ })
        $dns  = @($a.DNSServerSearchOrder | Where-Object { $_ })
        $script:gateways += $gw

        $detail = "IP: $($ipv4 -join ', ') | Gateway: $($gw -join ', ') | DNS: $($dns -join ', ') | DHCP: $($a.DHCPEnabled) | MAC: $($a.MACAddress)"
        if ($ipv4 | Where-Object { $_ -like '169.254.*' }) {
            Add-Result 'Network' $a.Description 'FAIL' "APIPA address - DHCP server not reachable. $detail"
        }
        elseif (-not $gw) {
            Add-Result 'Network' $a.Description 'WARN' "No default gateway. $detail"
        }
        else {
            Add-Result 'Network' $a.Description 'PASS' $detail
        }
    }
}

Invoke-Check 'Connectivity' 'Default gateway' {
    if (-not $gateways) { Add-Result 'Connectivity' 'Default gateway' 'INFO' 'No gateway to test'; return }
    foreach ($gw in ($gateways | Select-Object -Unique)) {
        $p = Test-Ping $gw
        if ($p.Success) { Add-Result 'Connectivity' "Ping gateway $gw" 'PASS' "$($p.Ms) ms" }
        else { Add-Result 'Connectivity' "Ping gateway $gw" 'FAIL' 'No reply - local network / VLAN / switch port issue' }
    }
}

Invoke-Check 'Connectivity' 'DNS resolution' {
    $name = 'www.microsoft.com'
    $addresses = [System.Net.Dns]::GetHostAddresses($name)
    Add-Result 'Connectivity' "DNS lookup ($name)" 'PASS' "Resolved to $($addresses[0].IPAddressToString)"
}

foreach ($h in $TestHosts) {
    Invoke-Check 'Connectivity' "Ping $h" {
        $p = Test-Ping $h
        if ($p.Success) { Add-Result 'Connectivity' "Ping $h" 'PASS' "$($p.Ms) ms" }
        else { Add-Result 'Connectivity' "Ping $h" 'WARN' 'No reply (ICMP may be blocked by firewall)' }
    }
}

Invoke-Check 'Connectivity' 'HTTPS (443)' {
    $target = 'www.microsoft.com'
    if (Test-TcpPort $target 443) { Add-Result 'Connectivity' "HTTPS to $target" 'PASS' 'Port 443 open' }
    else { Add-Result 'Connectivity' "HTTPS to $target" 'FAIL' 'Port 443 unreachable - proxy / firewall / internet issue' }
}

# ---------------------------------------------------------------- Pending reboot
Invoke-Check 'Maintenance' 'Pending reboot' {
    if (-not $onWindows) { Add-Result 'Maintenance' 'Pending reboot' 'INFO' 'Skipped (Windows only)'; return }
    $reasons = @()
    if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') { $reasons += 'Component Based Servicing' }
    if (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired') { $reasons += 'Windows Update' }
    $sm = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager' -ErrorAction SilentlyContinue
    if ($sm -and $sm.PendingFileRenameOperations) { $reasons += 'Pending file rename' }

    if ($reasons) { Add-Result 'Maintenance' 'Pending reboot' 'WARN' "Reboot required: $($reasons -join ', ')" }
    else { Add-Result 'Maintenance' 'Pending reboot' 'PASS' 'No reboot pending' }
}

# ---------------------------------------------------------------- Services
Invoke-Check 'Services' 'Critical services' {
    if (-not $onWindows) { Add-Result 'Services' 'Critical services' 'INFO' 'Skipped (Windows only)'; return }
    $critical = [ordered]@{
        'Spooler'   = 'Print Spooler'
        'Dnscache'  = 'DNS Client'
        'Dhcp'      = 'DHCP Client'
        'W32Time'   = 'Windows Time'
        'WinDefend' = 'Microsoft Defender Antivirus'
        'wuauserv'  = 'Windows Update'
    }
    foreach ($svcName in $critical.Keys) {
        $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
        if (-not $svc) { Add-Result 'Services' $critical[$svcName] 'INFO' 'Not installed'; continue }
        if ($svc.Status -eq 'Running') {
            Add-Result 'Services' $critical[$svcName] 'PASS' 'Running'
        }
        elseif ($svcName -eq 'wuauserv') {
            # Windows Update is a demand-start service; Stopped is normal between scans.
            Add-Result 'Services' $critical[$svcName] 'INFO' "$($svc.Status) (starts on demand)"
        }
        else {
            Add-Result 'Services' $critical[$svcName] 'FAIL' "$($svc.Status) - try: Start-Service $svcName"
        }
    }
}

# ---------------------------------------------------------------- Security
Invoke-Check 'Security' 'Microsoft Defender' {
    if (-not (Get-Command Get-MpComputerStatus -ErrorAction SilentlyContinue)) {
        Add-Result 'Security' 'Microsoft Defender' 'INFO' 'Defender module not available on this device'; return
    }
    $mp = Get-MpComputerStatus
    $sigAge = $mp.AntivirusSignatureAge
    if (-not $mp.RealTimeProtectionEnabled) {
        Add-Result 'Security' 'Defender real-time protection' 'FAIL' 'Real-time protection is OFF'
    }
    else {
        Add-Result 'Security' 'Defender real-time protection' 'PASS' 'Enabled'
    }
    $status = if ($sigAge -gt 7) { 'FAIL' } elseif ($sigAge -gt 2) { 'WARN' } else { 'PASS' }
    Add-Result 'Security' 'Defender signatures' $status "Signature age: $sigAge day(s)"
}

# ---------------------------------------------------------------- Event log
Invoke-Check 'Events' 'System log errors (24h)' {
    if (-not $onWindows) { Add-Result 'Events' 'System log errors (24h)' 'INFO' 'Skipped (Windows only)'; return }
    $events = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; Level = 1, 2; StartTime = (Get-Date).AddDays(-1) } -ErrorAction SilentlyContinue)
    $count = $events.Count
    $status = if ($count -ge 25) { 'WARN' } else { 'PASS' }
    $topSources = $events | Group-Object ProviderName | Sort-Object Count -Descending | Select-Object -First 3 |
        ForEach-Object { "$($_.Name) ($($_.Count))" }
    $detail = "$count critical/error event(s)"
    if ($topSources) { $detail += " | Top sources: $($topSources -join ', ')" }
    Add-Result 'Events' 'System log errors (24h)' $status $detail
}

# ---------------------------------------------------------------- Report
$counts = @{}
foreach ($s in 'PASS', 'WARN', 'FAIL', 'INFO') { $counts[$s] = @($results | Where-Object Status -eq $s).Count }
$overall = if ($counts.FAIL) { 'FAIL' } elseif ($counts.WARN) { 'WARN' } else { 'PASS' }

$hostName  = [Environment]::MachineName
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$enc = { param($t) [System.Net.WebUtility]::HtmlEncode([string]$t) }

$rows = foreach ($r in $results) {
    "<tr><td>$(& $enc $r.Category)</td><td>$(& $enc $r.Check)</td><td class='s $($r.Status)'>$($r.Status)</td><td>$(& $enc $r.Detail)</td></tr>"
}

$html = @"
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Endpoint Health - $hostName</title>
<style>
 body{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#f4f6f8;color:#1f2937}
 h1{margin:0 0 4px} .sub{color:#6b7280;margin-bottom:16px}
 .cards{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}
 .card{background:#fff;border-radius:8px;padding:12px 18px;box-shadow:0 1px 3px rgba(0,0,0,.1);min-width:90px}
 .card b{font-size:22px;display:block}
 table{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.1)}
 th,td{padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:left;font-size:14px;vertical-align:top}
 th{background:#111827;color:#fff}
 .s{font-weight:700;text-align:center;width:60px}
 .PASS{color:#047857;background:#d1fae5}.WARN{color:#92400e;background:#fef3c7}
 .FAIL{color:#991b1b;background:#fee2e2}.INFO{color:#1e40af;background:#dbeafe}
</style></head><body>
<h1>Endpoint Health Report</h1>
<div class="sub">$hostName &middot; $timestamp &middot; Overall: <span class="s $overall">$overall</span></div>
<div class="cards">
 <div class="card PASS"><b>$($counts.PASS)</b>PASS</div>
 <div class="card WARN"><b>$($counts.WARN)</b>WARN</div>
 <div class="card FAIL"><b>$($counts.FAIL)</b>FAIL</div>
 <div class="card INFO"><b>$($counts.INFO)</b>INFO</div>
</div>
<table><tr><th>Category</th><th>Check</th><th>Status</th><th>Detail</th></tr>
$($rows -join "`n")
</table></body></html>
"@

$fileName = 'EndpointHealth_{0}_{1}.html' -f $hostName, (Get-Date -Format 'yyyyMMdd_HHmmss')
$reportPath = Join-Path $OutputFolder $fileName
$html | Out-File -FilePath $reportPath -Encoding utf8

# Console summary
Write-Host ''
foreach ($r in $results | Where-Object { $_.Status -in 'FAIL', 'WARN' }) {
    $color = if ($r.Status -eq 'FAIL') { 'Red' } else { 'Yellow' }
    Write-Host ("[{0}] {1} - {2}: {3}" -f $r.Status, $r.Category, $r.Check, $r.Detail) -ForegroundColor $color
}
Write-Host ("`nOverall: {0}  (PASS {1} / WARN {2} / FAIL {3} / INFO {4})" -f $overall, $counts.PASS, $counts.WARN, $counts.FAIL, $counts.INFO) -ForegroundColor Cyan
Write-Host "Report saved: $reportPath" -ForegroundColor Cyan

if ($OpenReport) { Invoke-Item $reportPath }
