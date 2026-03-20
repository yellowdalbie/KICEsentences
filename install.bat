@echo off
setlocal
chcp 65001 >nul
title KICE Lynx 설치 도우미

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

echo.
echo =======================================================
echo   KICE Lynx 설치를 시작합니다.
echo   잠시 후 설치 창이 나타납니다...
echo =======================================================
echo.

:: 번들된 파이썬으로 설치 스크립트 실행
set "PYTHON_EXE=%ROOT_DIR%app\python\python.exe"
set "SETUP_PY=%ROOT_DIR%setup.py"

if exist "%PYTHON_EXE%" (
    start "" "%PYTHON_EXE%" "%SETUP_PY%"
) else (
    echo [오류] 필수 파일이 누락되었습니다. 압축을 다시 풀어주세요.
    echo 누락된 경로: "%PYTHON_EXE%"
    pause
)

exit
