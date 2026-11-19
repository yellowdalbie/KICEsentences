---
description: DB 재빌드 → 벡터 재빌드 → Vocab 재빌드 → 원격 서버(Ubuntu) git pull 및 PM2 재시작 (GitHub 푸시 제외)
---

# KICE Lynx 원격 배포 스킬 (GitHub 푸시 제외)

이 스킬은 해설 파일 수정 후 **로컬 DB/벡터/Vocab 재빌드 → 원격 서버 git pull → PM2 재시작**을 한 번에 처리합니다.
GitHub 푸시는 포함되지 않으므로, 이 스킬 실행 전에 이미 `git push`가 완료된 상태여야 합니다.

> **원격 서버 정보**
> - 주소: `ubuntu@146.56.118.155` (OCI A1 `lynx-a1`, aarch64, 예약 IP / 사설 10.0.0.138, 2026-11 이전)
> - SSH 키: `/Users/home/Downloads/ssh-key-2026-02-03.key`
> - 서버 포트: **8182** (`127.0.0.1` 루프백 전용, nginx `thinklynx.conf` 가 프록시 / PM2 앱 이름: `think-lynx-dashboard`)
> - 같은 서버에 DMGrade(포트 5001, nginx `grade-check.conf`)도 운영 중 — 재시작은 반드시 `think-lynx-dashboard`/`ecosystem.config.js` 대상으로만
> - Python 패키지는 `pip install --user` 로 설치됨 (sudo pip 금지)
> - 원격 프로젝트 경로: `/home/ubuntu/KICEsentences`
> - 로컬 프로젝트 경로: `/Users/home/vaults/projects/KICEsentences`

// turbo-all

## Step 1: 로컬 DB 재빌드

```bash
cd /Users/home/vaults/projects/KICEsentences
venv/bin/python build_db.py
```

- `kice_database.sqlite` 전체 재생성 (Sol/ 디렉토리 전체 파싱)
- 완료 후 `Total Steps extracted` 수 확인

## Step 2: 로컬 벡터 인덱스 재생성

```bash
cd /Users/home/vaults/projects/KICEsentences
/usr/bin/python3 build_vectors.py   # venv torch 깨짐 → 시스템 Python
```

- 완료 메시지: `완료! 저장된 벡터 수: N, 차원: 1024`
- `kice_step_vectors.npz` 업데이트 확인

## Step 3: 로컬 Vocab 재빌드

```bash
cd /Users/home/vaults/projects/KICEsentences
/usr/bin/python3 build_query_vocab.py
```

- `kice_query_vocab.npz` 재생성 (BGE-m3-ko 모델 사용, 수 분 소요)
- 완료 메시지: `[OfflineQueryEngine] 로드 완료: 어휘 N개 / Step M개 / Top-100`
- **반드시 Step 2 직후 실행** — 벡터와 Vocab의 스텝 수가 일치해야 검색 오류 없음
- 서버는 sentence_transformers 미설치이므로 반드시 로컬에서 빌드 후 git push로 배포

## Step 4: 원격 서버 git pull

```bash
ssh -i /Users/home/Downloads/ssh-key-2026-02-03.key -o StrictHostKeyChecking=no ubuntu@146.56.118.155 "cd /home/ubuntu/KICEsentences && git pull origin main 2>&1"
```

- Fast-forward 메시지 및 변경 파일 목록 확인

## Step 5: PM2 서버 재시작 및 상태 확인

```bash
ssh -i /Users/home/Downloads/ssh-key-2026-02-03.key -o StrictHostKeyChecking=no ubuntu@146.56.118.155 "cd /home/ubuntu/KICEsentences && pm2 restart ecosystem.config.js --update-env && sleep 2 && pm2 status think-lynx-dashboard"
```

- `--update-env` 플래그 필수: 없으면 PM2가 캐싱된 이전 환경변수를 유지함
- `think-lynx-dashboard` 상태가 `online`인지 확인

## Step 6: 포트 8182 응답 확인

```bash
ssh -i /Users/home/Downloads/ssh-key-2026-02-03.key -o StrictHostKeyChecking=no ubuntu@146.56.118.155 "for i in {1..20}; do curl -s http://127.0.0.1:8182 > /dev/null && echo 'SUCCESS: Port 8182 is up!' && exit 0 || echo \"Attempt \$i: waiting...\"; sleep 2; done; echo FAILED"
```

- `SUCCESS: Port 8182 is up!` 메시지 확인 시 배포 완료
- `FAILED` 출력 시 `pm2 logs think-lynx-dashboard`로 에러 확인 필요
