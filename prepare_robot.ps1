param([string]$RobotIP = '192.168.234.1', [switch]$DownloadOnly)
$ErrorActionPreference = 'Stop'
$parsedAddress = $null
if (-not [System.Net.IPAddress]::TryParse($RobotIP, [ref]$parsedAddress)) { throw 'RobotIP must be an IP address' }
$sdkPath = Join-Path $PSScriptRoot '.sdk-cache'
$sdkCommit = 'b5fe0a86094507238944ad118721376a98615ac0'
if (-not (Test-Path -LiteralPath $sdkPath)) {
    & git clone https://github.com/AgibotTech/agibot_D1_Edu-Ultra.git $sdkPath
    if ($LASTEXITCODE -ne 0) { throw 'SDK download failed. Connect PC to Internet and retry.' }
}
& git -C $sdkPath checkout --detach $sdkCommit
if ($LASTEXITCODE -ne 0) { throw 'Could not select verified SDK revision' }
if ($DownloadOnly) { Write-Host 'SDK cached. Connect to D1 Wi-Fi and run this script again without -DownloadOnly.'; return }
$robotHost = "firefly@$RobotIP"
& ssh $robotHost 'mkdir -p /home/firefly/d1-follow/sdk/lib'
if ($LASTEXITCODE -ne 0) { throw 'Cannot connect to D1. Join its Wi-Fi and retry.' }
& scp (Join-Path $PSScriptRoot 'robot_follow.py') (Join-Path $PSScriptRoot 'run_follow.sh') (Join-Path $PSScriptRoot 'robot_check.py') "${robotHost}:/home/firefly/d1-follow/"
if ($LASTEXITCODE -ne 0) { throw 'Follower upload failed' }
& scp -r (Join-Path $sdkPath 'lib/zsl-1') "${robotHost}:/home/firefly/d1-follow/sdk/lib/"
if ($LASTEXITCODE -ne 0) { throw 'SDK upload failed' }
& scp (Join-Path $sdkPath 'LICENSE') "${robotHost}:/home/firefly/d1-follow/sdk/"
if ($LASTEXITCODE -ne 0) { throw 'SDK license upload failed' }
& ssh $robotHost "bash /home/firefly/d1-follow/run_follow.sh --check --local-ip $RobotIP"
if ($LASTEXITCODE -ne 0) { throw 'Uploaded, but robot prerequisite check failed. See diagnostic above.' }
Write-Host 'Installed and checked. No movement commands sent. Follow RUN_FOLLOW_TH.md to start.'
