# KICE 수능 대시보드 — 오프라인 로컬 패키징 절차서

**작성일**: 2026-03-02
**최종 수정**: 2026-03-02 (오프라인 전용 기능 제거 반영)
**대상**: 기술 비전문가도 따라할 수 있도록 작성
**적용 환경**: macOS 패키지, Windows 패키지 (내용은 동일, 시작 방법만 다름)

> ⚠️ **오프라인 버전 전용 특이사항**
> 오프라인 패키지는 `OFFLINE_MODE=1` 환경 변수를 설정하여 실행합니다.
> 이 모드에서는 **오류 제보 기능**과 **관리자 패널**이 완전히 비활성화됩니다.
> - UI에서 오류 제보 아이콘·패널이 렌더링되지 않음 (templates/index.html Jinja2 조건부 처리)
> - `/api/report_error`, `/api/step_reports`, `/admin`, `/api/admin/*` 엔드포인트 → 404 반환
> - `admin.key`, `templates/admin.html` 파일은 패키지에 포함하지 않음

---

## 이 절차서를 읽기 전에: 전체 구조 이해

### 왜 Mac용과 Windows용이 "거의 같지만 약간 다른가"

이 프로그램은 Python으로 만들어진 웹 서버입니다. 브라우저가 화면을 보여주고, 뒤에서 Python이 데이터를 처리합니다. Python은 Mac과 Windows 어디서나 동작하므로 **핵심 파일은 동일**합니다.

다른 점은 딱 두 가지입니다:
- **시작 스크립트**: Mac은 `.sh` 파일, Windows는 `.bat` 파일 (운영체제가 읽는 형식이 다름)
- **명령어 문법**: Mac은 `python3`, Windows는 `python` (설치 방식 차이)

따라서 **하나의 공통 패키지 폴더**를 만들고, 시작 스크립트만 각 OS용으로 따로 넣으면 됩니다.

### 왜 인터넷 없이 실행하려면 준비가 필요한가

현재 프로그램은 실행 시 두 가지를 인터넷에서 가져옵니다:
1. **KaTeX** (수식 렌더링 라이브러리): 수학 기호 표시용
2. **Paperlogy 폰트** (9개 폰트 파일): 화면에 표시되는 글꼴

이것들이 없으면 수식이 깨지고 글꼴이 이상하게 보입니다. 인터넷 없이 쓰려면 이 파일들을 미리 다운로드해서 패키지 안에 넣어야 합니다.

그리고 AI 검색 기능에 사용하는 한국어 언어 모델(약 500MB)도 인터넷에서 자동으로 다운로드되는데, 이것도 미리 포함시켜야 합니다.

---

## 준비물 체크리스트

이 절차는 **현재 Mac에서** 진행합니다. 인터넷 연결이 필요합니다.

- [ ] 현재 Mac에서 `python3 dashboard.py`가 정상 실행되는 상태
- [ ] 인터넷 연결
- [ ] 저장 공간 여유: 최소 3GB (패키지 조립용)

---

## 1단계: 패키지용 작업 폴더 만들기

**왜 필요한가**: 기존 개발 폴더와 배포용 폴더를 분리해야 합니다. 배포용에는 불필요한 스크립트, 임시 파일, 개발 도구가 들어가면 안 됩니다.

터미널을 열고 아래 명령어를 실행합니다:

```bash
# 바탕화면에 패키지 작업 폴더 만들기
mkdir -p ~/Desktop/KICE_Package/static/katex
mkdir -p ~/Desktop/KICE_Package/static/fonts
mkdir -p ~/Desktop/KICE_Package/hf_cache/hub
```

이렇게 하면 바탕화면에 `KICE_Package` 폴더가 생기고, 그 안에 필요한 하위 폴더들이 만들어집니다.

---

## 2단계: KaTeX 로컬 파일 다운로드

**왜 필요한가**: `templates/index.html`이 KaTeX를 외부 서버(cdn.jsdelivr.net)에서 불러옵니다. 인터넷이 없으면 수식이 전혀 표시되지 않습니다. KaTeX 전체를 로컬에 저장해두면 인터넷 없이도 수식이 정상 표시됩니다.

```bash
# KaTeX 0.16.8 전체 패키지 다운로드
cd ~/Desktop/KICE_Package/static/katex
curl -L https://github.com/KaTeX/KaTeX/releases/download/v0.16.8/katex.zip -o katex.zip

# 압축 해제
unzip katex.zip
# 압축 해제 후 생긴 katex/ 폴더 안의 내용물을 현재 위치로 이동
mv katex/* .
rmdir katex
rm katex.zip
```

완료 후 `~/Desktop/KICE_Package/static/katex/` 안에 다음 파일들이 있어야 합니다:
- `katex.min.css`
- `katex.min.js`
- `contrib/` (폴더)
- `fonts/` (폴더, KaTeX 자체 수식 폰트들)

---

## 3단계: Paperlogy 폰트 로컬 다운로드

**왜 필요한가**: `static/style.css`가 Paperlogy 폰트 9개를 외부 서버에서 불러옵니다. 인터넷이 없으면 폰트가 시스템 기본 폰트로 대체되어 디자인이 달라 보입니다.

```bash
cd ~/Desktop/KICE_Package/static/fonts

# 폰트 파일 9개를 하나씩 다운로드
curl -O "https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/Paperlogy-1Thin.woff2"
curl -O "https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/Paperlogy-2ExtraLight.woff2"
curl -O "https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/Paperlogy-3Light.woff2"
curl -O "https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/Paperlogy-4Regular.woff2"
curl -O "https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/Paperlogy-5Medium.woff2"
curl -O "https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/Paperlogy-6SemiBold.woff2"
curl -O "https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/Paperlogy-7Bold.woff2"
curl -O "https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/Paperlogy-8ExtraBold.woff2"
curl -O "https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/Paperlogy-9Black.woff2"
```

완료 후 `fonts/` 폴더에 `.woff2` 파일 9개가 있어야 합니다.

---

## 4단계: AI 언어 모델 캐시 복사

**왜 필요한가**: AI 검색 기능(`/api/search`)은 `dragonkue/BGE-m3-ko`라는 한국어 언어 모델을 사용합니다. 이 모델은 프로그램 첫 실행 시 Hugging Face 서버에서 약 500MB를 자동으로 다운로드합니다. 오프라인 환경에서는 이 다운로드가 불가능하므로, 이미 현재 Mac에 다운로드된 모델 파일을 패키지에 포함시켜야 합니다.

```bash
# 현재 Mac에 캐시된 모델 위치 확인
ls ~/.cache/huggingface/hub/ | grep dragonkue
```

`models--dragonkue--BGE-m3-ko` 폴더가 보이면 정상입니다. 없다면 `python3 build_vectors.py`를 한 번 실행해서 모델을 다운로드받아야 합니다.

```bash
# 모델 캐시를 패키지에 복사 (약 500MB, 1~2분 소요)
cp -r ~/.cache/huggingface/hub/models--dragonkue--BGE-m3-ko \
      ~/Desktop/KICE_Package/hf_cache/hub/
```

---

## 5단계: pip 패키지 오프라인 다운로드

**왜 필요한가**: 패키지를 받는 사람이 인터넷 없이 Python 라이브러리를 설치해야 합니다. `pip download`는 실제 설치하지 않고 설치 파일만 내려받아 둡니다. 나중에 이 파일로 인터넷 없이 설치할 수 있습니다.

```bash
cd ~/Desktop/KICE_Package
mkdir offline_wheels

# 현재 프로젝트 requirements.txt를 기준으로 다운로드
pip download -r /Users/home/vaults/projects/KICEsentences/requirements.txt \
             -d ./offline_wheels/
```

완료 후 `offline_wheels/` 안에 `.whl` 파일들이 여러 개 생깁니다.

**주의**: `pip download`는 현재 Mac 운영체제에 맞는 파일을 받습니다. Windows용은 다른 파일이 필요할 수 있습니다. 이 문제의 해결법은 9단계에서 설명합니다.

---

## 6단계: 프로젝트 핵심 파일 복사

**왜 필요한가**: 프로그램 실행에 꼭 필요한 파일들을 패키지 폴더로 옮깁니다. 개발용 스크립트(`build_db.py`, `build_vectors.py`, `fix_*.py` 등)는 배포용에서 불필요하므로 제외합니다.

```bash
# 프로젝트 루트로 이동
SRC=/Users/home/vaults/projects/KICEsentences
DST=~/Desktop/KICE_Package

# 핵심 파이썬 파일
cp "$SRC/dashboard.py"       "$DST/"
cp "$SRC/requirements.txt"   "$DST/"
cp "$SRC/trigger_mapping.json" "$DST/"
cp "$SRC/concepts.json"      "$DST/" 2>/dev/null || true

# ⚠️ 업데이트 원클릭 도구를 지원하려면 아래 두 파일도 포함 (13단계 참고)
cp "$SRC/build_db.py"        "$DST/"
cp "$SRC/build_vectors.py"   "$DST/"

# 데이터베이스와 벡터 (미리 빌드된 것 복사)
cp "$SRC/kice_database.sqlite"   "$DST/"
cp "$SRC/kice_step_vectors.npz"  "$DST/"   # 약 500MB, 수 분 소요

# 정적 파일 (thumbnails 포함, 대용량)
cp -r "$SRC/static/style.css"   "$DST/static/"
cp -r "$SRC/static/cart.js"     "$DST/static/"
cp -r "$SRC/static/logo.png"    "$DST/static/"
cp -r "$SRC/static/thumbnails"  "$DST/static/"   # 약 500MB

# 템플릿 (admin.html은 오프라인 버전에 포함하지 않음)
cp "$SRC/templates/index.html" "$DST/templates/"

# ⛔ 오프라인 버전에서 제외하는 파일
# admin.key   → 관리자 패널 사용 안 함
# templates/admin.html → 관리자 페이지 없음
# error_reports.jsonl  → 오류 제보 저장 파일 없음

# 해설 파일 전체
cp -r "$SRC/Sol"            "$DST/"
cp -r "$SRC/MD_Ref"         "$DST/"  2>/dev/null || true
cp -r "$SRC/PDF_Ref"        "$DST/"  2>/dev/null || true
```

---

## 7단계: CDN 참조를 로컬 경로로 수정

**왜 필요한가**: 현재 `index.html`과 `style.css`는 KaTeX와 Paperlogy를 외부 서버 주소(https://...)로 불러옵니다. 오프라인에서는 그 주소에 접근할 수 없으므로, 방금 다운로드한 로컬 파일을 가리키도록 주소를 바꿔야 합니다.

### index.html 수정

텍스트 에디터(VS Code, TextEdit 등)로 `~/Desktop/KICE_Package/templates/index.html`을 열고, 다음 3줄을 찾아서:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js"></script>
```

아래와 같이 바꿉니다:

```html
<link rel="stylesheet" href="/static/katex/katex.min.css">
<script defer src="/static/katex/katex.min.js"></script>
<script defer src="/static/katex/contrib/auto-render.min.js"></script>
```

### style.css 수정

`~/Desktop/KICE_Package/static/style.css`를 열고, 앞부분의 CDN 주소 9개를 찾아서:

```css
src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/Paperlogy-1Thin.woff2') format('woff2');
```

이런 형태의 줄들을 모두 찾아 다음과 같이 바꿉니다:

```css
src: url('/static/fonts/Paperlogy-1Thin.woff2') format('woff2');
```

9개 폰트 파일 이름:
1. `Paperlogy-1Thin.woff2`
2. `Paperlogy-2ExtraLight.woff2`
3. `Paperlogy-3Light.woff2`
4. `Paperlogy-4Regular.woff2`
5. `Paperlogy-5Medium.woff2`
6. `Paperlogy-6SemiBold.woff2`
7. `Paperlogy-7Bold.woff2`
8. `Paperlogy-8ExtraBold.woff2`
9. `Paperlogy-9Black.woff2`

전부 `https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/파일명` → `/static/fonts/파일명` 형태로 바꿉니다.

**터미널로 자동 변환하는 방법** (수동 편집이 번거로울 때):

```bash
# style.css: CDN URL → 로컬 경로 일괄 변환
sed -i '' \
  "s|url('https://cdn.jsdelivr.net/gh/projectnoonnu/2408-3@1.0/|url('/static/fonts/|g" \
  ~/Desktop/KICE_Package/static/style.css

# index.html: KaTeX CDN → 로컬 경로 변환
sed -i '' \
  's|https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/|/static/katex/|g' \
  ~/Desktop/KICE_Package/templates/index.html
```

---

## 8단계: macOS용 시작 스크립트 작성

**왜 필요한가**: 일반 사용자가 터미널 명령어를 외울 필요 없이 더블클릭 하나로 실행할 수 있게 합니다. 스크립트가 Python 패키지 설치, AI 모델 경로 설정, 서버 시작, 브라우저 열기를 자동으로 처리합니다.

`~/Desktop/KICE_Package/` 안에 `시작_Mac.command` 파일을 만듭니다:

```bash
cat > ~/Desktop/KICE_Package/시작_Mac.command << 'EOF'
#!/bin/bash
# KICE 수능 대시보드 - macOS 시작 스크립트

# 이 스크립트가 있는 폴더로 이동 (어디서 실행해도 경로가 맞게)
cd "$(dirname "$0")"

echo "==================================="
echo " KICE 수능 대시보드 시작 중..."
echo "==================================="

# Python 설치 확인
if ! command -v python3 &>/dev/null; then
    echo "[오류] Python 3가 설치되어 있지 않습니다."
    echo "https://www.python.org 에서 Python 3.10 이상을 설치해주세요."
    read -p "아무 키나 누르면 종료합니다..."
    exit 1
fi

# pip 패키지 설치 (처음 실행 시만 설치, 이미 있으면 스킵)
echo "[1/3] Python 패키지 확인 중..."
pip3 install --quiet --no-index --find-links=./offline_wheels/ -r requirements.txt 2>/dev/null || \
pip3 install --quiet -r requirements.txt

# AI 모델 경로 설정 (인터넷 없이 로컬 캐시 사용)
export HF_HOME="$(pwd)/hf_cache"
export TRANSFORMERS_OFFLINE=1

echo "[2/3] 서버 시작 중 (포트 5050)..."

# 이전에 실행 중인 프로세스 정리
lsof -ti :5050 | xargs kill -9 2>/dev/null || true
sleep 1

# 오프라인 모드 설정 (관리자 패널·오류 제보 비활성화)
export OFFLINE_MODE=1

# 백그라운드로 서버 시작
python3 dashboard.py &
SERVER_PID=$!

# 서버가 뜰 때까지 최대 30초 대기
echo "[3/3] 브라우저 열기 대기 중..."
for i in {1..15}; do
    sleep 2
    if curl -s http://localhost:5050 >/dev/null 2>&1; then
        echo ""
        echo "==================================="
        echo " 서버 시작 완료!"
        echo " 브라우저: http://localhost:5050"
        echo " 종료하려면 이 창을 닫으세요."
        echo "==================================="
        open http://localhost:5050
        wait $SERVER_PID
        exit 0
    fi
    echo "  대기 중... ($((i*2))초)"
done

echo "[오류] 서버 시작에 실패했습니다. dashboard.log를 확인해주세요."
read -p "아무 키나 누르면 종료합니다..."
EOF

# 실행 권한 부여 (macOS에서 스크립트를 실행 가능하게)
chmod +x ~/Desktop/KICE_Package/시작_Mac.command
```

---

## 9단계: Windows용 시작 스크립트 작성

**왜 필요한가**: Windows는 `.sh` 파일을 읽지 못하고 `.bat` 파일 문법이 전혀 다릅니다. Windows 사용자는 `.bat` 파일을 더블클릭하면 됩니다.

`~/Desktop/KICE_Package/` 안에 `시작_Windows.bat` 파일을 만듭니다:

```bash
cat > ~/Desktop/KICE_Package/시작_Windows.bat << 'EOF'
@echo off
chcp 65001 >nul
title KICE 수능 대시보드

REM 이 스크립트가 있는 폴더로 이동
cd /d "%~dp0"

echo ===================================
echo  KICE 수능 대시보드 시작 중...
echo ===================================

REM Python 설치 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Python이 설치되어 있지 않습니다.
    echo https://www.python.org 에서 Python 3.10 이상을 설치해주세요.
    echo 설치 시 "Add Python to PATH" 옵션을 반드시 체크하세요.
    pause
    exit /b 1
)

REM pip 패키지 설치
echo [1/3] Python 패키지 확인 중...
python -m pip install --quiet --no-index --find-links=offline_wheels -r requirements.txt 2>nul
if errorlevel 1 (
    python -m pip install --quiet -r requirements.txt
)

REM AI 모델 경로 설정
set HF_HOME=%~dp0hf_cache
set TRANSFORMERS_OFFLINE=1

REM 오프라인 모드 설정 (관리자 패널·오류 제보 비활성화)
set OFFLINE_MODE=1

REM 이전 프로세스 정리
echo [2/3] 이전 서버 프로세스 정리 중...
for /f "tokens=5" %%a in ('netstat -aon ^| find ":5050" ^| find "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

REM 서버 시작
echo [3/3] 서버 시작 중 (포트 5050)...
start /b python dashboard.py

REM 서버 대기
echo 브라우저 열기 대기 중...
timeout /t 8 /nobreak >nul

REM 브라우저 열기
start http://localhost:5050

echo.
echo ===================================
echo  서버가 실행 중입니다.
echo  브라우저: http://localhost:5050
echo  이 창을 닫으면 서버가 종료됩니다.
echo ===================================
pause
EOF
```

### Windows의 pip 패키지 문제 해결

**중요**: `pip download`는 현재 Mac(ARM 또는 Intel)에 맞는 파일을 받습니다. Windows용 파일이 다를 수 있습니다. 두 가지 방법이 있습니다:

**방법 A (권장)**: 첫 실행 시 인터넷으로 설치
- 위 `.bat` 파일이 이미 이 방법을 처리합니다: `offline_wheels`가 없으면 자동으로 인터넷에서 설치
- Windows 수신자가 처음 한 번만 인터넷에 연결하면 됩니다

**방법 B (완전 오프라인)**: Windows 머신에서 직접 wheels 다운로드
```bat
pip download -r requirements.txt -d offline_wheels_win --platform win_amd64 --only-binary=:all:
```
이 명령어는 Windows 64비트용 파일만 받습니다. Windows 머신이 있다면 거기서 실행하세요.

---

## 10단계: 최종 패키지 구조 확인

모든 파일이 제자리에 있는지 확인합니다:

```bash
# 폴더 구조 출력
find ~/Desktop/KICE_Package -maxdepth 2 -type d | sort
ls -lh ~/Desktop/KICE_Package/*.py
ls -lh ~/Desktop/KICE_Package/*.sqlite
ls -lh ~/Desktop/KICE_Package/*.npz
ls ~/Desktop/KICE_Package/static/katex/katex.min.js  # KaTeX 확인
ls ~/Desktop/KICE_Package/static/fonts/*.woff2        # 폰트 확인
ls ~/Desktop/KICE_Package/hf_cache/hub/              # 모델 캐시 확인
```

최종 폴더 구조:
```
KICE_Package/
├── 시작_Mac.command         ← macOS 시작 스크립트
├── 시작_Windows.bat         ← Windows 시작 스크립트
├── dashboard.py             ← 메인 프로그램
├── requirements.txt         ← 패키지 목록
├── kice_database.sqlite     ← 데이터베이스 (~100MB)
├── kice_step_vectors.npz    ← AI 벡터 (~500MB)
├── trigger_mapping.json     ← 트리거 매핑
├── concepts.json            ← 개념 데이터
├── offline_wheels/          ← pip 오프라인 패키지
├── hf_cache/
│   └── hub/
│       └── models--dragonkue--BGE-m3-ko/  ← AI 모델 (~500MB)
├── static/
│   ├── style.css            ← CDN 수정됨
│   ├── cart.js
│   ├── logo.png
│   ├── katex/               ← KaTeX 로컬 파일
│   ├── fonts/               ← Paperlogy 폰트 9개
│   └── thumbnails/          ← 문항 이미지 (~500MB)
├── templates/
│   ├── index.html           ← CDN 수정됨
│   └── admin.html
├── Sol/                     ← 해설 파일 전체
├── MD_Ref/                  ← 원본 문항
└── PDF_Ref/                 ← PDF 참조
```

---

## 11단계: macOS에서 테스트

```bash
# 패키지 폴더로 이동
cd ~/Desktop/KICE_Package

# 테스트 실행
export HF_HOME="$(pwd)/hf_cache"
export TRANSFORMERS_OFFLINE=1
export OFFLINE_MODE=1
python3 dashboard.py &

sleep 8
open http://localhost:5050
```

확인 사항:
- [ ] 메인 화면이 정상 표시되는가
- [ ] 수식(LaTeX)이 깨지지 않고 잘 보이는가
- [ ] 폰트가 이상하지 않은가
- [ ] 문항 검색이 작동하는가
- [ ] AI 검색(검색창에 개념 입력)이 작동하는가
- [ ] 썸네일 이미지가 보이는가

테스트 완료 후 서버 종료:
```bash
lsof -ti :5050 | xargs kill -9 2>/dev/null || true
```

---

## 12단계: 배포 압축

```bash
cd ~/Desktop

# macOS용 패키지 (tar.gz 형식)
tar -czf KICE_Dashboard_v1.0_Mac.tar.gz KICE_Package/

# 또는 zip 형식 (Windows 호환성 높음)
zip -r KICE_Dashboard_v1.0.zip KICE_Package/

# 파일 크기 확인
ls -lh KICE_Dashboard_v1.0.zip
```

압축 파일 크기는 약 1.5~2GB가 될 것입니다.

---

## Windows 수신자 설치 안내 (별도 문서로 제공)

Windows 사용자에게 전달할 간단한 안내문:

```
KICE 수능 대시보드 설치 방법 (Windows)

1. Python 설치
   - https://www.python.org/downloads/ 방문
   - "Download Python 3.12" 버튼 클릭
   - 설치 시 ⚠️ "Add Python to PATH" 체크박스 반드시 체크

2. 패키지 압축 해제
   - KICE_Dashboard_v1.0.zip 파일을 원하는 폴더에 압축 해제
   - (예: C:\KICE_Dashboard\)

3. 실행
   - 압축 해제된 폴더 안에서 "시작_Windows.bat" 더블클릭
   - 처음 실행 시 패키지 설치로 1~2분 소요 (인터넷 필요)
   - 브라우저가 자동으로 열립니다

4. 종료
   - 열려있는 명령창(검은 화면)을 닫으면 서버가 종료됩니다
```

---

## 13단계: 업데이트 원클릭 도구

### 전체 개념 이해

해설을 추가할 때마다 **배포받은 사람들에게 전체 패키지(2GB)를 다시 보내는 건 비효율적**입니다. 대신 "업데이트 패키지"라는 작은 폴더를 따로 만들어서 배포하고, 받는 사람이 클릭 한 번으로 적용할 수 있게 합니다.

업데이트 방식에는 두 가지가 있습니다:

| 구분 | 포함 파일 | 크기 | 사용자 처리 시간 |
|------|----------|------|----------------|
| **경량 업데이트** | 새 Sol 파일만 | 수 MB | 5~10분 (재빌드 자동 수행) |
| **전체 업데이트** | Sol + DB + 벡터 | 600MB+ | 즉시 (교체만) |

- **자주 업데이트할 때**: 경량 업데이트 (작고 빠름)
- **오랜만에 대량 추가 후**: 전체 업데이트 (큰 파일이지만 사용자 기기에서 재빌드 없음)

---

### 업데이트 패키지 구조

배포할 업데이트 패키지 폴더의 모습입니다:

```
KICE_업데이트_2026-06-01/      ← 이 폴더를 zip으로 압축해서 배포
├── 업데이트_Mac.command        ← Mac용 업데이트 실행 스크립트
├── 업데이트_Windows.bat        ← Windows용 업데이트 실행 스크립트
├── update_info.json            ← 업데이트 정보 (버전, 설명, 유형)
├── kice_database.sqlite        ← 전체 업데이트 시만 포함
├── kice_step_vectors.npz       ← 전체 업데이트 시만 포함
└── Sol/                        ← 새로 추가된 Sol 파일
    └── 2026/
        ├── 2026.6모_20.md
        └── ...
```

사용자는 이 zip을 받아서 압축 해제한 뒤, **KICE_Package 폴더 옆에** 놓고 스크립트를 실행합니다:

```
(바탕화면 등 아무 폴더나)
├── KICE_Package/                    ← 기존 설치된 패키지
└── KICE_업데이트_2026-06-01/        ← 압축 해제한 업데이트 폴더
    ├── 업데이트_Mac.command          ← 이걸 더블클릭
    └── ...
```

스크립트가 자동으로 `KICE_Package`를 찾아서 처리하므로 사용자는 위치만 신경 쓰면 됩니다.

---

### 개발자 측 작업 A: 개발 환경에서 해설 추가 후 빌드

```bash
cd /Users/home/vaults/projects/KICEsentences

# Sol/ 파일 추가 완료 후 실행
python3 build_db.py
python3 build_vectors.py

# 로컬 서버로 확인
```

---

### 개발자 측 작업 B: update_info.json 작성

업데이트 폴더 안에 아래 내용의 `update_info.json` 파일을 만듭니다:

```json
{
  "version": "2026-06-01",
  "description": "2026학년도 6월 모의고사 해설 전체 추가 (27문항)",
  "type": "sol_only",
  "date": "2026-06-01"
}
```

- `"type"`: `"sol_only"` 또는 `"full"` 중 선택
- `"description"`: 사용자에게 표시될 업데이트 설명

---

### 개발자 측 작업 C: 업데이트 스크립트 준비

아래 두 스크립트를 프로젝트 루트에 저장해두고 매번 업데이트 패키지에 복사합니다.

#### `업데이트_Mac.command` (macOS용)

```bash
#!/bin/bash
# KICE 수능 대시보드 - 업데이트 스크립트 (macOS)
cd "$(dirname "$0")"
UPDATE_DIR="$(pwd)"
PARENT_DIR="$(dirname "$UPDATE_DIR")"

echo "==================================="
echo " KICE 대시보드 업데이트"
echo "==================================="
echo ""

# ─── KICE_Package 자동 탐색 ──────────────────────────────
find_package() {
    if [ -f "$PARENT_DIR/KICE_Package/dashboard.py" ]; then
        echo "$PARENT_DIR/KICE_Package"; return
    fi
    if [ -f ~/Desktop/KICE_Package/dashboard.py ]; then
        echo ~/Desktop/KICE_Package; return
    fi
    if [ -f ~/Documents/KICE_Package/dashboard.py ]; then
        echo ~/Documents/KICE_Package; return
    fi
    echo ""
}

PACKAGE_DIR=$(find_package)

if [ -n "$PACKAGE_DIR" ]; then
    echo "설치된 패키지를 찾았습니다:"
    echo "  $PACKAGE_DIR"
    read -p "이 위치가 맞습니까? (y/n): " CONFIRM
    [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]] && PACKAGE_DIR=""
fi

if [ -z "$PACKAGE_DIR" ]; then
    echo ""
    echo "KICE_Package 폴더의 전체 경로를 직접 입력해주세요."
    echo "(예: /Users/홍길동/Desktop/KICE_Package)"
    read -p "> " PACKAGE_DIR
    PACKAGE_DIR="${PACKAGE_DIR/#\~/$HOME}"
fi

if [ ! -f "$PACKAGE_DIR/dashboard.py" ]; then
    echo ""
    echo "[오류] 올바른 KICE_Package 폴더를 찾을 수 없습니다."
    echo "  확인한 경로: $PACKAGE_DIR"
    read -p "아무 키나 누르면 종료합니다..."
    exit 1
fi

echo ""
echo "패키지 위치: $PACKAGE_DIR"
echo ""

# ─── 업데이트 정보 표시 ──────────────────────────────────
if [ -f "update_info.json" ]; then
    echo "[ 업데이트 내용 ]"
    python3 -c "
import json
with open('update_info.json') as f:
    info = json.load(f)
print(f'  버전: {info.get(\"version\", \"?\")}')
print(f'  설명: {info.get(\"description\", \"\")}')
print(f'  유형: {\"전체 업데이트\" if info.get(\"type\")==\"full\" else \"경량 업데이트 (재빌드 필요)\"}')
"
    echo ""
fi

UPDATE_TYPE=$(python3 -c "
import json, sys
try:
    info = json.load(open('update_info.json'))
    print(info.get('type', 'sol_only'))
except:
    print('sol_only')
" 2>/dev/null || echo "sol_only")

read -p "업데이트를 시작합니다. 계속하시겠습니까? (y/n): " GO
[[ "$GO" != "y" && "$GO" != "Y" ]] && exit 0

echo ""

# ─── 1. 서버 종료 ─────────────────────────────────────────
echo "[1/4] 실행 중인 서버 종료..."
lsof -ti :5050 | xargs kill -9 2>/dev/null || true
sleep 2

# ─── 2. Sol 파일 복사 ─────────────────────────────────────
if [ -d "Sol" ]; then
    echo "[2/4] 새 해설 파일 복사 중..."
    rsync -av Sol/ "$PACKAGE_DIR/Sol/"
else
    echo "[2/4] Sol 파일 없음 (건너뜀)"
fi

# ─── 3. DB/벡터 처리 ──────────────────────────────────────
if [ "$UPDATE_TYPE" = "full" ]; then
    echo "[3/4] 데이터베이스 및 벡터 교체 중..."
    [ -f "kice_database.sqlite" ]  && cp kice_database.sqlite  "$PACKAGE_DIR/"
    [ -f "kice_step_vectors.npz" ] && cp kice_step_vectors.npz "$PACKAGE_DIR/"
    echo "      교체 완료."
else
    echo "[3/4] 데이터베이스 재빌드 중 (5~10분 소요, 창을 닫지 마세요)..."
    cd "$PACKAGE_DIR"
    export HF_HOME="$(pwd)/hf_cache"
    export TRANSFORMERS_OFFLINE=1
    python3 build_db.py
    echo "      DB 완료. 벡터 빌드 중..."
    python3 build_vectors.py
    cd "$UPDATE_DIR"
fi

# ─── 4. 완료 ──────────────────────────────────────────────
echo ""
echo "==================================="
echo " 업데이트 완료!"
echo " 이제 시작_Mac.command를 실행해서"
echo " 대시보드를 다시 열어주세요."
echo "==================================="
read -p "아무 키나 누르면 종료합니다..."
```

이 파일에 실행 권한을 부여합니다:
```bash
chmod +x 업데이트_Mac.command
```

---

#### `업데이트_Windows.bat` (Windows용)

```bat
@echo off
chcp 65001 >nul
title KICE 업데이트

cd /d "%~dp0"
set UPDATE_DIR=%~dp0
for %%I in ("%UPDATE_DIR:~0,-1%\..") do set PARENT_DIR=%%~fI

echo ===================================
echo  KICE 대시보드 업데이트
echo ===================================
echo.

REM ─── KICE_Package 자동 탐색 ─────────────────────────────
set PACKAGE_DIR=

if exist "%PARENT_DIR%\KICE_Package\dashboard.py" (
    set PACKAGE_DIR=%PARENT_DIR%\KICE_Package
    goto found_candidate
)
if exist "%USERPROFILE%\Desktop\KICE_Package\dashboard.py" (
    set PACKAGE_DIR=%USERPROFILE%\Desktop\KICE_Package
    goto found_candidate
)
if exist "%USERPROFILE%\Documents\KICE_Package\dashboard.py" (
    set PACKAGE_DIR=%USERPROFILE%\Documents\KICE_Package
    goto found_candidate
)
goto ask_path

:found_candidate
echo 설치된 패키지를 찾았습니다:
echo   %PACKAGE_DIR%
set /p CONFIRM="이 위치가 맞습니까? (y/n): "
if /i "%CONFIRM%"=="y" goto confirmed
set PACKAGE_DIR=

:ask_path
echo.
echo KICE_Package 폴더의 전체 경로를 입력해주세요.
echo (예: C:\Users\홍길동\Desktop\KICE_Package)
set /p PACKAGE_DIR="> "

:confirmed
if not exist "%PACKAGE_DIR%\dashboard.py" (
    echo.
    echo [오류] 올바른 KICE_Package 폴더를 찾을 수 없습니다.
    pause
    exit /b 1
)

echo.
echo 패키지 위치: %PACKAGE_DIR%
echo.

REM ─── 업데이트 정보 표시 ─────────────────────────────────
if exist "update_info.json" (
    echo [ 업데이트 내용 ]
    python -c "import json; info=json.load(open('update_info.json')); print(f'  버전: {info.get(\"version\",\"?\")}'); print(f'  설명: {info.get(\"description\",\"\")}'); print(f'  유형: {\"전체\" if info.get(\"type\")==\"full\" else \"경량 (재빌드 필요)\"}')"
    echo.
)

REM 업데이트 유형 확인
set UPDATE_TYPE=sol_only
for /f "usebackq tokens=*" %%a in (`python -c "import json; info=json.load(open('update_info.json')); print(info.get('type','sol_only'))" 2^>nul`) do set UPDATE_TYPE=%%a

set /p GO="업데이트를 시작합니다. 계속하시겠습니까? (y/n): "
if /i not "%GO%"=="y" exit /b 0

echo.

REM ─── 1. 서버 종료 ─────────────────────────────────────
echo [1/4] 실행 중인 서버 종료...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| find ":5050" ^| find "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 3 /nobreak >nul

REM ─── 2. Sol 파일 복사 ────────────────────────────────
if exist "Sol\" (
    echo [2/4] 새 해설 파일 복사 중...
    xcopy /E /Y /I Sol "%PACKAGE_DIR%\Sol"
) else (
    echo [2/4] Sol 파일 없음 ^(건너뜀^)
)

REM ─── 3. DB/벡터 처리 ─────────────────────────────────
if "%UPDATE_TYPE%"=="full" (
    echo [3/4] 데이터베이스 및 벡터 교체 중...
    if exist "kice_database.sqlite"  copy /Y kice_database.sqlite  "%PACKAGE_DIR%\"
    if exist "kice_step_vectors.npz" copy /Y kice_step_vectors.npz "%PACKAGE_DIR%\"
    echo       교체 완료.
) else (
    echo [3/4] 데이터베이스 재빌드 중 ^(5~10분 소요, 창 닫지 마세요^)...
    cd /d "%PACKAGE_DIR%"
    set HF_HOME=%PACKAGE_DIR%\hf_cache
    set TRANSFORMERS_OFFLINE=1
    python build_db.py
    echo       DB 완료. 벡터 빌드 중...
    python build_vectors.py
    cd /d "%UPDATE_DIR%"
)

REM ─── 4. 완료 ─────────────────────────────────────────
echo.
echo ===================================
echo  업데이트 완료!
echo  이제 시작_Windows.bat를 실행해서
echo  대시보드를 다시 열어주세요.
echo ===================================
pause
```

---

### 개발자 측 작업 D: 업데이트 패키지 조립 및 압축

매번 손으로 하지 않도록 조립 스크립트를 만들어둡니다. 프로젝트 루트에 `make_update.sh` 로 저장하세요:

```bash
#!/bin/bash
# 사용법: bash make_update.sh 2026-06-01 sol_only
#         bash make_update.sh 2026-06-01 full

VERSION="${1:-$(date +%Y-%m-%d)}"
TYPE="${2:-sol_only}"

SRC=/Users/home/vaults/projects/KICEsentences
PKG_NAME="KICE_업데이트_$VERSION"
PKG_DIR=~/Desktop/"$PKG_NAME"

echo "=== 업데이트 패키지 생성 ==="
echo "버전: $VERSION | 유형: $TYPE"
echo ""

# 1. 개발 환경 재빌드
echo "[1/4] DB 재빌드..."
cd "$SRC" && python3 build_db.py
echo "[2/4] 벡터 재빌드..."
python3 build_vectors.py

# 2. 업데이트 폴더 구성
echo "[3/4] 업데이트 패키지 구성..."
rm -rf "$PKG_DIR" && mkdir -p "$PKG_DIR/Sol"

# update_info.json 작성 (설명은 직접 수정)
cat > "$PKG_DIR/update_info.json" << JSON
{
  "version": "$VERSION",
  "description": "해설 업데이트",
  "type": "$TYPE",
  "date": "$(date +%Y-%m-%d)"
}
JSON

# 업데이트 스크립트 복사
cp "$SRC/업데이트_Mac.command" "$PKG_DIR/"
cp "$SRC/업데이트_Windows.bat"  "$PKG_DIR/"
chmod +x "$PKG_DIR/업데이트_Mac.command"

# Sol 파일 전체 동기화
rsync -av --delete "$SRC/Sol/" "$PKG_DIR/Sol/"

# 전체 업데이트면 DB/벡터도 포함
if [ "$TYPE" = "full" ]; then
    echo "      DB/벡터 복사 중 (대용량)..."
    cp "$SRC/kice_database.sqlite"  "$PKG_DIR/"
    cp "$SRC/kice_step_vectors.npz" "$PKG_DIR/"
fi

# 4. 압축
echo "[4/4] 압축 중..."
cd ~/Desktop
zip -r "$PKG_NAME.zip" "$PKG_NAME/"
rm -rf "$PKG_DIR"

echo ""
echo "완료: ~/Desktop/$PKG_NAME.zip"
ls -lh ~/Desktop/"$PKG_NAME.zip"
```

실행 방법:
```bash
# 경량 업데이트 (Sol만, 작은 파일)
bash make_update.sh 2026-06-01 sol_only

# 전체 업데이트 (DB+벡터 포함, 대용량)
bash make_update.sh 2026-06-01 full
```

---

### 사용자(수신자) 측 절차 — 안내문

배포할 때 아래 내용을 함께 보내세요:

```
[ KICE 업데이트 적용 방법 ]

1. 받은 zip 파일을 압축 해제합니다.
   → "KICE_업데이트_2026-06-01" 폴더가 생깁니다.

2. 이 폴더를 KICE_Package 폴더와 같은 위치에 놓습니다.
   예) 바탕화면/
       ├── KICE_Package/         ← 기존 설치
       └── KICE_업데이트_2026-06-01/  ← 여기 놓기

3. "KICE_업데이트_2026-06-01" 폴더 안에서
   • Mac: "업데이트_Mac.command" 더블클릭
   • Windows: "업데이트_Windows.bat" 더블클릭

4. 완료 메시지가 나오면 평소처럼 시작 스크립트로 실행합니다.

※ 경량 업데이트의 경우 재빌드 시간이 5~10분 소요됩니다.
   창을 닫지 말고 기다려주세요.
```

---

### 버전 관리 팁

패키지와 업데이트 파일명에 날짜를 붙여서 관리합니다:

```
KICE_Dashboard_2026-03-02.zip      ← 초기 배포
KICE_업데이트_2026-06-01.zip       ← 6월 모의고사 해설 추가
KICE_업데이트_2026-09-01.zip       ← 9월 모의고사 해설 추가
KICE_Dashboard_2026-11-01.zip      ← 대규모 추가 후 전체 재배포
```

**전체 재배포(KICE_Dashboard) 시기**: 초기 패키지 대비 Sol 파일이 2배 이상 늘었거나, 새 사용자를 받을 때 과거 업데이트를 누적 적용하기 번거로울 때입니다.

---

## 부록: 자주 묻는 문제

### "AI 검색이 안 돼요"
- `hf_cache/hub/models--dragonkue--BGE-m3-ko/` 폴더가 있는지 확인
- `TRANSFORMERS_OFFLINE=1` 환경 변수가 설정되어 있는지 확인

### "수식이 깨져 보여요"
- `static/katex/katex.min.js` 파일이 있는지 확인
- `templates/index.html`에서 CDN URL이 `/static/katex/...`로 바뀌었는지 확인

### "폰트가 이상해요"
- `static/fonts/` 안에 `.woff2` 파일 9개가 있는지 확인
- `static/style.css`에서 CDN URL이 `/static/fonts/...`로 바뀌었는지 확인

### "포트 5050이 이미 사용 중이에요"
- macOS: `lsof -ti :5050 | xargs kill -9`
- Windows: 작업 관리자에서 `python.exe` 프로세스 종료
