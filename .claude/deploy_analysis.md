# 배포 전 점검 분석 리포트 (2026-03-02)

## 아키텍처 개요
- 백엔드: Flask (Python 3)
- DB: SQLite (kice_database.sqlite)
- 벡터: NumPy NPZ (kice_step_vectors.npz, ~500MB)
- AI 모델: dragonkue/BGE-m3-ko (Hugging Face, ~500MB, 런타임 필요)
- 수식: KaTeX (CDN 의존)
- 폰트: Paperlogy (CDN 의존, 9개 woff2)

## 🔴 즉시 처리 필요
1. `admin.key` - GitHub 제외 필수 (.gitignore 확인)
2. `*.sqlite`, `*.npz` - GitHub 용량 초과, 제외 필수
3. HTTPS 미설정 - admin.key가 URL 파라미터로 평문 노출됨
4. Flask 개발 서버 직접 사용 - 프로덕션은 Gunicorn + Nginx 필요

## 🟠 온라인 배포 (Oracle Cloud)
- Oracle Cloud 보안 그룹: 80, 443만 열기 (5050 외부 차단)
- Nginx → Gunicorn → Flask 구조 필요
- BGE-m3-ko 모델 다운로드 가능 여부 확인 (방화벽)
- Systemd 서비스 등록 (재부팅 자동 시작)
- 대용량 파일 (썸네일 1000+개) 업로드 전략: rsync 권장

## 🟠 오프라인 패키징
- KaTeX CDN → 로컬 파일로 교체 (templates/index.html)
- Paperlogy CDN → 로컬 woff2 파일로 교체 (static/style.css)
- BGE-m3-ko 모델 캐시를 패키지에 포함 (~/.cache/huggingface/hub/)
- pip 오프라인 wheels 준비

## 주요 CDN 참조
- KaTeX: https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/
- Paperlogy: https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/

## API 엔드포인트 (인증 없음 - 주의)
- /api/search (AI 벡터 검색)
- /api/search_expression (기출표현 검색)
- /api/report_error (오류 제보 - XSS 위험)
- /admin (admin.key 인증)

## 파일 크기 예상
- kice_database.sqlite: 50~100MB
- kice_step_vectors.npz: ~500MB
- BGE-m3-ko 모델: ~500MB
- static/thumbnails/: ~500MB (1000+ PNG)
- Sol/ 디렉토리: ~100MB

## 보안 이슈
- admin.key 평문 저장 + URL 파라미터 전달 (HTTPS 필수)
- 오류 제보 자유 텍스트 입력 (XSS 가능성, admin.html에서 escHtml()로 방어 중)
- CORS 미설정 (Flask 기본값)
- Rate limiting 없음
