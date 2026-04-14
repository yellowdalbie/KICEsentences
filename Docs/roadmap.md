# KICEsentences 전체 작업 로드맵

**최종 목표**: 수능 수학 문항 해설 Sol 파일을 수학교육학적으로 정확하고 검색·분류에 최적화된 완벽한 형태로 재작성한다.  
**버전**: 1.2 (2026-04-12)  
**상태**: Phase A-2 Step 2 진행 중 (qwen 클러스터 명명)

---

## 핵심 개념 모델: 원자-분자 체계

### 원자 (Atom)

> 수능 수학 문항의 풀이 스텝 하나에서 사용되는 **단일 수학적 아이디어 / 공식 / 도구**.

- 예: "0/0형 불정형을 인수분해로 처리하여 극한값 산출"
- 예: "좌극한·우극한 비교로 연속 여부 판정"
- 예: "등비수열 인덱스 합 동치로 항의 곱 변환"
- 원자는 concept_id(성취기준)보다 세밀하다. 하나의 concept_id 안에 여러 원자가 존재한다.
- **같은 원자 → canonical_name이 거의 동일한 텍스트여야 한다.**
- 원자의 이름(canonical_name)에는 문항의 특수성(delta)이 섞이지 않는다.
- canonical_name은 반드시 vocab_standard 공식 용어를 anchor_term으로 포함한다.

### 분자 (Molecule)

> Sol 파일의 **스텝타이틀(step_title)**. 원자 이름(canonical_name)을 기반으로 이 문항의 맥락(delta)을 더해 작성한다.

- 유사한 원자 집합을 쓰는 스텝들은 유사한 분자를 가지므로 벡터 유사도 검색에서 자연스럽게 클러스터링된다.

### delta (문항 특수성)

> 원자 이름에는 포함되지 않으나 분자(step_title) 작성 시 반영되는 **이 문항만의 특수한 맥락**.

- 예: canonical_name = "좌극한·우극한 비교로 연속 여부 판정"
- delta = "x=1에서 k값을 결정하기 위한 조건"
- 분자(step_title) = "좌극한·우극한 비교로 x=1 연속 조건의 미정계수 결정"

---

## 데이터 구조

### Sol 파일 (단일 진실 공급원)

```markdown
## [Step N] {step_title}           ← 분자 (최종 결과물)

- **Trigger**: [{카테고리}] {원본 문제의 촉발 조건}
- **Action**: [{concept_id}] {수학적 조작 설명}
- **Result**: {이 스텝에서 산출된 결과}

> **📝 해설 (Explanation)**
> {풀이 서술}
```

### DB (kice_database.sqlite)

| 테이블 | 역할 |
|--------|------|
| `problems` | 문항 메타데이터 |
| `steps` | step_title, action_concept_id, action_text, result_text |
| `triggers` | trigger 텍스트 |
| `step_triggers` | step ↔ trigger 다대다 |

### Phase A 작업 파일

| 파일 | 역할 | 상태 |
|------|------|------|
| `vocab_standard.json` | 공식 용어 사전 SSoT (terms + _banned_terms) | ✅ 운영 중 |
| `Docs/vocab_standard.md` | 위 자동 렌더링 (`tools/render_vocab_md.py`) | ✅ |
| `phaseA_v7_mapped.json` | V7 결과: concept_id + canonical_name 후보 | ✅ 완료 |
| `.build_cache/phase_A/clusters_raw.json` | 클러스터링 결과 (A-2 Step1) | ✅ 생성 완료 (2541 클러스터) |
| `.build_cache/phase_A/clusters_named.json` | qwen 명명 결과 (A-2 Step2) | 🔄 진행 중 |
| `atom_registry_review.md` | 사람 검토용 문서 (A-2 Step3) | 미생성 |
| `atom_registry.json` | 확정된 원자 목록 (A-2 완료) | 미생성 |
| `phaseA_final_mapped.json` | 원자 기반 최종 매핑 (A-3 완료) | 미생성 |
| `merge_split_proposals.json` | 병합/분리 후보 목록 (A-3 말미) | 미생성 |

### Phase A 스크립트 전체

| 스크립트 | 역할 | 단계 |
|---------|------|------|
| `phase_A_atom_clusterer.py` | raw_action 임베딩 + concept_id별 계층적 클러스터링 | A-2 Step1 |
| `phase_A_cluster_namer.py` | qwen으로 클러스터별 canonical_name + anchor_term 생성 | A-2 Step2 |
| `phase_A_review_builder.py` | 사람 검토용 마크다운 문서 생성 | A-2 Step3 |
| `phase_A_registry_builder.py` | 검토 완료 마크다운 → atom_registry.json | A-2 Step4 |
| `phase_A_final_mapper.py` | atom_registry 기반 각 청크 재분류 | A-3 |
| `phase_A_merge_split.py` | Sol Step 병합/분리 후보 자동 탐지 | A-3 말미 |

---

## 전체 로드맵

```
Phase A-1: 원자 후보 채굴 (V7 매핑)          ✅ 완료 (2026-04-12)
     │
Phase A-2: 원자 목록 구성                    ← 현재
     │  Step 1: raw_action 클러스터링
     │  Step 2: qwen 클러스터 명명 (vocab 연동)
     │  Step 3: 사람 검토 (is_pure=false 집중)
     │  Step 4: atom_registry.json 확정
     │
Phase A-3: 원자 기반 재분류 + 병합/분리 분석
     │  · atom_registry 기반 각 청크 재분류
     │  · delta 추출
     │  · Sol Step 병합/분리 후보 자동 생성
     │
Phase B:   Trigger 검증 및 정제
     │
Phase C:   지침서 작성 + Sol 파일 재검토
     │  · 병합/분리 후보 보고 사람이 Step 구조 최종 결정
     │  · step_title(분자) 작성
     │
Phase D:   DB/벡터 재빌드 → 배포
```

---

## Phase A-1: 원자 후보 채굴 ✅

**상태**: 완료 (2026-04-12)

| 항목 | 수치 |
|------|------|
| 총 완료 | 2,845개 |
| needs_review | 68개 (vocab 검증 실패 또는 LLM 오류) |
| top1_sim < 0.4 (저신뢰) | 694개 (fallback 포함) |

**주요 설계 원칙**
- canonical_name: vocab_standard 공식 용어 최소 1개 포함, LaTeX 금지
- is_core_jump: 새로운 수학적 도구/아이디어가 처음 적용되는 순간. 단순 대입·확인은 false.
- V7의 canonical_name은 **원자 후보(candidate)**이며 확정이 아님.

---

## Phase A-2: 원자 목록 구성 ← 현재

**목표**: V7 후보들을 클러스터링하고 qwen + vocab_standard 연동으로 원자 목록을 확정한다.

### vocab_standard 연동 원칙

- 모든 atom canonical_name은 vocab_standard의 해당 concept_id `terms` 중 하나를 **anchor_term**으로 포함해야 한다.
- anchor_term은 canonical_name에서 수학적으로 가장 중심이 되는 공식 용어 1개.
- qwen 프롬프트에 `terms`와 `_banned_terms` 주입 → 출력 검증 → vocab 불일치 시 재시도.
- qwen이 vocab 없는 용어를 제안할 경우: vocab_standard 확장 검토 대상으로 플래그.

### atom_registry.json 구조

```json
[
  {
    "atom_id": "CA1-LIM-001",
    "concept_id": "12미적Ⅰ-01-02",
    "anchor_term": "좌극한",
    "canonical_name": "좌극한·우극한 비교로 연속 여부 판정",
    "instance_count": 12
  }
]
```

### Step 1: raw_action 클러스터링 (`phase_A_atom_clusterer.py`)

- 입력: `phaseA_v7_mapped.json`
- needs_review 항목 분리 후 별도 처리
- concept_id별로 raw_action 임베딩 (BGE-m3-ko)
- agglomerative clustering (임계값 0.82, average linkage)
- 출력: `.build_cache/phase_A/clusters_raw.json`

### Step 2: qwen 클러스터 명명 (`phase_A_cluster_namer.py`)

- 입력: `clusters_raw.json` + `vocab_standard.json`
- 클러스터당 qwen 1회 호출 (멤버 raw_action 최대 8개 샘플)
- 요청: is_pure 판단 + anchor_term + delta 없는 canonical_name
- vocab 검증 → 실패 시 재시도 (최대 2회)
- needs_review 항목: concept_id 재검토 포함하여 별도 호출
- 출력: `.build_cache/phase_A/clusters_named.json`

```
qwen 판단 결과:
  is_pure=true  → 자동 atom 후보 등록
  is_pure=false → 사람 검토 큐 (상단 배치)
  vocab_missing → vocab_standard 확장 검토 큐
```

### Step 3: 사람 검토 문서 생성 (`phase_A_review_builder.py`)

- 입력: `clusters_named.json`
- 출력: `atom_registry_review.md`

검토 문서 구성:
1. **[우선 검토]** is_pure=false 클러스터 (분리 제안 포함)
2. **[vocab 확장 검토]** vocab_missing 플래그 항목
3. **[정상 검토]** is_pure=true 클러스터 (concept_id 순, 크기 내림차순)
4. **[needs_review]** 별도 섹션 (concept_id 재검토 포함)

### Step 4: atom_registry 확정 (`phase_A_registry_builder.py`)

- 입력: `atom_registry_review.md` (사람 편집 완료)
- 출력: `atom_registry.json`

---

## Phase A-3: 원자 기반 재분류 + 병합/분리 분석

**목표**: atom_registry를 기반으로 모든 청크를 재분류하고, Sol Step 구조 재편 후보를 산출한다.

### 재분류 + delta 추출

- 입력: `phaseA_v7_mapped.json` + `atom_registry.json`
- 각 청크의 raw_action → atom_registry에서 가장 유사한 원자 선택
- delta = raw_action에서 canonical_name의 추상 부분을 제거한 잔여
- 신뢰도 낮은 항목 → needs_review 플래그
- 출력: `phaseA_final_mapped.json`

```json
{
  "file": "./Sol/2024/2024.수능_15.md",
  "step_number": 2,
  "atom_id": "CA1-LIM-001",
  "concept_id": "12미적Ⅰ-01-02",
  "anchor_term": "좌극한",
  "canonical_name": "좌극한·우극한 비교로 연속 여부 판정",
  "delta": "x=1에서 k값 결정 조건",
  "needs_review": false
}
```

### 병합/분리 후보 자동 생성

atom_id 매핑 완료 후 Sol 파일별 청크 구조를 분석한다.

**병합 신호**: 동일 Sol Step 내 연속 청크가 같은 atom_id
```
Sol Step 1
  chunk A → atom CA1-LIM-001  ─┐ 같은 원자
  chunk B → atom CA1-LIM-001  ─┘ → chunk B는 Step에 흡수
```

**분리 신호**: 동일 Sol Step 내 청크들이 서로 다른 atom_id
```
Sol Step 2
  chunk C → atom CA1-LIM-001  ─┐ 다른 원자
  chunk D → atom CA1-DIF-003  ─┘ → Step 2 분리 후보
```

- 출력: `merge_split_proposals.json`
- **주의**: 후보 목록만 생성. 실제 Sol 파일 구조 변경은 Phase C에서 사람이 결정.

---

## Phase B: Trigger 검증 및 정제

**목표**: 각 Sol Step의 Trigger가 해당 원자를 촉발하는 올바른 조건인지 검증한다.

- 기존 Trigger를 재생성하지 않고 **검증·수정** 방식
- `phaseA_final_mapped.json`의 concept_id vs Sol Action의 concept_id 불일치 항목 우선 검토
- Trigger 카테고리가 concept_id와 정합하지 않으면 교체

---

## Phase C: 지침서 작성 + Sol 파일 재검토

**목표**: 확정된 원자 목록으로 step_title 작성 지침서를 완성하고, 전체 Sol 파일을 재검토한다.

### 지침서 내용

1. 원자-분자-delta 모델 설명
2. step_title 작성 규칙 (canonical_name + delta 결합)
3. 원자 목록 참조 (atom_registry 기반, concept_id별 canonical_name 예시)
4. **Sol Step 병합/분리 최종 판단** (`merge_split_proposals.json` 참고)
5. Trigger 작성 기준

### Sol 파일 재검토 순서

1. 샘플 20~30개 수동 검토 → 지침서 검증
2. 자동 플래그: 지침서 위반 패턴 탐지
3. 플래그 항목 수동 수정
4. 나머지 전수 검토 (자동화 규칙 적용)

---

## Phase D: 최종 빌드

```bash
python3 build_db.py
python3 build_vectors.py
python3 build_query_vocab.py
python3 build_dist.py
```

배포 패키지 상세: `memory/project_packaging_plan.md` 참조.

---

## 현재 상태 (2026-04-12)

| Phase | 상태 | 완료 기준 |
|-------|------|---------|
| A-1: V7 매핑 | ✅ 완료 | phaseA_v7_mapped.json 2,845개 |
| A-2 Step1: 클러스터링 | ✅ 완료 | clusters_raw.json (2,541 클러스터) |
| A-2 Step2: qwen 명명 | 🔄 진행 중 | clusters_named.json |
| A-2 Step3~4: 검토+확정 | ⏳ 대기 | atom_registry.json |
| A-3: 재분류 + 병합/분리 | ⏳ 대기 | phaseA_final_mapped.json + merge_split_proposals.json |
| B: Trigger 검증 | ⏳ 대기 | 불일치 항목 수정 완료 |
| C: 지침서 + Sol 재검토 | ⏳ 대기 | 전 Sol 파일 step_title 확정 |
| D: 빌드 + 배포 | ⏳ 대기 | 배포 ZIP 생성 완료 |

---

## Phase A 터미널 실행 가이드

```bash
cd /Users/home/vaults/projects/KICEsentences

# ── Step 1: 클러스터링 (완료) ──────────────────────────────
# python3 phase_A_atom_clusterer.py
# 출력: .build_cache/phase_A/clusters_raw.json (2,541 클러스터)

# ── Step 2: qwen 명명 (진행 중 → 완료 후 다음으로) ──────────
python3 phase_A_cluster_namer.py
# 소요: ~3~5시간 (qwen2.5-coder:14b, 489회 LLM 호출)
# 중단 후 재시작 가능 (자동 이어하기 지원)
# 출력: .build_cache/phase_A/clusters_named.json

# ── Step 3: 검토 문서 생성 ───────────────────────────────────
python3 phase_A_review_builder.py
# 출력: atom_registry_review.md
# → 이 파일을 직접 편집:
#   - "제안 이름:" 줄 수정 (canonical_name 확정)
#   - "anchor:" 줄 수정 (anchor_term 확정)
#   - STATUS: DELETE 추가 (삭제 항목)
#   - 섹션 복사/삭제로 분리/병합 처리

# ── Step 4: atom_registry 확정 ──────────────────────────────
python3 phase_A_registry_builder.py
# 출력: atom_registry.json

# ── A-3: 최종 매핑 ────────────────────────────────────────
python3 phase_A_final_mapper.py
# 출력: phaseA_final_mapped.json

# ── A-3: 병합/분리 후보 생성 ──────────────────────────────
python3 phase_A_merge_split.py
# 출력: merge_split_proposals.json
```

> Step 2는 시간이 오래 걸리므로 백그라운드에서 실행:
> `nohup python3 phase_A_cluster_namer.py > namer_log.txt 2>&1 &`
> 진행 확인: `tail -f namer_log.txt`
