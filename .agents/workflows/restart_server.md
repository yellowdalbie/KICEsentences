---
description: 최적의 로컬 서버 재시작 방법 (재시작 후 안전 대기)
---

KICE LYNX 파이썬 서버(`dashboard.py`)는 AI 문장 임베딩 모델(SentenceTransformers)과 수많은 벡터 데이터를 메모리에 초기 적재하는 단계가 필요하여 부팅에 최소 10~20초 이상이 소요됩니다.
이 때문에 `python3 dashboard.py` 명령어 직후 브라우저를 바로 새로고침하면 서버 포트(5050)가 아직 열리지 않아 `Connection refused(연결 거부)` 오류가 발생하게 됩니다.

아래 명령어는 문제의 원인을 제거한 **최적의 자동화 스크립트**입니다. 기존 서버를 안전하게 종료하고 재실행한 뒤, 단순히 기다리는 것이 아니라 URL 핑(ping) 테스트를 통해 실제로 5050 포트에 데이터가 서빙될 때까지 모니터링하다가 성공 신호를 보내 줍니다.

// turbo-all

```bash
echo "▶ 1. 기존 dashboard.py 프로세스를 모두 종료합니다..."
pkill -f dashboard.py || true
sleep 2

echo "▶ 2. 백그라운드에서 로컬 서버를 재시작합니다 (로그는 server_runtime.log에 기록)..."
nohup python3 dashboard.py > server_runtime.log 2>&1 &

echo "▶ 3. AI 언어 모델과 벡터 데이터를 메모리에 적재 중입니다. 잠시만 기다려 주세요 (통상 10~30초 소요)..."
for i in {1..40}; do
    # curl로 접속 테스트 시도
    if curl -s http://127.0.0.1:5050 > /dev/null; then
        echo "✅ 완료! 포트 5050이 열리고 웹 서버가 성공적으로 응답합니다."
        echo "👉 [이제 브라우저 창을 새로고침 하시면 사이트에 정상 접속됩니다!]"
        exit 0
    fi
    sleep 1
done

echo "⚠️ 에러: 40초 내에 서버가 시작되지 못했습니다. server_runtime.log 파일을 열어 파이썬 에러 로그를 점검해 보세요."
exit 1
```
