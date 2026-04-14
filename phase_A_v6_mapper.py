"""
Phase A V6: Concept-Accurate Mapper (개선판)
============================================
V5 대비 변경사항:
  1. Top-K 3 → 5 (정답이 후보에 없는 경우 감소)
  2. vocab_standard 공식 용어 목록 프롬프트 주입
     → LLM이 교육과정 공식 용어를 반드시 참조하게 함
  3. canonical_name 형식 강제
     - 금지: 성취기준명 전문 복붙, LaTeX($...$), 변수명, 숫자
     - 필수: 교육과정 공식 용어 + 구체적 수학 조작 (15자 이상 40자 이하)
     - 형식 예시: "등비수열 공비를 이용한 인접항 곱의 일반화"
  4. 이어 실행 지원 (기 완료 건 skip)
  5. 5개마다 저장 → 10개마다 저장 (I/O 감소)

실행: .venv/bin/python phase_A_v6_mapper.py
출력: phaseA_v6_mapped.json
"""

import json, os, re, requests, numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ─── 설정 ──────────────────────────────────────────────────
RAW_CHUNKS_FILE   = '.build_cache/phase_A/raw_chunks_cache_v3_ollama.json'
CONCEPTS_FILE     = 'concepts.json'
VOCAB_FILE        = 'vocab_standard.json'   # 수학 개념어 사전 (SSoT)
RESULT_FILE       = 'phaseA_v6_mapped.json'
CACHE_DIR         = '.build_cache/phase_A'
EMBED_CACHE_FILE  = '.build_cache/phase_A/v6_embeddings.npz'  # 임베딩 캐시
os.makedirs(CACHE_DIR, exist_ok=True)

OLLAMA_URL      = "http://localhost:11434/api/chat"
OLLAMA_MODEL    = "qwen2.5-coder:14b"
EMBED_MODEL     = 'dragonkue/BGE-m3-ko'
TOP_K           = 5    # v5=3 → v6=5


# ─── 교육과정 공식 용어 사전 로드 (vocab_standard.json) ────
# 수정 시 vocab_standard.json만 편집하면 됨. 코드 변경 불필요.
with open(VOCAB_FILE, 'r') as _f:
    _vocab_raw = json.load(_f)
VOCAB_TABLE = {cid: entry['terms'] for cid, entry in _vocab_raw.items()}


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


# ─── 성취기준 후보별 공식 용어 문자열 생성 ─────────────────
def vocab_hint(concept_id):
    terms = VOCAB_TABLE.get(concept_id, [])
    if not terms:
        return "(사전 미등록)"
    return ", ".join(terms)


# ─── Step 2+3 통합 LLM 프롬프트 (v6) ──────────────────────
def map_and_name(raw_action, sub_calcs, candidates):
    """
    Step 2: Top-5 후보 중 정확한 성취기준 1개 선택
    Step 3: 해당 성취기준의 공식 용어를 반드시 사용해 canonical_name 작성
    """
    cand_str = "\n".join([
        f"  [{i+1}] {c['id']}: {c['name']}\n"
        f"       공식 용어: {vocab_hint(c['id'])}"
        for i, c in enumerate(candidates)
    ])
    sub_str = "\n".join([f"  - {s}" for s in sub_calcs[:4]])

    prompt = f"""너는 한국 고등학교 수학 교육과정 전문가다.

[풀이 스텝]
행동: "{raw_action}"
세부 계산:
{sub_str}

━━━ 작업 1: 성취기준 선택 ━━━
위 풀이 스텝이 사용하는 수학적 원리에 가장 정확하게 대응하는 성취기준을 아래 후보 중 1개 선택하라.
성취기준명과 공식 용어를 수학적으로 꼼꼼히 읽고 판단하라.

후보:
{cand_str}

━━━ 작업 2: canonical_name 작성 ━━━
선택한 성취기준의 "공식 용어" 중 1~2개를 반드시 포함하여, 이 스텝의 수학적 조작을 명명하라.

canonical_name 규칙 (위반 시 오답 처리):
  ✅ 형식: "[공식 용어] + [을/를 이용한] + [구체적 수학 조작]"
  ✅ 예시: "등비수열 공비를 이용한 인접항 곱의 일반화"
  ✅ 예시: "부정형(0/0꼴) 극한에서 분자 인수분해로 약분"
  ✅ 예시: "좌극한·우극한 비교를 통한 연속성 판정"
  ✅ 예시: "점화식의 홀짝 분기를 이용한 수열 주기 파악"
  ❌ 금지: 성취기준명 전체를 앞에 붙이기 ("함수의 극한에 대한 성질을(를) 이용하여...")
  ❌ 금지: LaTeX 수식 ($...$, \\frac, \\sum 등)
  ❌ 금지: 변수명, 숫자, 특정 문항 고유 값 (f(x), x=3, k 등)
  ❌ 금지: 모호한 서술어 ("도출하기", "확인하기", "파악하기")
  📏 길이: 15자 이상 45자 이하

반드시 아래 JSON만 반환 (다른 텍스트 없이):
{{
  "concept_id": "선택한 성취기준 ID (예: 12미적Ⅰ-01-02)",
  "canonical_name": "공식 용어 포함 수학 조작명",
  "reason": "선택 이유 (한 문장, 공식 용어 근거 명시)"
}}"""

    return call_llm(prompt)


# ─── 결과 검증 ──────────────────────────────────────────────
def validate_canonical(name: str) -> tuple[bool, str]:
    """canonical_name 형식 검증. (valid, 문제점)"""
    if not name or len(name) < 15:
        return False, f"너무 짧음 ({len(name)}자)"
    if len(name) > 50:
        return False, f"너무 김 ({len(name)}자)"
    if re.search(r'\$|\\\w+\{', name):
        return False, "LaTeX 수식 포함"
    bad_words = ["을(를) 이용하여", "도출하기", "확인하기", "파악하기", "계산하여", "정확히"]
    for w in bad_words:
        if w in name:
            return False, f"금지 표현 '{w}' 포함"
    return True, ""


# ─── 메인 ──────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("🎯 Phase A V6: Concept-Accurate Mapper")
    print("   Top-K=5 | vocab_standard 통합 | canonical_name 형식 강제")
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
            'embed_text': row.get('standard_name', '') + ' ' + ' '.join(kws[:6])
        })
    print(f"\n고등학교 성취기준: {len(concepts)}개")

    # ── 청크 로드 ──────────────────────────────────────────
    with open(RAW_CHUNKS_FILE, 'r') as f:
        raw_data = json.load(f)
    chunks = []
    for item in raw_data:
        fpath = item.get('file', '')
        for c in item.get('chunks', []):
            if not isinstance(c, dict):
                continue
            if not c.get('is_core_jump'):
                continue
            chunks.append({
                'file':             fpath,
                'step_number':      c.get('step_number', 0),
                'raw_action':       c.get('logical_action', ''),
                'sub_calculations': c.get('sub_calculations', []),
            })
    print(f"is_core_jump 청크: {len(chunks)}개")

    # ── 기존 결과 로드 (이어 실행) ────────────────────────
    if os.path.exists(RESULT_FILE):
        with open(RESULT_FILE, 'r') as f:
            results = json.load(f)
        print(f"기 완료: {len(results)}개 → 이어 실행")
    else:
        results = []
    done_keys = {f"{r['file']}_{r['step_number']}" for r in results}
    pending = [c for c in chunks if f"{c['file']}_{c['step_number']}" not in done_keys]
    print(f"신규 대상: {len(pending)}개")

    # ── Step 1: 임베딩 일괄 생성 후 모델 해제 ───────────────
    chunk_actions = [c['raw_action'] for c in pending]

    if os.path.exists(EMBED_CACHE_FILE):
        print(f"\n[Step 1] 임베딩 캐시 로드: {EMBED_CACHE_FILE}")
        cached = np.load(EMBED_CACHE_FILE)
        concept_embs = cached['concept_embs']
        # 청크 임베딩은 pending 목록이 달라질 수 있으므로 항상 재생성
        print(f"    성취기준 임베딩 캐시 로드 완료: {concept_embs.shape}")
        print(f"    청크 임베딩 재생성 중 ({len(chunk_actions)}개)...")
        model = SentenceTransformer(EMBED_MODEL)
        chunk_embs = model.encode(
            chunk_actions, normalize_embeddings=True,
            show_progress_bar=True, batch_size=64,
        )
        del model
        import gc; gc.collect()
    else:
        print("\n[Step 1] 임베딩 일괄 생성 중 (완료 후 모델 해제)...")
        model = SentenceTransformer(EMBED_MODEL)
        concept_embs = model.encode(
            [c['embed_text'] for c in concepts],
            normalize_embeddings=True, show_progress_bar=False, batch_size=64,
        )
        print(f"    성취기준 임베딩: {concept_embs.shape}")
        chunk_embs = model.encode(
            chunk_actions, normalize_embeddings=True,
            show_progress_bar=True, batch_size=64,
        )
        print(f"    청크 임베딩: {chunk_embs.shape}")
        # 성취기준 임베딩 캐시 저장 (재실행 시 재사용)
        np.savez(EMBED_CACHE_FILE, concept_embs=concept_embs)
        print(f"    임베딩 캐시 저장: {EMBED_CACHE_FILE}")
        del model
        import gc; gc.collect()

    print("    BGE-M3 모델 해제 완료 (메모리 확보)")

    # 전체 유사도 행렬 한번에 계산
    all_sims = cosine_similarity(chunk_embs, concept_embs)  # (N_pending, N_concepts)
    del chunk_embs  # 유사도 계산 후 즉시 해제
    gc.collect()
    print(f"    유사도 행렬: {all_sims.shape}")

    # ── Step 2~3: LLM 매핑 루프 ───────────────────────────
    print("\n[Step 2~3] LLM 매핑 시작 ---")
    warn_count = 0
    for idx, chunk in enumerate(pending):
        sims = all_sims[idx]
        top_idx = np.argsort(sims)[-TOP_K:][::-1]
        candidates = [
            {**concepts[i], 'sim': round(float(sims[i]), 4)}
            for i in top_idx
        ]
        top1_sim = candidates[0]['sim']

        fname = os.path.basename(chunk['file'])
        print(f"  ({idx+1}/{len(pending)}) {fname} S{chunk['step_number']} "
              f"[top1_sim={top1_sim:.3f}]", flush=True)

        # LLM 호출
        llm_result = map_and_name(
            chunk['raw_action'],
            chunk['sub_calculations'],
            candidates,
        )

        if llm_result and 'concept_id' in llm_result:
            concept_id    = llm_result.get('concept_id', candidates[0]['id'])
            canonical     = llm_result.get('canonical_name', chunk['raw_action'])
            reason        = llm_result.get('reason', '')

            # concept_id 유효성 검증 (후보에 없으면 top-1)
            valid_ids = {c['id'] for c in candidates}
            if concept_id not in valid_ids:
                concept_id = candidates[0]['id']
                reason += " [fallback: 유효하지 않은 ID → top-1]"

            # canonical_name 형식 검증
            valid, issue = validate_canonical(canonical)
            if not valid:
                warn_count += 1
                print(f"    ⚠️  canonical 형식 문제: {issue} → '{canonical[:40]}'")

            print(f"    → [{concept_id}] {canonical[:55]}")
        else:
            # LLM 실패: vector top-1 fallback
            concept_id = candidates[0]['id']
            canonical  = chunk['raw_action'][:45]
            reason     = "LLM 실패 - vector top-1 fallback"
            print(f"    ⚠️  LLM 실패 fallback: {concept_id}")

        results.append({
            # Abstract Layer (검색·클러스터링용)
            'concept_id':     concept_id,
            'canonical_name': canonical,
            'reason':         reason,
            'top1_sim':       top1_sim,

            # Concrete Layer (문항 맥락 보존)
            'raw_action':        chunk['raw_action'],
            'sub_calculations':  chunk['sub_calculations'],

            # 메타
            'file':        chunk['file'],
            'step_number': chunk['step_number'],
            'top5_candidates': [
                {'id': c['id'], 'sim': c['sim']} for c in candidates
            ],
        })
        done_keys.add(f"{chunk['file']}_{chunk['step_number']}")

        # 10개마다 저장
        if (idx + 1) % 10 == 0:
            with open(RESULT_FILE, 'w') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

    # 최종 저장
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # ── 요약 ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"✅ 완료! 총 {len(results)}개 매핑")
    print(f"   canonical 형식 경고: {warn_count}건")
    print(f"   결과: {RESULT_FILE}")

    # 성취기준별 집계
    from collections import Counter
    id_counts = Counter(r['concept_id'] for r in results)
    print(f"\n성취기준별 Top 10:")
    for cid, cnt in id_counts.most_common(10):
        name = next((c['name'][:30] for c in concepts if c['id'] == cid), '')
        print(f"  [{cid:25s}] {cnt:4d}개 | {name}")

    print(f"\n💡 다음 단계: canonical_name 클러스터링 → 병합/분리 대상 추출")


if __name__ == "__main__":
    main()
