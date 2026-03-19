@echo off
:: KICE Lynx 시작 스크립트 (Windows)

cd /d "%~dp0app"

:: pythonw.exe 사용 (터미널 창 없이 실행)
if exist "python\pythonw.exe" (
    start "" /b "python\pythonw.exe" launcher.py
) else (
    :: embedded Python 없으면 오류 안내
    powershell -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('프로그램 파일이 손상되었습니다.`n폴더를 삭제하고 다시 다운로드해주세요.', 'KICE Lynx — 오류', 'OK', 'Error')"
)
