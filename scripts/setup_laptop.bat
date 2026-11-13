@echo off
rem APEX laptop one-click setup. Double-click this file. It does NOT bypass the human-in-the-loop design:
rem it only installs dependencies, fetches the agent script, and starts it - the agent still asks for your
rem bridge key and (unless you created ~/.apex_agent_auto_confirm yourself) still shows you every task.
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "VENV=%USERPROFILE%\apex-agent\venv"
set "AGENT_URL=https://console.apexcorelab.uk/bridge/agent.py"
set "AGENT_FILE=%~dp0laptop_agent.py"
set "KEYFILE_HINT=%~dp0bridge_key.txt"
set "DOWNLOADS=%USERPROFILE%\Downloads\laptop_agent.py"

echo ===== APEX laptop setup =====

echo [1/5] Checking Python...
where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Opening the download page - install it, TICK "Add python.exe to PATH", then double-click this file again.
  start https://www.python.org/downloads/
  pause
  exit /b 1
)

echo [2/5] Setting up the virtual environment ^(one time^)...
if not exist "%VENV%\Scripts\python.exe" (
  py -3 -m venv "%VENV%" || goto :fail
)
"%VENV%\Scripts\python.exe" -c "import fastapi, playwright" >nul 2>nul
if errorlevel 1 (
  echo Installing packages ^(one time, takes a minute^)...
  "%VENV%\Scripts\python.exe" -m pip install --upgrade pip --quiet || goto :fail
  "%VENV%\Scripts\python.exe" -m pip install fastapi uvicorn playwright --quiet || goto :fail
  "%VENV%\Scripts\python.exe" -m playwright install chromium || goto :fail
)

echo [3/5] Getting the agent script...
if not exist "%AGENT_FILE%" (
  if exist "%DOWNLOADS%" del /f /q "%DOWNLOADS%" >nul 2>nul
  echo Opening your browser to download it ^(sign in with Cloudflare Access if asked^)...
  start "" "%AGENT_URL%"
  echo Waiting up to 2 minutes for the download to finish...
  set /a tries=0
  :waitloop
  if exist "%DOWNLOADS%" (
    timeout /t 1 /nobreak >nul
    move /y "%DOWNLOADS%" "%AGENT_FILE%" >nul
    goto :gotagent
  )
  set /a tries+=1
  if !tries! GEQ 120 (
    echo Did not see the download finish. Save the file as laptop_agent.py in this folder, then run this file again:
    echo   %~dp0
    pause
    exit /b 1
  )
  timeout /t 1 /nobreak >nul
  goto :waitloop
  :gotagent
  echo Saved to %AGENT_FILE%
)

echo [4/5] Bridge key...
if exist "%KEYFILE_HINT%" (
  if not exist "%USERPROFILE%\.apex_agent_key" (
    copy /y "%KEYFILE_HINT%" "%USERPROFILE%\.apex_agent_key" >nul
    echo Used bridge_key.txt from this folder. Delete that file now if you like - the key is saved for next time.
  )
) else (
  echo ^(No bridge_key.txt found here - the agent will ask you to paste the key the first time it runs.^)
)

echo [5/5] Starting the agent. It will show every task before running it, unless you created %%USERPROFILE%%\.apex_agent_auto_confirm yourself.
echo Close this window to stop the agent.
"%VENV%\Scripts\python.exe" "%AGENT_FILE%"
goto :eof

:fail
echo Something failed above. Nothing was started.
pause
exit /b 1
