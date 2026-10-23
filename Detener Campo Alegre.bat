@echo off
rem Detiene el sistema Campo Alegre si quedo funcionando sin ventana.
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Sistema detenido.
pause
