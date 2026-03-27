# KICE Lynx 학습지 생성 프롬프트

> 이 파일과 함께 아래 두 파일을 AI에게 첨부합니다:
> 1. `ws_shared.css` — 공용 스타일 (변수 시스템 포함)
> 2. 해당 템플릿 HTML 파일 (A/B/C 중 필요한 것)
> 3. `content_package.json` — 장바구니 내보내기 데이터

---

## 시스템 프롬프트

당신은 고등학교 수학 학습지를 HTML 형식으로 편집하는 전문 편집자입니다.
아래 규칙과 첨부된 템플릿 파일을 엄격히 준수하여 학습지를 완성하십시오.

### 핵심 원칙

1. **구조는 건드리지 않습니다.**
   `ws-page`, `ws-columns`, `ws-col`, `ws-footer` 등 구조적 클래스와
   CSS 변수 `--ws-page-*`, `--ws-pad-*`, `--ws-footer-top`은 절대 수정하지 마십시오.
   A4 크기(210mm × 296mm)와 여백(상 10mm / 좌우 15mm / 하 18mm)은 고정입니다.

2. **테마만 사용자 요청에 따라 조정합니다.**
   `ws_shared.css`의 `--ws-accent`, `--ws-concept-bg`, `--ws-step-title-bg` 등
   테마 변수만 수정하십시오.

3. **수식은 KaTeX 문법을 사용합니다.**
   인라인: `$수식$`, 디스플레이: `$$수식$$`

4. **페이지 분절을 직접 계산합니다.**
   각 페이지의 유효 콘텐츠 높이는 약 230mm입니다. 아래 기준으로 배치하십시오:

   | 요소 | 예상 높이 |
   |------|-----------|
   | 문항 헤더(번호+pid) | 25px |
   | 단문항 썸네일 이미지 | 컬럼 높이의 약 50% (96~110mm) |
   | 장문항 썸네일 이미지 | 컬럼 높이의 100% |
   | 해설 문항 헤더 | 28px |
   | Step 블록 1개 (짧은 풀이) | 35~50px |
   | Step 블록 1개 (긴 풀이/수식 포함) | 55~90px |
   | 개념 박스 (정의+공식) | 65~80mm |
   | 개념 박스 (짧은 포인트) | 40~55mm |

5. **페이지가 넘칠 경우 분할합니다.**
   - 문항: 다음 컬럼 또는 다음 페이지에 배치
   - 해설: Step 단위로 분할. 첫 조각은 `.ws-exp-item`, 이후 조각은 `.ws-exp-item-cont`
   - 개념: 박스 단위로 다음 페이지에 배치

---

## 사용자 지시문 템플릿

다음 내용을 AI에게 전달합니다. 꺾쇠 `< >` 부분을 채워 사용하세요.

---

### 요청 유형 A — 개념+문항+해설 통합 학습지

```
첨부된 파일을 사용하여 학습지를 생성해 주세요.

[구성 요청]
- 학습지 제목: <예: "2028 수능 대비 삼각함수 집중 학습지">
- 페이지 구성:
  1. 개념 정리 페이지 (Template A) × <1~2>
  2. 문항 페이지 (Template B) × <필요한 만큼>
  3. 해설 페이지 (Template C) × <필요한 만큼>
- 정답 표시: <인라인 / 정답표 / 없음>
- 테마 색상: <기본(파란 계열) / 초록 계열 / 모노크롬 / 직접 지정: #XXXXXX>

[콘텐츠 데이터]
첨부 파일 `content_package.json` 참조.

[추가 요청]
<예: "개념 박스에 공식만 간결하게 넣어주세요" / "Step 번호 대신 ▶로 표시해주세요">
```

---

### 요청 유형 B — 문항지만 (해설 없음)

```
첨부된 Template B를 사용하여 문항지만 만들어 주세요.

- 제목: <제목>
- 정답표: <마지막 페이지 포함 / 없음>
- 문항 데이터: 첨부 `content_package.json` 참조
```

---

### 요청 유형 C — 해설지만

```
첨부된 Template C를 사용하여 해설지만 만들어 주세요.

- 제목: <제목>
- Step 표시 방식: <"Step 1 — 타이틀" 형식 유지 / 번호 없이 타이틀만>
- 해설 데이터: 첨부 `content_package.json` 참조
```

---

## content_package.json 형식 (내보내기 데이터 구조)

KICE Lynx 앱에서 내보낸 JSON의 구조입니다.
AI는 이 데이터를 읽어 템플릿에 채워 넣습니다.

```json
{
  "title": "2028 수능 대비 삼각함수 집중 학습지",
  "generated_at": "2026-03-25",
  "items": [
    {
      "pid": "2023_수능_15",
      "exam_number": 1,
      "is_long": false,
      "thumbnail_src": "/static/thumbnails/2023_수능_15.png",
      "answer": "③",
      "cpt_codes": ["12대수02-02"],
      "cpt_names": ["삼각함수의 뜻과 그래프"],
      "steps": [
        {
          "step_number": 1,
          "step_title": "주기와 진폭 파악",
          "explanation_html": "$f(x) = a\\sin(bx+c)+d$에서 진폭 $= |a|$, 주기 $= \\dfrac{2\\pi}{|b|}$..."
        },
        {
          "step_number": 2,
          "step_title": "계수 결정",
          "explanation_html": "..."
        }
      ]
    }
  ],
  "concepts": [
    {
      "cpt_id": "12대수02-02",
      "curriculum_unit": "대수 - 삼각함수",
      "standard_name": "삼각함수의 뜻을 알고 그래프를 그릴 수 있다.",
      "related_item_count": 3
    }
  ]
}
```

---

## 테마 변수 빠른 참조

AI에게 테마 변경을 요청할 때 아래 변수를 지정하세요.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `--ws-accent` | `#2563eb` | 포인트 컬러 (pill, 링크 등) |
| `--ws-accent-light` | `#dbeafe` | 포인트 연한 배경 |
| `--ws-concept-title-bg` | `#2563eb` | 개념 박스 제목 배경 |
| `--ws-concept-bg` | `#f0f7ff` | 개념 박스 본문 배경 |
| `--ws-formula-bg` | `#fffbeb` | 공식 블록 배경 |
| `--ws-formula-border` | `#fcd34d` | 공식 블록 좌측 선 |
| `--ws-step-title-bg` | `#f1f5f9` | Step 제목 배경 |
| `--ws-font-size-step-body` | `0.76rem` | Step 본문 폰트 크기 |

### 테마 프리셋 예시

**모노크롬 (흑백 인쇄 최적화)**
```css
--ws-accent: #000000;
--ws-accent-light: #f8f8f8;
--ws-concept-title-bg: #333333;
--ws-concept-bg: #fafafa;
--ws-formula-bg: #f5f5f5;
--ws-formula-border: #999999;
--ws-step-title-bg: #eeeeee;
```

**초록 계열**
```css
--ws-accent: #059669;
--ws-accent-light: #d1fae5;
--ws-concept-title-bg: #065f46;
--ws-concept-bg: #ecfdf5;
--ws-formula-bg: #f0fdf4;
--ws-formula-border: #6ee7b7;
--ws-step-title-bg: #f0fdf4;
```

---

## 개발 메모

- **현재 구현 상태**: 템플릿 3종 + 프롬프트 초안 완성 (2026-03-25)
- **미구현**: KICE Lynx 앱 내 "학습지 내보내기" 버튼 및 content_package.json 생성 로직
- **다음 단계**:
  1. `dashboard.py`에 `/api/export-worksheet` 엔드포인트 추가
     → cart 아이템 + Step 데이터를 content_package.json 형식으로 반환
  2. 앱 UI에 "학습지 생성" 버튼 추가 (장바구니 → 내보내기)
  3. 사용자가 JSON + 템플릿 파일들을 묶어 AI에 업로드
  4. (선택) 프롬프트를 앱 내에서 복사할 수 있는 UI 추가
- **검토 필요**:
  - 썸네일 이미지 오프라인 패키징 방식 (base64 inline vs. 상대경로)
  - Step explanation_html의 이미지 포함 방식
