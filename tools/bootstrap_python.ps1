param(
    [string]$RuntimeRoot = "$env:LOCALAPPDATA\ReportChecker\runtime"
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$pythonDir = Join-Path $RuntimeRoot 'python'
$pythonExe = Join-Path $pythonDir 'python.exe'

if (Test-Path $pythonExe) {
    Write-Host "Python runtime already exists: $pythonExe"
    exit 0
}

New-Item -ItemType Directory -Force -Path $pythonDir | Out-Null

$mirrors = @(
    @{ Name = 'HuaweiCloud'; Url = 'https://mirrors.huaweicloud.com/python/3.11.9/python-3.11.9-embed-amd64.zip' },
    @{ Name = 'npmmirror'; Url = 'https://registry.npmmirror.com/-/binary/python/3.11.9/python-3.11.9-embed-amd64.zip' },
    @{ Name = 'Aliyun'; Url = 'https://mirrors.aliyun.com/python-release/windows/python-3.11.9-embed-amd64.zip' }
)

$zip = Join-Path $env:TEMP 'reportchecker_python311.zip'
$ok = $false
foreach ($m in $mirrors) {
    try {
        Write-Host "Downloading Python 3.11.9 from $($m.Name)..."
        Invoke-WebRequest -Uri $m.Url -OutFile $zip -UseBasicParsing
        $ok = $true
        break
    } catch {
        Write-Host "  failed: $($_.Exception.Message)"
    }
}
if (-not $ok) {
    Write-Host 'All Python mirrors failed. Check network and retry.'
    exit 1
}

Expand-Archive -Path $zip -DestinationPath $pythonDir -Force
Remove-Item $zip -Force

$pth = Join-Path $pythonDir 'python311._pth'
@"
python311.zip
.
Lib\site-packages

import site
"@ | Set-Content -Path $pth -Encoding ASCII

$getPip = Join-Path $env:TEMP 'reportchecker_get-pip.py'
Write-Host 'Installing pip from Aliyun...'
Invoke-WebRequest -Uri 'https://mirrors.aliyun.com/pypi/get-pip.py' -OutFile $getPip -UseBasicParsing
& $pythonExe $getPip -i 'https://pypi.tuna.tsinghua.edu.cn/simple'
Remove-Item $getPip -Force

Write-Host 'Upgrading pip...'
& $pythonExe -m pip install --upgrade pip setuptools wheel `
    -i 'https://pypi.tuna.tsinghua.edu.cn/simple' --no-warn-script-location

Write-Host "Python runtime ready: $pythonExe"
exit 0
