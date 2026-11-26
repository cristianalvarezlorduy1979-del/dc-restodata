@echo off
chcp 65001 >nul
title Diagnostico de Almacen y Mermas - DC Restaurantes
cd /d "%~dp0"

echo ======================================================================
echo   DC RESTAURANTES - EXPLORADOR DE ALMACEN, COMIDA Y MERMAS (SR11)
echo ======================================================================
echo.

if exist "probar_tablas_almacen.py" goto :RUN_PY

echo [ERROR] No se encontro probar_tablas_almacen.py en esta carpeta.
pause
exit /b 1

:RUN_PY
python probar_tablas_almacen.py
goto :FIN

:FIN
echo.
echo Presione cualquier tecla para salir...
pause >nul
