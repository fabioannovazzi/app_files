<# Probe bootstrap interpreters before using Vera's managed CPython 3.12.
   No package discovery, registry edits, execution-policy changes or archive writes.
#>
[CmdletBinding(PositionalBinding=$false)]
param(
    [Parameter(Mandatory=$true)][guid]$SessionId,
    [string]$PythonExecutable,
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$ArchiveArguments
)
$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot 'studio_archive_session.py'
if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
    throw 'archive_package_unreadable: select the actual installed Vera scripts folder.'
}
# Windows argv quoting is mechanical: preserve spaces, quotes and trailing slashes.
function Quote-Argument([string]$Value) {
    return '"' + ([regex]::Replace(([regex]::Replace($Value, '(\\*)"', '$1$1\"')), '(\\+)$', '$1$1')) + '"'
}
function Probe-Python([string]$Executable, [string[]]$Prefix) {
    $probe = 'import sys,pathlib,json; assert sys.implementation.name == "cpython" and sys.version_info >= (3,10); p=pathlib.Path(sys.argv[1]); p.open("rb").close(); print(json.dumps({"vera_bootstrap":True,"executable":sys.executable}))'
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = ((@($Prefix) + @('-I','-c',$probe,$entry)) | ForEach-Object { Quote-Argument $_ }) -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(15000)) {
            $process.Kill()
            return $null
        }
        if ($process.ExitCode -ne 0) { return $null }
        $result = $stdout.GetAwaiter().GetResult() | ConvertFrom-Json -ErrorAction SilentlyContinue
        if (-not $result) { return $null }
        if ($result.vera_bootstrap -eq $true -and (Test-Path -LiteralPath $result.executable -PathType Leaf)) {
            return [string]$result.executable
        }
    } catch [System.ComponentModel.Win32Exception] {
        return $null
    } catch [System.ArgumentException] {
        return $null
    } finally {
        $process.Dispose()
    }
    return $null
}
$candidates = @()
if ($PythonExecutable) {
    $candidates += @{ Name=$PythonExecutable; Prefix=@() }
} else {
    $candidates += @{ Name='py'; Prefix=@('-3') }
    $candidates += @{ Name='python'; Prefix=@() }
    $candidates += @{ Name='python3'; Prefix=@() }
}
$selected = $null
foreach ($candidate in $candidates) {
    $resolved = Get-Command $candidate.Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $resolved) { continue }
    $selected = Probe-Python $resolved.Source $candidate.Prefix
    if ($selected) { break }
}
if (-not $selected) {
    throw 'archive_bootstrap_unavailable: no callable CPython 3.10+ could read the installed Vera entrypoint. Check App Installer aliases and the actual plugin path, or supply -PythonExecutable with a working interpreter. No archive was created. Do not rename Python executables or change Windows security settings.'
}
if (-not $ArchiveArguments) { $ArchiveArguments = @('diagnose') }
& $selected $entry '--session-id' $SessionId.ToString() @ArchiveArguments
exit $LASTEXITCODE
