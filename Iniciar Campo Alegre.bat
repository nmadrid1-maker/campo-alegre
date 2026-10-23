@echo off
rem Inicia el sistema Campo Alegre y abre el navegador. Doble clic para usarlo.
cd /d "%~dp0"
set CAMPO_ALEGRE_PRODUCCION=1
title Campo Alegre
if exist ".venv\Scripts\python.exe" (set PY=".venv\Scripts\python.exe") else (set PY=py)
echo Iniciando el sistema Campo Alegre...
echo No cierre esta ventana mientras use el sistema.
%PY% run.py
echo.
echo El sistema se detuvo. Si fue por un error, copie el mensaje de arriba.
if /i not "%1"=="oculto" pause
