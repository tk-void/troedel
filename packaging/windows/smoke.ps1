# Checks on this machine that what build.py made starts: the unpacked ZIP,
# its window, and the installer if one was built. Run after build.py, on
# Windows.
$ErrorActionPreference = "Stop"

function Wait-ForTroedel($port) {
    foreach ($i in 1..60) {
        try {
            if ((Invoke-WebRequest "http://127.0.0.1:$port/health" -UseBasicParsing).StatusCode -eq 200) { return }
        } catch { Start-Sleep -Seconds 1 }
    }
    throw "Troedel did not answer on port $port within a minute"
}

$archive = (Get-ChildItem dist\troedel-*-windows-x64.zip)[0].FullName
$work = Join-Path $env:TEMP "troedel-smoke"
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive $archive -DestinationPath $work
$folder = (Get-ChildItem $work -Directory)[0].FullName
$python = Join-Path $folder "python\python.exe"
$env:TROEDEL_DATA_DIR = Join-Path $work "data"

# The server by itself, with a console.
$env:TROEDEL_PORT = "8765"
$server = Start-Process $python -ArgumentList "-I", "-m", "troedel" -PassThru -NoNewWindow
try {
    Wait-ForTroedel 8765
    $setup = Invoke-WebRequest "http://127.0.0.1:8765/setup" -UseBasicParsing
    if ($setup.Content -notmatch "troedel.css") { throw "the setup page came without its stylesheet" }
} finally {
    Stop-Process -Id $server.Id -Force
}

& $python -I -c "import tkinter, segno, rembg, onnxruntime, pillow_heif, argon2; tkinter.Tcl().eval('package require Tk'); print('imports ok')"
if ($LASTEXITCODE -ne 0) { throw "a bundled package does not load" }

# The way a double-click starts it: no console, the window.
$env:TROEDEL_PORT = "8766"
$window = Start-Process (Join-Path $folder "python\pythonw.exe") -ArgumentList "-I", "-m", "troedel", "window" -PassThru
try {
    Wait-ForTroedel 8766
} catch {
    Get-Content (Join-Path $env:TROEDEL_DATA_DIR "troedel.log") -ErrorAction SilentlyContinue
    throw
} finally {
    Stop-Process -Id $window.Id -Force -ErrorAction SilentlyContinue
}

$installer = Get-ChildItem dist\troedel-*-windows-x64-setup.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if ($installer) {
    $target = Join-Path $work "installed"
    $run = Start-Process $installer.FullName -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=`"$target`"" -PassThru -Wait
    if ($run.ExitCode -ne 0) { throw "the installer ended with $($run.ExitCode)" }
    if (-not (Test-Path (Join-Path $target "python\pythonw.exe"))) { throw "the installer left no Python behind" }
    $shortcut = Join-Path ([Environment]::GetFolderPath("Programs")) "Tr$([char]0xF6)del.lnk"
    if (-not (Test-Path $shortcut)) { throw "no entry in the start menu" }
    $env:TROEDEL_PORT = "8767"
    $window = Start-Process (Join-Path $target "python\pythonw.exe") -ArgumentList "-I", "-m", "troedel", "window" -PassThru
    try { Wait-ForTroedel 8767 } finally { Stop-Process -Id $window.Id -Force -ErrorAction SilentlyContinue }
    $remove = Start-Process (Join-Path $target "unins000.exe") -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -PassThru -Wait
    if ($remove.ExitCode -ne 0) { throw "the uninstaller ended with $($remove.ExitCode)" }
    if (Test-Path (Join-Path $target "python")) { throw "the uninstaller left the program behind" }
    if (-not (Test-Path $env:TROEDEL_DATA_DIR)) { throw "the uninstaller took the data with it" }
} elseif ($env:CI) {
    throw "no installer was built"
}
