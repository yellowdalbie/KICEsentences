# 신규 시험지 반영 절차서 (분할 → 썸네일 → 원문 → 해설 → 재빌드 → 배포)

> **최종 수정**: 2026-11-19 (2027수능 반영 시 실제 수행 절차 기준)
> **대상 경로**: `/Users/home/vaults/projects/KICEsentences/`
> 이 문서가 신규 시험지(모의평가·수능) 반영의 단일 절차서다. `UPDATE_PROCEDURE.md` 는 해설만 고칠 때의 재빌드 요약이다.

---

## 0. 준비

| 항목 | 값 |
|---|---|
| 시험지 | 작업 폴더에 PDF로 둔다 (예: `2027수능.pdf`). 수능은 **홀수형(1~20쪽)** + 짝수형(21~40쪽)이 이어붙어 있으므로 홀수형만 쓴다 |
| 정답표 | PDF (예: `2027수능_정답.pdf`). 홀수형 정답을 쓴다 (짝수형은 일부 문항의 선지 순서가 다름) |
| 파일명 접두어 | 기존 규칙: `2027.6모`, `2027.9모`, `2027수능` |
| 문항 접미어 | 공통 `01`~`22`, 선택 `확23`~`확30`, `미23`~`미30`, `기23`~`기30` (총 46개) |

### Python 실행 환경 (2026-11 기준)

| 작업 | 인터프리터 | 이유 |
|---|---|---|
| PDF 분할·썸네일 (fitz, pypdfium2) | `venv/bin/python` | Homebrew `python3` 에는 fitz 없음 |
| `build_db.py`, `lint_sol.py`, `dashboard.py` | `venv/bin/python` | Homebrew `python3` 에는 markdown·numpy 없음 |
| `build_vectors.py`, `build_query_vocab.py` | `/usr/bin/python3` | venv 의 torch 가 깨져 있음(libtorch_cpu.dylib 누락). 시스템 Python 에 sentence_transformers + torch 2.8 있음 |

환경이 바뀌었으면 각 인터프리터에서 `import fitz` / `import markdown` / `import sentence_transformers` 로 먼저 확인한다.

---

## 1. 문항 분할

```bash
venv/bin/python scripts/extract_exam_auto.py 2027수능.pdf scratch/2027_suneung_extracted 2027수능
```

- 텍스트 레이어에서 문항 번호(`1.`, `23.` 등)의 위치를 찾아 영역을 **자동 계산**한다. 좌표를 손으로 잡을 필요 없음.
  - 같은 단(왼쪽/오른쪽)의 다음 번호 직전까지를 한 문항으로 자른다.
  - 경계는 단 전체 폭이 4pt 이상 비어 있는 줄로 잡는다. 번호 위로 솟은 분수·지수·lim 이 잘리지 않는다.
  - 단 하단의 「※ 확인 사항」 박스는 자동으로 제외한다.
- 쪽 → 구간 대응(1~8 공통, 9~12 확, 13~16 미, 17~20 기)은 스크립트의 `SECTIONS` 에 있다. 시험지 구성이 달라지면 여기만 고친다.
- 마지막 줄의 `총 46개 추출` 을 확인한다(다르면 ⚠ 경고가 출력됨).
- **반드시 눈으로 검수**: 46개를 한 장의 미리보기로 렌더링해서 잘림·겹침·박스 포함 여부를 확인한다.
- 검수 후 복사: `cp -n scratch/2027_suneung_extracted/*.pdf PDF_Ref/`
- 파일명은 NFC 정규화 상태여야 한다(기존 `PDF_Ref` 파일 전부 NFC).

> 이전 방식인 `scripts/extract_2027_9mo.py` 는 시험마다 `AREA_COORDINATES` / `PAGE_AREA_CONFIG` 를 손으로 맞춰야 했다. 자동 방식이 실패하는 특이 레이아웃에서만 참고한다.

## 2. 썸네일 생성

```bash
venv/bin/python scripts/generate_thumbnails_2027.py 2027수능 scratch/2027_suneung_extracted scratch/2027_suneung_thumbnails
```

- 인자: `<접두어> [PDF폴더=PDF_Ref] [출력폴더=scratch/<접두어>_thumbnails]`
- 문항 번호를 흰색으로 가리고 마침표 위치를 기준으로 정렬한 PNG(가로 1400px)를 만든다.
- 기존 썸네일(예: `static/thumbnails/2027.9모_01.png`)과 나란히 놓고 정렬·여백을 비교한 뒤 복사한다:
  `cp -n scratch/2027_suneung_thumbnails/*.png static/thumbnails/`
- 한 문항만 다시 만들 때는 `scripts/rebuild_thumbnail.py <문항ID> [높이]` 를 쓴다.

## 3. 문항 원문 MD 작성 (`MD_Ref/<연도>/`, 46개)

- 수식 글꼴이 PDF 텍스트 레이어에서 사설 영역 문자로 깨져 나오므로 **텍스트 추출은 쓸 수 없다**. 문항 이미지를 130dpi 정도로 렌더링해서 보고 LaTeX 로 옮겨 적는다.
- 형식(예: `MD_Ref/2027/2027수능_01.md`):

```markdown
---
학년도: 2027
시기: 수능          # 6모 / 9모 / 수능
유형: 공통          # 공통 / 확통 / 미적 / 기하
번호: 01            # 선택과목은 23~30
---
![[2027수능_01.pdf]]

1. $\sqrt[3]{32} \times 4^{-\frac{1}{3}}$ 의 값은? [2점]
(1) 1
(2) 2
...
```

- 선지는 `(1)`~`(5)`, 보기 박스는 `\*{〈보 기〉}` 뒤에 ㄱ/ㄴ/ㄷ, 조건 박스는 (가)/(나) 줄로 적는다. 그림은 PDF 임베드로 대신한다.

## 4. 해설 작성 (`Sol/<연도>/`)

- **범위**: 공통 22개 + 확률과 통계 8개 = 30개. 미적분·기하 선택은 해설을 쓰지 않는다(분할·썸네일·원문은 46개 모두 만든다).
- **규칙 문서** (작성 전에 다시 읽기):
  - 형식: `AI_Sol_Instructions.md` (T-A-R 블록)
  - 절차·검수: `.agents/workflows/해설작성.md`
  - 금지어·누적 규칙: `Docs/Dialectical_Memory.md`
  - Trigger 카테고리: `Docs/Trigger_Dictionary.md` (기존 `Sol/` 에서 쓰는 카테고리도 grep 해서 맞춘다)
  - 용어: `Docs/vocab_standard.md`
  - 성취기준 코드: `concepts.json` 에 실제로 있는 id 만 쓴다. 지수·로그함수 그래프 코드(`12대수01-05~07`)는 없으므로 `12대수01-04` 를 쓴다.
- **정답 검증**: 모든 문항을 독립적으로 풀어 정답표와 30/30 대조한다.
- **자동 점검** (파일 기록 후):
  - 타이틀: `$` 없음, 끝이 `구하기`, ㄱ/ㄴ/ㄷ·(가)/(나) 없음
  - `따라서` 는 파일마다 1회이고 마지막 줄 `따라서 정답은 **N**입니다.` 에서만 쓴다
  - 금지어(`점화식`, `영점`, `중복도`, `에 따라` 등)와 소재어(`주사위`, `카드`, `주머니`)가 타이틀·Trigger·Action 에 없음
  - Action 코드가 모두 `concepts.json` 에 있음
  - `venv/bin/python lint_sol.py` 에서 새 파일 지적 0건. 이 스크립트는 `lint_report.csv` 를 덮어쓰므로 필요하면 미리 백업해 두고 되돌린다.

## 5. 재빌드

```bash
venv/bin/python build_db.py          # kice_database.sqlite 전체 재생성
/usr/bin/python3 build_vectors.py    # kice_step_vectors.npz (BGE-m3-ko, 로컬 캐시)
/usr/bin/python3 build_query_vocab.py  # kice_query_vocab.npz
```

- 확인: `sqlite3 kice_database.sqlite "select count(*) from problems where problem_id like '2027수능%'"` → 30
- `build_vectors.py` 의 저장 벡터 수 = DB 의 Step 수

## 6. 로컬 확인 (포트 8181)

```bash
kill $(lsof -ti :8181) 2>/dev/null || true
nohup venv/bin/python dashboard.py >> nohup.out 2>&1 &
```

- `nohup.out` 에서 `[OfflineQueryEngine] 로드 완료: ... Step N개` 확인
- `/api/search_probid?q=2027수능 21`, `/api/search?q=<타이틀 문구>`, `/thumbnail/<문항ID>`, `/pdf/<문항ID>.pdf` 응답 확인

## 7. 커밋 · 배포

- `PDF_Ref/` 는 `.gitignore` 대상이다. 로컬·오프라인 빌드용이라 운영 서버에는 폴더가 없고, 온라인 서비스는 썸네일만 쓴다.
- 커밋 대상: `static/thumbnails/`, `MD_Ref/`, `Sol/`, `kice_database.sqlite`, `kice_step_vectors.npz`, `kice_query_vocab.npz`, 수정한 스크립트·문서
- 원본 시험지 PDF 와 `scratch/` 는 커밋하지 않는다.
- 배포: `.agents/workflows/deploy_remote.md` (push 후 서버 `git pull --ff-only` → `pm2 restart ecosystem.config.js --update-env` → `pm2 save`)
- **운영 서버는 `ubuntu@146.56.118.155` (`lynx-a1`)**. 같은 SSH 키로 접속되는 `144.24.93.90` (`instance-main-recovered`) 은 Think Lynx 서버가 아니다(think-lynx-dashboard 없음, 도메인 DNS 도 146.56.118.155).
