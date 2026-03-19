#!/bin/bash
cd "$(dirname "$0")"
echo "==========================================="
echo "   KICE Lynx 보안 격리 해제 도우미"
echo "==========================================="
echo ""
echo "이 스크립트는 macOS의 '확인되지 않은 개발자' 차단"
echo "및 '휴지통으로 이동' 경고를 해결합니다."
echo ""

APP_NAME="KICE Lynx.app"

if [ ! -d "$APP_NAME" ]; then
    echo "❌ 에러: '$APP_NAME' 파일을 찾을 수 없습니다."
    echo "이 파일을 압축 해제한 폴더(앱과 같은 위치)에 넣고 다시 실행해 주세요."
    exit 1
fi

echo "1. 보안 격리 속성(Quarantine) 제거 중..."
# 앱 번들과 내부 리소스(python 등)가 담긴 app 폴더 모두 격리 해제
xattr -cr "$APP_NAME" "app" 2>/dev/null

echo "2. 실행 권한 부여 중..."
chmod +x "$APP_NAME/Contents/MacOS/KICE Lynx" 2>/dev/null
chmod +x "app/python/bin/python3" 2>/dev/null

echo "3. 앱을 직접 실행합니다. 터미널 창에 에러가 뜨는지 확인해 주세요..."
# 앱의 백그라운드 실행을 위해 'open' 대신 직접 파이썬을 호출합니다.
export OFFLINE_MODE=1
./app/python/bin/python3 ./app/launcher.py

echo ""
echo "✅ 완료되었습니다! 이제부터는 앱을 바로 실행하셔도 됩니다."
sleep 2
exit 0
