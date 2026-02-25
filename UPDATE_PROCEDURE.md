# 해설 추가 후 DB/벡터 업데이트 절차서

> **대상 경로**: `/Users/home/vaults/projects/KICEsentences/`  
> **최종 수정**: 2026-02-23

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
python3 build_db.py
```

- 기존 `kice_database.sqlite` 삭제 후 전체 재생성
- 완료 후 터미널에서 추가된 레코드 수 확인

---

## 3단계: 벡터 인덱스 재생성

```bash
python3 build_vectors.py
```

- 모든 `step_title` 재임베딩 (BGE-m3-ko 모델, 로컬 캐시 사용 → 빠름)
- 완료 메시지: `완료! 저장된 벡터 수: N, 차원: 1024`
- `kice_step_vectors.npz` 파일 업데이트됨

---

## 4단계: PDF 썸네일 생성 (신규 문항인 경우만)

새 문항의 PDF가 `PDF_Ref/` 폴더에 없을 경우:

```bash
# PDF_Ref/ 에 해당 PDF 파일 복사
cp <원본 경로>/<문항명>.pdf PDF_Ref/
```

기존 썸네일은 `static/thumbnails/` 에 캐시되어 있으므로 새 문항만 첫 마우스오버 시 자동 생성됨.

---

## 5단계: 서버 재시작

```bash
pkill -f dashboard.py
nohup python3 dashboard.py < /dev/null > dashboard.log 2>&1 &
```

시작 로그 확인:

```bash
grep "벡터" dashboard.log
# → [벡터 인덱스 로드됨] N개 스텝
```

---

## 전체 요약 (한 번에 실행)

```bash
cd /Users/home/vaults/projects/KICEsentences
python3 build_db.py && python3 build_vectors.py && pkill -f dashboard.py; nohup python3 dashboard.py < /dev/null > dashboard.log 2>&1 &
```

---

## 확인 체크리스트

- [ ] `Sol/<연도>/<문항명>.md` 파일 형식 정상 확인
- [ ] `build_db.py` 오류 없이 완료
- [ ] `build_vectors.py` 완료 메시지의 스텝 수 증가 확인
- [ ] 대시보드 새로고침 후 새 문항 검색 결과 확인
- [ ] 🔍 아이콘 클릭 시 유사 스텝 패널 정상 작동 확인
