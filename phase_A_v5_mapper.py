"""
Phase A V5 (재설계): Concept-Accurate Mapper
=============================================
올바른 파이프라인:
  Step 1. [Vector] 86개 성취기준 중 Top-3 후보 추출 (좁히기만)
  Step 2. [LLM]   Top-3 후보 + 성취기준 정의를 보고 "정확한" 1개 선택
  Step 3. [LLM]   해당 성취기준 내에서 쓰인 수학적 개념을 개념어로 명명
                   → canonical_name (수학적 개념어 형식)

유사도는 Step 1에서만 쓰임 (후보 좁히기).
최종 정확도는 Step 2~3의 LLM 판단에 달려 있음.
Step 4에서 canonical_name 간 유사도로 "같은 개념, 다른 문항" 연결.

실행: .venv/bin/python phase_A_v5_mapper.py
"""

import json, os, re, requests, numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ─── 설정 ──────────────────────────────────────────────────
RAW_CHUNKS_FILE = '.build_cache/phase_A/raw_chunks_cache_v3_ollama.json'
CONCEPTS_FILE   = 'concepts.json'
RESULT_FILE     = 'phaseA_v5_mapped.json'
CACHE_DIR       = '.build_cache/phase_A'
os.makedirs(CACHE_DIR, exist_ok=True)

OLLAMA_URL      = "http://localhost:11434/api/chat"
OLLAMA_MODEL    = "qwen2.5-coder:14b"
EMBED_MODEL     = 'dragonkue/BGE-m3-ko'
TOP_K           = 3    # vector로 좁힐 후보 수


# ─── LLM 호출 ──────────────────────────────────────────────
def call_llm(prompt, timeout=180):
    try:
        res = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False, "format": "json"
        }, timeout=timeout)
        res.raise_for_status()
        return json.loads(res.json()['message']['content'])
    except Exception as e:
        print(f"  [!] LLM 오류: {e}")
        return None


# ─── Step 2+3 통합 LLM 프롬프트 ────────────────────────────
def map_and_name(raw_action, sub_calcs, candidates):
    """
    Step 2: 후보 3개 중 정확한 성취기준 1개 선택
    Step 3: 해당 성취기준 내에서 쓰인 수학적 개념을 개념어로 명명
    두 작업을 한 번의 LLM 호출로 처리.
    """
    cand_str = "\n".join([
        f"  [{i+1}] {c['id']}: {c['name']}\n       핵심어: {', '.join(c['keywords'][:4])}"
        for i, c in enumerate(candidates)
    ])
    sub_str = "\n".join([f"  - {s}" for s in sub_calcs[:3]])

    prompt = f"""너는 한국 고등학교 수학 교육과정 전문가다.

[풀이 스텝]
행동: "{raw_action}"
세부 계산:
{sub_str}

위 풀이 스텝이 사용하는 수학적 원리에 가장 정확하게 대응하는 성취기준을 아래 후보 중 하나 선택하라.
성취기준명과 핵심어를 수학적으로 꼼꼼이 읽고 판단하라.

후보:
{cand_str}

선택 후, 이 스텝에서 실제로 적용된 수학적 개념을 "개념어 형식"으로 명명하라.
개념어 작명 규칙:
  - 형식: [교육과정 공식 용어]를 이용한 [구체적 수학 조작]
  - 예시: "등비수열의 공비 관계를 이용한 인접항의 곱 일반화"
  - 문항 고유 변수·숫자 절대 사용 금지
  - 너무 포괄적("조건 이용")이거나 너무 세세("x에 3 대입")하지 않게

반드시 아래 JSON만 반환:
{{
  "concept_id": "선택한 성취기준 ID",
  "canonical_name": "개념어 형식의 이 스텝 명칭",
  "reason": "선택 이유 한 문장"
}}"""

    return call_llm(prompt)


# ─── 메인 ──────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("🎯 Phase A V5: Concept-Accurate Mapper (재설계)")
    print("   Step1=Vector 후보좁히기 | Step2~3=LLM 정확 매핑+명명")
    print("=" * 60)

    # ── 성취기준 로드 ──────────────────────────────────────
    with open(CONCEPTS_FILE, 'r') as f:
        raw_concepts = json.load(f)
    concepts = []
    for row in raw_concepts:
        if row['id'].startswith('9수'):
            continue
        kws = [k for k in row.get('keywords', []) if isinstance(k, str) and len(k) > 1]
        concepts.append({
            'id':       row['id'],
            'name':     row.get('standard_name', ''),
            'keywords': kws,
            'embed_text': row.get('standard_name', '') + ' ' + ' '.join(kws)
        })
    print(f"\n고등학교 성취기준: {len(concepts)}개")

    # ── 청크 로드 ──────────────────────────────────────────
    with open(RAW_CHUNKS_FILE, 'r') as f:
        raw_data = json.load(f)
    chunks = []
    for item in raw_data:
        fpath = item.get('file', '')
        for c in item.get('chunks', []):
            if not isinstance(c, dict) or not c.get('is_core_jump'):
                continue
            chunks.append({
                'file':            fpath,
                'step_number':     c.get('step_number', 0),
                'raw_action':      c.get('logical_action', ''),
                'sub_calculations': c.get('sub_calculations', []),
            })
    print(f"is_core_jump=True 청크: {len(chunks)}개")

    # ── 기존 결과 로드 (이어 부르기) ──────────────────────
    if os.path.exists(RESULT_FILE):
        with open(RESULT_FILE, 'r') as f:
            results = json.load(f)
    else:
        results = []
    done_keys = {f"{r['file']}_{r['step_number']}" for r in results
                 if r.get('concept_id')}
    print(f"기 완료: {len(done_keys)}개 → 남은 대상: {len(chunks)-len(done_keys)}개")

    # ── Step 1: 성취기준 임베딩 (vector 후보 좁히기용) ────
    print("\n[Step 1] 성취기준 임베딩 생성...")
    model = SentenceTransformer(EMBED_MODEL)
    concept_embs = model.encode(
        [c['embed_text'] for c in concepts],
        normalize_embeddings=True, show_progress_bar=False
    )

    # ── Step 2~3: LLM 정확 매핑 루프 ──────────────────────
    print("\n[Step 2~3] LLM 정확 매핑 시작 ---")
    new_count = 0

    for idx, chunk in enumerate(chunks):
        key = f"{chunk['file']}_{chunk['step_number']}"
        if key in done_keys:
            continue

        # Vector: top-3 후보 좁히기
        action_emb = model.encode([chunk['raw_action']], normalize_embeddings=True)
        sims = cosine_similarity(action_emb, concept_embs)[0]
        top3_idx = np.argsort(sims)[-TOP_K:][::-1]
        candidates = [
            {**concepts[i], 'sim': round(float(sims[i]), 4)}
            for i in top3_idx
        ]

        fname = os.path.basename(chunk['file'])
        print(f"  > ({idx+1}/{len(chunks)}) {fname} Step {chunk['step_number']}", flush=True)

        # LLM: 정확한 성취기준 선택 + 개념어 명명
        llm_result = map_and_name(
            chunk['raw_action'],
            chunk['sub_calculations'],
            candidates
        )

        if llm_result and 'concept_id' in llm_result:
            concept_id   = llm_result.get('concept_id', candidates[0]['id'])
            canonical    = llm_result.get('canonical_name', chunk['raw_action'])
            reason       = llm_result.get('reason', '')

            # concept_id가 유효한지 검증 (후보에 없으면 top-1으로 fallback)
            valid_ids = {c['id'] for c in candidates}
            if concept_id not in valid_ids:
                concept_id = candidates[0]['id']
                reason += " [fallback: 유효하지 않은 ID → top-1 사용]"

            print(f"    → [{concept_id}] {canonical[:50]}")
        else:
            # LLM 실패: vector top-1으로 fallback
            concept_id = candidates[0]['id']
            canonical  = chunk['raw_action']
            reason     = "LLM 실패 - vector top-1 fallback"
            print(f"    ⚠️  LLM 실패, fallback: {concept_id}")

        # 결과 저장 (두 레이어 모두 보존)
        results.append({
            # ── Abstract Layer (검색·연결용) ──
            'concept_id':     concept_id,
            'canonical_name': canonical,
            'reason':         reason,

            # ── Concrete Layer (문항 고유 맥락, 보존) ──
            'raw_action':        chunk['raw_action'],
            'sub_calculations':  chunk['sub_calculations'],

            # ── 메타 ──
            'file':         chunk['file'],
            'step_number':  chunk['step_number'],
            'top3_candidates': [
                {'id': c['id'], 'sim': c['sim']} for c in candidates
            ],
        })
        done_keys.add(key)
        new_count += 1

        # 5개마다 자동 저장 (세이브포인트)
        if new_count % 5 == 0:
            with open(RESULT_FILE, 'w') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

    # 최종 저장
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ 완료! 신규 처리: {new_count}개 | 총 누적: {len(results)}개")
    print(f"   결과: {RESULT_FILE}")
    print(f"\n💡 다음 단계: canonical_name 품질 검토 → 동일 개념어 클러스터링")
