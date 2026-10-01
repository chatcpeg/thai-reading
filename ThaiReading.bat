@echo off
rem ThaiReading.bat - Thai text to its spoken reading (style C) for TTS / AI voice models. For people:
rem   ThaiReading.bat                    interactive menu
rem   drag files onto this .bat          writes <name>_(read).<ext> beside each file, then waits for a key
rem   ThaiReading.bat --text "..."       one reading (plain text only: cmd breaks on " with & | < > ^)
rem AI agents / scripts: call  python thai_read.py ...  directly (see AGENTS.md).
rem Needs Python 3.8+ (py launcher or python on PATH). Standard library only.
rem Set THAI_READ_NOPAUSE=1 to never wait for a key.
setlocal
(for /f "tokens=2 delims=:." %%a in ('chcp') do set "OLDCP=%%a") <nul
set "OLDCP=%OLDCP: =%"
chcp 65001 >nul <nul
set "HERE=%~dp0"
set "PYTHONUTF8=1"
set "PY="
py -3 -c "import sys; assert sys.version_info >= (3, 8)" >nul 2>nul <nul && set "PY=py -3"
if not defined PY python -c "import sys; assert sys.version_info >= (3, 8)" >nul 2>nul <nul && set "PY=python"
if not defined PY goto :nopython
if "%~1"=="" goto :menu
rem files only (drag and drop) -> wait for a key at the end so the window can be read
set "DROP=1"
:scan
if "%~1"=="" goto :scanned
call :checkarg %1
shift
goto :scan
:scanned
%PY% "%HERE%thai_read.py" %*
set "RC=%ERRORLEVEL%"
if "%DROP%"=="1" if not defined THAI_READ_NOPAUSE pause
goto :done
:menu
%PY% "%HERE%thai_read.py" --menu
set "RC=%ERRORLEVEL%"
goto :done
:nopython
echo Python 3.8+ was not found. Install it from https://www.python.org/downloads/ and tick "Add to PATH".
set "RC=9009"
if not "%~1"=="" if not defined THAI_READ_NOPAUSE pause
goto :done
:checkarg
set "A=%~1"
if "%A:~0,1%"=="-" set "DROP=0" & goto :eof
if not exist "%~1" set "DROP=0"
goto :eof
:done
if defined OLDCP chcp %OLDCP% >nul <nul
endlocal & exit /b %RC%
