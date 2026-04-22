# worksheet_gen — THINK LYNX 학습지 생성 시스템

AI(Claude/Gemini)를 활용하여 장바구니 문항 데이터를 A4 인쇄용 학습지 HTML로 변환하는
템플릿 및 프롬프트 시스템.

## 파일 구성

```
worksheet_gen/
├── README.md                ← 이 파일
├── ws_shared.css            ← 공용 CSS (A4 구조 + 테마 변수)
├── template_A_concept.html  ← Template A: 개념 정리 페이지
├── template_B_problem.html  ← Template B: 문항 페이지 (썸네일 기반)
├── template_C_solution.html ← Template C: 해설 페이지 (Step별)
└── prompt_worksheet.md      ← AI 지시문 + 사용법 + 개발 메모
```

## 사용 방법 (현재)

1. THINK LYNX에서 장바구니 구성
2. (미구현) `/api/export-worksheet` → `content_package.json` 다운로드
3. 필요한 템플릿 HTML + `ws_shared.css` + `content_package.json`을 Claude/Gemini에 업로드
4. `prompt_worksheet.md`의 지시문을 복사해 요청 전송
5. AI가 반환한 HTML을 브라우저에서 열어 인쇄 (Ctrl+P)

## 템플릿 구조 요약

| 템플릿 | 용도 | 핵심 구조 |
|--------|------|-----------|
| A — 개념 | 성취기준별 개념/공식 정리 | `.ws-concept-box` × 1~3개 / 페이지 |
| B — 문항 | 썸네일 이미지 2단 배치 | `.ws-col-problem` (grid 2행) |
| C — 해설 | Step별 풀이 2단 배치 | `.ws-col-solution` (flex column) |

## 페이지 치수 (고정)

- 크기: 210mm × 296mm (A4)
- 여백: 상 10mm / 좌우 15mm / 하 18mm
- 유효 콘텐츠: 180mm(가로) × 약 230mm(세로)
- 2단 컬럼: 각 약 83mm 가로 (vline 제외)
