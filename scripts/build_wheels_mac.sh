#!/bin/bash
# ============================================================
# KICE Lynx — Mac wheels 빌드 스크립트
#
# [실행 방법]
#   Apple Silicon Mac: bash scripts/build_wheels_mac.sh
#   Intel Mac:         bash scripts/build_wheels_mac.sh
#
# 아키텍처를 자동 감지해서 wheels_mac-arm64/ 또는 wheels_mac-x86/ 생성
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# 아키텍처 감지
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
  PLATFORM="mac-arm64"
else
  PLATFORM="mac-x86"
fi

WHEELS_DIR="$SCRIPT_DIR/wheels_$PLATFORM"
REQ_FILE="$SCRIPT_DIR/requirements_dist.txt"

echo "================================================"
echo " KICE Lynx wheels 빌드"
echo " 플랫폼: $PLATFORM ($ARCH)"
echo " 출력:   $WHEELS_DIR"
echo "================================================"

# 기존 wheels 정리
if [ -d "$WHEELS_DIR" ]; then
  echo "기존 $WHEELS_DIR 삭제 중..."
  rm -rf "$WHEELS_DIR"
fi
mkdir -p "$WHEELS_DIR"

# Python 버전 확인
PY=$(python3 --version 2>&1)
echo "사용 Python: $PY"

# pip 최신화
python3 -m pip install --upgrade pip -q

# wheels 다운로드 (바이너리 우선)
echo ""
echo "패키지 다운로드 중..."
python3 -m pip download \
  -r "$REQ_FILE" \
  -d "$WHEELS_DIR" \
  --prefer-binary \
  2>&1

echo ""
echo "================================================"
echo " 완료: $(ls $WHEELS_DIR | wc -l | tr -d ' ')개 파일"
ls "$WHEELS_DIR"
echo "================================================"
echo ""
echo "다음 단계: python3 build_dist.py --platform $PLATFORM"
