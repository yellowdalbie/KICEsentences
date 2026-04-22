#!/bin/bash
# THINK LYNX PM2 배포 스크립트 (Ubuntu)

echo "--- [THINK LYNX 배포 시작] ---"

# 의존성 설치 (필요시)
if [ -f "requirements_server.txt" ]; then
    echo "의존성 확인 및 설치 중..."
    pip3 install -r requirements_server.txt
fi

# PM2 설치 확인
if ! command -v pm2 &> /dev/null; then
    echo "PM2가 설치되어 있지 않습니다. 'npm install -g pm2'로 설치해주세요."
    exit 1
fi

# 서비스 실행/재시작
echo "PM2 서비스를 시작/재시작합니다..."
pm2 start ecosystem.config.js

# 상태 확인
pm2 list

echo "--- [배포 완료] ---"
echo "대시보드: http://<서버IP>:5050"
echo "랜딩 페이지: http://<서버IP>:8181"
echo "로그 확인: pm2 logs"
