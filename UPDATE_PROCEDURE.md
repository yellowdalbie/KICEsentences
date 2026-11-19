# 해설 추가 후 DB/벡터 업데이트 절차서

> **대상 경로**: `/Users/home/vaults/projects/KICEsentences/`  
> **최종 수정**: 2026-11-19
>
> ⚠ **신규 시험지(문항 분할·썸네일·원문·해설) 반영은 [`Docs/new_exam_procedure.md`](Docs/new_exam_procedure.md) 를 따를 것.** 이 문서는 해설만 고친 뒤의 재빌드 요약이다.

---

## 1단계: 해설 파일 작성

`Sol/<연도>/` 폴더에 마크다운 파일 작성.  
반드시 아래 T-A-C 형식을 준수할 것.

```markdown
## [Step N] 스텝 타이틀 (한국어, 간결하게)

- **Trigger**: [트리거 설명] 수식 또는 조건
- **Action**: [CPT-XX-XXX-000] 성취기준 ID + 행동 설명
- **Result**: 결과값 또는 결론

> **📝 해설 (Explanation)**
> 상세 풀이 설명...
```

**주의사항:**

- `step_title`은 "~을 이용한 ~의 계산/판단/결정" 형태로 명확하게 작성
- `Action`의 `[CPT-...]` ID는 반드시 `concepts.json`에 존재하는 값 사용

---

## 2단계: DB 재빌드

```bash
cd /Users/home/vaults/projects/KICEsentences
venv/bin/python build_db.py
```

- 기존 `kice_database.sqlite` 삭제 후 전체 재생성
- 완료 후 터미널에서 추가된 레코드 수 확인

---

## 3단계: 벡터 인덱스 재생성

```bash
/usr/bin/python3 build_vectors.py
/usr/bin/python3 build_query_vocab.py
```

- 모든 `step_title` 재임베딩 (BGE-m3-ko 모델, 로컬 캐시 사용 → 빠름). venv 의 torch 는 깨져 있어 시스템 Python 사용
- 이어서 검색 어휘(`kice_query_vocab.npz`)도 반드시 재빌드
- 완료 메시지: `완료! 저장된 벡터 수: N, 차원: 1024`
- `kice_step_vectors.npz` 파일 업데이트됨

---

## 4단계: PDF 썸네일 생성 (신규 문항인 경우만)

썸네일은 자동 생성되지 않는다. `scripts/generate_thumbnails_2027.py <접두어> [PDF폴더] [출력폴더]` 로 미리 만들어 `static/thumbnails/` 에 둔다 (상세: `Docs/new_exam_procedure.md` 2단계). 한 문항만 다시 만들 때는 `scripts/rebuild_thumbnail.py <문항ID>`.

---

## 5단계: 서버 재시작

```bash
kill $(lsof -ti :8181) 2>/dev/null || true
nohup venv/bin/python dashboard.py >> nohup.out 2>&1 &
```

시작 로그 확인:

```bash
grep "OfflineQueryEngine" nohup.out | tail -1
# → [OfflineQueryEngine] 로드 완료: 어휘 N개 / Step N개
```

원격 배포는 `.agents/workflows/deploy_remote.md` (운영 서버 `ubuntu@146.56.118.155`).

---

## 전체 요약 (한 번에 실행)

```bash
cd /Users/home/vaults/projects/KICEsentences
venv/bin/python build_db.py && /usr/bin/python3 build_vectors.py && /usr/bin/python3 build_query_vocab.py
```

---

## 확인 체크리스트

- [ ] `Sol/<연도>/<문항명>.md` 파일 형식 정상 확인
- [ ] `build_db.py` 오류 없이 완료
- [ ] `build_vectors.py` 완료 메시지의 스텝 수 증가 확인
- [ ] 대시보드 새로고침 후 새 문항 검색 결과 확인
- [ ] 🔍 아이콘 클릭 시 유사 스텝 패널 정상 작동 확인
