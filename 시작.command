#!/bin/bash
# KICE Lynx 시작 스크립트 (Mac)

APP_DIR="$(cd "$(dirname "$0")/app" && pwd)"
PYTHON="$APP_DIR/python/bin/python3"

if [ ! -f "$PYTHON" ]; then
  osascript -e 'display dialog "프로그램 파일이 손상되었습니다.\n압축 파일을 다시 내려받아 주세요." with title "KICE Lynx — 오류" buttons {"확인"} default button 1 with icon stop'
  exit 1
fi

"$PYTHON" "$APP_DIR/launcher.py" &

sleep 1
osascript -e 'tell application "Terminal" to close front window' 2>/dev/null
