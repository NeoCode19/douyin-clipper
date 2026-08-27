@echo off
rem Register dyclip:// custom protocol (one-time setup).
rem After this, the extension popup can wake up the local assistant on demand.
rem Uninstall: reg delete HKCU\Software\Classes\dyclip /f

setlocal
for /f "delims=" %%p in ('where pythonw 2^>nul') do set PYW=%%p
if not defined PYW (
    echo [X] pythonw.exe not found - check Python installation / PATH
    pause & exit /b 1
)

set ROOT=%~dp0..
set PYW_SCRIPT=%ROOT%\scripts\assistant.pyw
for %%i in ("%PYW_SCRIPT%") do set PYW_SCRIPT=%%~fi

reg add "HKCU\Software\Classes\dyclip" /ve /d "URL:douyin-clipper Assistant" /f >nul
reg add "HKCU\Software\Classes\dyclip" /v "URL Protocol" /d "" /f >nul
reg add "HKCU\Software\Classes\dyclip\shell\open\command" /ve /d "\"%PYW%\" \"%PYW_SCRIPT%\" \"%%1\"" /f >nul

echo [OK] dyclip:// protocol registered ^(pythonw: %PYW%^)
pause
