: << 'CMDBLOCK'
@echo off
REM Runs scripts\voice_alerts.py with a Python 3, on Windows and on Unix.
REM On Windows cmd.exe runs this batch part; on Unix the shell skips it
REM (":" is a no-op reading a heredoc) and runs the part at the bottom.
REM A voice alert must never break a session, so both parts exit 0.
REM
REM Each candidate is run once before it is used: on many machines "python"
REM and "python3" are Microsoft Store placeholders that only print a message.
REM where.exe is called by full path and with $PATH: so nothing comes from
REM the current directory.

setlocal
set "PYEXE="
if not defined SystemRoot exit /b 0
for %%C in (py python python3) do (
  if not defined PYEXE for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" $PATH:%%C 2^>nul') do (
    if not defined PYEXE "%%P" -c "import sys; sys.exit(sys.version_info < (3, 8))" <nul >nul 2>nul && set "PYEXE=%%P"
  )
)
if not defined PYEXE exit /b 0
"%PYEXE%" "%~dp0..\scripts\voice_alerts.py" %*
exit /b 0
CMDBLOCK

# Unix: find a Python 3 and run voice-alerts.
case "$0" in
  */*|*\\*) dir="${0%[/\\]*}" ;;
  *) dir="." ;;
esac
for py in python3 python; do
  if command -v "$py" >/dev/null 2>&1 &&
     "$py" -c 'import sys; sys.exit(sys.version_info < (3, 8))' </dev/null >/dev/null 2>&1; then
    "$py" "$dir/../scripts/voice_alerts.py" "$@"
    exit 0
  fi
done
exit 0
