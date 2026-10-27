@echo off
rem Windows entry point next to the sh one: PowerShell and cmd cannot run an
rem extensionless sh script and hand it to the "Open with" dialog instead.
python "%~dp0..\skills\break-it-down\tasks.py" %*
