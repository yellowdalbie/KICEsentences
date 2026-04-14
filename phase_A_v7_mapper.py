"""
Phase A V7: Real-time Vocab-Checked Mapper
==========================================
V6 대비 변경사항:
  1. canonical_name 형식 완화
     - 기존: "[공식 용어]을 이용한 [조작]" 템플릿 강제 → 억지스러운 결과
     - 변경: 형식 자유, 단 vocab_standard 공식 용어 최소 1개 포함 필수
  2. 실시간 vocab 포함 여부 체크 + 자동 재시도 (최대 2회)
     - 포함 확인 후 통과 → 저장
     - 미포함 → "반드시 [term1 / term2 / ...] 중 하나를 포함하라" 재시도
     - 2회 재시도 후에도 실패 → needs_review: true 플래그 후 저장
  3. 개념어 명명 프롬프트 개선
     - "어떤 수학 개념을 써서, 무엇을 알아냈는가" 중심 자연어 서술
     - 예시 다양화 (형식 다양성)

실행: .venv/bin/python phase_A_v7_mapper.py
출력: phaseA_v7_mapped.json
"""

import json, os, re, gc, requests, numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ─── 설정 ──────────────────────────────────────────────────
RAW_CHUNKS_FILE  = '.build_cache/phase_A/raw_chunks_cache_v3_ollama.json'
CONCEPTS_FILE    = 'concepts.json'
VOCAB_FILE       = 'vocab_standard.json'
RESULT_FILE      = 'phaseA_v7_mapped.json'
CACHE_DIR        = '.build_cache/phase_A'
EMBED_CACHE_FILE = '.build_cache/phase_A/v7_embeddings.npz'
os.makedirs(CACHE_DIR, exist_ok=True)

OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5-coder:14b"
EMBED_MODEL  = 'dragonkue/BGE-m3-ko'
TOP_K        = 5
MAX_RETRY    = 2   # vocab 미포함 시 재시도 횟수


# ─── vocab_standard 로드 ───────────────────────────────────
with open(VOCAB_FILE) as f:
    _vocab_raw = json.load(f)
BANNED_TERMS = _vocab_raw.get('_banned_terms', [])   # 구교육과정 삭제 용어 등
VOCAB_TABLE  = {cid: entry['terms']
                for cid, entry in _vocab_raw.items()
                if not cid.startswith('_')}


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


# ─── vocab 포함 여부 + 금지어 체크 ────────────────────────
def check_vocab(canonical_name: str, concept_id: str) -> tuple[bool, list, list]:
    """
    Returns (ok, required_terms, found_banned)
      ok           : vocab 용어 포함 AND 금지어 미포함이면 True
      required_terms: concept_id의 vocab 용어 목록
      found_banned : canonical_name에서 발견된 금지어 목록
    """
    terms = VOCAB_TABLE.get(concept_id, [])
    has_vocab = any(t in canonical_name for t in terms)
    found_banned = [t for t in BANNED_TERMS if t in canonical_name]
    return has_vocab and not found_banned, terms, found_banned


# ─── 1차 LLM 프롬프트: 성취기준 선택 + 개념어 명명 ─────────
def map_and_name(raw_action, sub_calcs, candidates):
    cand_str = "\n".join([
        f"  [{i+1}] {c['id']}: {c['name']}\n"
        f"       공식 용어: {', '.join(VOCAB_TABLE.get(c['id'], [])[:4])}"
        for i, c in enumerate(candidates)
    ])
    sub_str = "\n".join([f"  - {s}" for s in sub_calcs[:4]])

    prompt = f"""너는 한국 고등학교 수학 교육과정 전문가다.

[풀이 스텝]
행동: "{raw_action}"
세부 계산:
{sub_str}

━━━ 작업 1: 성취기준 선택 ━━━
위 스텝이 사용하는 수학적 원리에 가장 정확한 성취기준을 후보 중 1개 선택하라.
성취기준명과 공식 용어를 수학적으로 꼼꼼히 읽고 판단하라.

후보:
{cand_str}

━━━ 작업 2: canonical_name 작성 ━━━
이 스텝에서 쓰인 수학 개념을 **한 문장**으로 표현하라.

규칙:
  • 선택한 성취기준의 "공식 용어" 중 최소 1개를 반드시 포함
  • "어떤 수학 개념으로 무엇을 알아냈는가"를 자연스럽게 서술
  • 형식에 얽매이지 말 것 — 아래처럼 다양한 표현 가능:
      "등비수열 공비로 인접항 비를 일반화"
      "좌극한·우극한 비교로 극한값 존재 여부 판정"
      "인수분해로 0/0 부정형 극한 해소"
      "점화식 홀짝 분기로 수열 주기 파악"
      "코사인법칙으로 미지 변의 길이 산출"
  • 금지: LaTeX($...$), 변수명(f(x), x=3), 특정 숫자, 보기번호
  • 길이: 10자 이상 40자 이하

반드시 아래 JSON만 반환:
{{
  "concept_id": "선택한 성취기준 ID",
  "canonical_name": "자연스러운 수학 개념 서술",
  "reason": "선택 이유 한 문장"
}}"""
    return call_llm(prompt)


# ─── 재시도 프롬프트: vocab 용어 강제 포함 ─────────────────
def retry_with_vocab(raw_action, sub_calcs, concept_id, concept_name, terms, prev_name, found_banned=None):
    terms_str = " / ".join(f'"{t}"' for t in terms[:5])
    sub_str = "\n".join([f"  - {s}" for s in sub_calcs[:3]])
    banned_note = ""
    if found_banned:
        banned_str = ", ".join(f'"{t}"' for t in found_banned)
        banned_note = f"\n  ⛔ 사용 금지 용어 (교육과정 삭제): {banned_str}"

    prompt = f"""너는 한국 고등학교 수학 교육과정 전문가다.

[풀이 스텝]
행동: "{raw_action}"
세부 계산:
{sub_str}

성취기준: {concept_id} — {concept_name}

이전에 생성한 이름 "{prev_name}"을 다시 작성해야 한다.

아래 공식 용어 중 **반드시 1개 이상**을 자연스럽게 포함하여 작성하라:
  {terms_str}{banned_note}

규칙:
  • 위 공식 용어 중 하나가 반드시 포함되어야 함
  • "어떤 수학 개념으로 무엇을 알아냈는가"를 자연스럽게 서술
  • LaTeX, 변수명, 특정 숫자 금지
  • 10자 이상 40자 이하

반드시 아래 JSON만 반환:
{{
  "canonical_name": "공식 용어 포함 수학 개념 서술"
}}"""
    return call_llm(prompt)


# ─── 메인 ──────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("🎯 Phase A V7: Real-time Vocab-Checked Mapper")
    print("   Top-K=5 | vocab 실시간 체크 | 자동 재시도(최대 2회)")
    print("=" * 60)

    # 성취기준 로드
    with open(CONCEPTS_FILE) as f:
        raw_concepts = json.load(f)
    concepts = []
    for row in raw_concepts:
        if row['id'].startswith('9수'):
            continue
        kws = [k for k in row.get('keywords', []) if isinstance(k, str) and len(k) > 1]
        concepts.append({
            'id':         row['id'],
            'name':       row.get('standard_name', ''),
            'keywords':   kws,
            'embed_text': row.get('standard_name', '') + ' ' + ' '.join(kws[:6])
        })
    print(f"고등학교 성취기준: {len(concepts)}개")

    # 청크 로드
    with open(RAW_CHUNKS_FILE) as f:
        raw_data = json.load(f)
    chunks = []
    for item in raw_data:
        for c in item.get('chunks', []):
            if not isinstance(c, dict) or not c.get('is_core_jump'):
                continue
            chunks.append({
                'file':             item['file'],
                'step_number':      c.get('step_number', 0),
                'raw_action':       c.get('logical_action', ''),
                'sub_calculations': c.get('sub_calculations', []),
            })
    print(f"is_core_jump 청크: {len(chunks)}개")

    # 이어 실행
    if os.path.exists(RESULT_FILE):
        with open(RESULT_FILE) as f:
            results = json.load(f)
        print(f"기 완료: {len(results)}개 → 이어 실행")
    else:
        results = []
    done_keys = {f"{r['file']}_{r['step_number']}" for r in results}
    pending = [c for c in chunks if f"{c['file']}_{c['step_number']}" not in done_keys]
    print(f"신규 대상: {len(pending)}개")

    # 임베딩 (캐시 활용)
    if os.path.exists(EMBED_CACHE_FILE):
        print(f"\n[Step 1] 임베딩 캐시 로드...")
        cached = np.load(EMBED_CACHE_FILE)
        concept_embs = cached['concept_embs']
        print(f"    성취기준 임베딩: {concept_embs.shape}")
        model = SentenceTransformer(EMBED_MODEL)
        chunk_embs = model.encode(
            [c['raw_action'] for c in pending],
            normalize_embeddings=True, show_progress_bar=True, batch_size=64
        )
    else:
        print("\n[Step 1] 임베딩 일괄 생성 중...")
        model = SentenceTransformer(EMBED_MODEL)
        concept_embs = model.encode(
            [c['embed_text'] for c in concepts],
            normalize_embeddings=True, show_progress_bar=False, batch_size=64
        )
        chunk_embs = model.encode(
            [c['raw_action'] for c in pending],
            normalize_embeddings=True, show_progress_bar=True, batch_size=64
        )
        np.savez(EMBED_CACHE_FILE, concept_embs=concept_embs)
        print(f"    임베딩 캐시 저장 완료")

    del model; gc.collect()
    print("    BGE-M3 해제 완료")

    all_sims = cosine_similarity(chunk_embs, concept_embs)
    del chunk_embs; gc.collect()
    print(f"    유사도 행렬: {all_sims.shape}")

    # LLM 매핑 루프
    print("\n[Step 2~3] LLM 매핑 시작 ---")
    needs_review_count = 0
    retry_total = 0

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
              f"[sim={top1_sim:.3f}]", flush=True)

        # 1차 LLM
        llm_result = map_and_name(chunk['raw_action'], chunk['sub_calculations'], candidates)

        needs_review = False
        retry_count = 0

        if llm_result and 'concept_id' in llm_result:
            concept_id   = llm_result.get('concept_id', candidates[0]['id'])
            canonical    = llm_result.get('canonical_name', chunk['raw_action'])
            reason       = llm_result.get('reason', '')

            # concept_id 유효성 검증
            valid_ids = {c['id'] for c in candidates}
            if concept_id not in valid_ids:
                concept_id = candidates[0]['id']
                reason += " [fallback: 유효하지 않은 ID]"

            # 실시간 vocab 체크 + 금지어 체크 + 재시도
            concept_name = next((c['name'] for c in concepts if c['id'] == concept_id), '')
            ok, terms, found_banned = check_vocab(canonical, concept_id)

            while not ok and retry_count < MAX_RETRY:
                retry_count += 1
                retry_total += 1
                reason_str = f"금지어={found_banned}" if found_banned else "vocab 미포함"
                print(f"    ↩ 재시도 {retry_count}/{MAX_RETRY} ({reason_str}): '{canonical[:35]}'")
                retry_result = retry_with_vocab(
                    chunk['raw_action'], chunk['sub_calculations'],
                    concept_id, concept_name, terms, canonical, found_banned
                )
                if retry_result and 'canonical_name' in retry_result:
                    canonical = retry_result['canonical_name']
                    ok, _, found_banned = check_vocab(canonical, concept_id)
                else:
                    break

            if not ok:
                needs_review = True
                needs_review_count += 1
                print(f"    ⚠️  needs_review: '{canonical[:45]}'")
            else:
                print(f"    → [{concept_id}] {canonical[:55]}")
        else:
            concept_id   = candidates[0]['id']
            canonical    = chunk['raw_action'][:45]
            reason       = "LLM 실패 - vector top-1 fallback"
            needs_review = True
            needs_review_count += 1
            print(f"    ⚠️  LLM 실패 fallback: {concept_id}")

        results.append({
            'concept_id':        concept_id,
            'canonical_name':    canonical,
            'needs_review':      needs_review,
            'reason':            reason,
            'retry_count':       retry_count,
            'top1_sim':          top1_sim,
            'raw_action':        chunk['raw_action'],
            'sub_calculations':  chunk['sub_calculations'],
            'file':              chunk['file'],
            'step_number':       chunk['step_number'],
            'top5_candidates':   [{'id': c['id'], 'sim': c['sim']} for c in candidates],
        })
        done_keys.add(f"{chunk['file']}_{chunk['step_number']}")

        if (idx + 1) % 10 == 0:
            with open(RESULT_FILE, 'w') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ 완료! 총 {len(results)}개")
    print(f"   vocab 재시도: {retry_total}건")
    print(f"   needs_review: {needs_review_count}건 ({needs_review_count/len(results)*100:.1f}%)")
    print(f"   결과: {RESULT_FILE}")

    from collections import Counter
    id_counts = Counter(r['concept_id'] for r in results)
    print(f"\n성취기준별 Top 10:")
    for cid, cnt in id_counts.most_common(10):
        name = next((c['name'][:30] for c in concepts if c['id'] == cid), '')
        print(f"  [{cid:25s}] {cnt:4d}개 | {name}")

    print(f"\n💡 다음 단계:")
    print(f"   1. needs_review 항목 검토 → vocab_standard.json 용어 보완")
    print(f"   2. 병합/분리 분석 → 청킹 품질 개선")


if __name__ == "__main__":
    main()
