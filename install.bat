@echo off
setlocal
title KICE Lynx 설치 도우미

echo.
echo =======================================================
echo   KICE Lynx 설치를 시작합니다.
echo   잠시 후 설치 창이 나타납니다...
echo =======================================================
echo.

:: 번들된 파이썬으로 설치 스크립트 실행
if exist "app\python\python.exe" (
    start "" /b "app\python\python.exe" "setup.py"
) else (
    echo [오류] 필수 파일이 누락되었습니다. 압축을 다시 풀어주세요.
    pause
)

exit
