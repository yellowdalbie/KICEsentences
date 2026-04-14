"""
Phase A-3: Final Atom Classification
=====================================
atom_registry.json을 기반으로 phaseA_v7_mapped.json의 각 청크를
가장 유사한 원자(atom)에 매핑하여 phaseA_final_mapped.json을 생성한다.

동작 방식:
  1. atom_registry.json의 canonical_name을 임베딩
  2. 각 청크의 raw_action을 임베딩 (V7 캐시 재활용)
  3. concept_id로 1차 필터링 → 코사인 유사도로 최근접 원자 선택
  4. atom_id + atom_sim + low_confidence 필드 추가

추가 필드:
  atom_id        : 매핑된 원자 ID (e.g., CA1-001)
  atom_name      : 원자 canonical_name
  atom_sim       : 코사인 유사도 (0~1)
  low_confidence : atom_sim < LOW_CONF_THRESHOLD 이면 True

입력: phaseA_v7_mapped.json + atom_registry.json
출력: phaseA_final_mapped.json

실행: python3 phase_A_final_mapper.py  (atom_registry.json 완성 후)
다음: python3 phase_A_merge_split.py
"""

import json, os
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

MAPPED_FILE       = 'phaseA_v7_mapped.json'
REGISTRY_FILE     = 'atom_registry.json'
OUTPUT_FILE       = 'phaseA_final_mapped.json'

# 임베딩 캐시 경로
CHUNK_EMBED_CACHE = '.build_cache/phase_A/atom_cluster_embeddings.npz'  # V7에서 생성된 캐시
ATOM_EMBED_CACHE  = '.build_cache/phase_A/atom_registry_embeddings.npz'

EMBED_MODEL       = 'dragonkue/BGE-m3-ko'
LOW_CONF_THRESHOLD = 0.50  # 이 값 미만이면 low_confidence=True


def load_chunk_embeddings(chunks):
    """
    V7 캐시에서 raw_action 임베딩을 로드.
    캐시가 없거나 texts가 다르면 재계산.
    """
    raw_actions = [c.get('raw_action', '') for c in chunks]

    if os.path.exists(CHUNK_EMBED_CACHE):
        cache = np.load(CHUNK_EMBED_CACHE, allow_pickle=True)
        cached_texts = list(cache['texts'])
        # needs_review 제외 항목만 캐시에 있으므로 직접 비교 불가 → 재계산 여부 확인
        if len(cached_texts) == len(raw_actions) and cached_texts == raw_actions:
            print(f"  청크 임베딩 캐시 재사용 ({len(raw_actions)}개)")
            return cache['embeddings']

    print(f"  청크 임베딩 생성 중 ({len(raw_actions)}개)...")
    model = SentenceTransformer(EMBED_MODEL)
    embeddings = model.encode(
        raw_actions, normalize_embeddings=True,
        show_progress_bar=True, batch_size=64
    )
    return embeddings


def load_atom_embeddings(registry):
    """
    atom_registry의 canonical_name을 임베딩.
    캐시가 있고 텍스트가 같으면 재사용.
    """
    canonical_names = [a['canonical_name'] for a in registry]

    if os.path.exists(ATOM_EMBED_CACHE):
        cache = np.load(ATOM_EMBED_CACHE, allow_pickle=True)
        cached_texts = list(cache['texts'])
        if cached_texts == canonical_names:
            print(f"  원자 임베딩 캐시 재사용 ({len(canonical_names)}개)")
            return cache['embeddings']

    print(f"  원자 임베딩 생성 중 ({len(canonical_names)}개)...")
    model = SentenceTransformer(EMBED_MODEL)
    embeddings = model.encode(
        canonical_names, normalize_embeddings=True,
        show_progress_bar=True, batch_size=64
    )
    os.makedirs(os.path.dirname(ATOM_EMBED_CACHE), exist_ok=True)
    np.savez(ATOM_EMBED_CACHE,
             embeddings=embeddings,
             texts=np.array(canonical_names, dtype=object))
    print(f"  캐시 저장: {ATOM_EMBED_CACHE}")
    return embeddings


def main():
    print("=" * 55)
    print("Phase A-3: Final Atom Classification")
    print("=" * 55)

    # ── 데이터 로드 ──────────────────────────────────────
    with open(MAPPED_FILE) as f:
        chunks = json.load(f)
    with open(REGISTRY_FILE) as f:
        registry = json.load(f)

    print(f"\n청크: {len(chunks)}개")
    print(f"원자 레지스트리: {len(registry)}개")

    # ── concept_id별 원자 인덱스 구성 ──────────────────
    # concept_id → list of (atom_index, atom_dict)
    from collections import defaultdict
    atoms_by_concept = defaultdict(list)
    for i, atom in enumerate(registry):
        atoms_by_concept[atom['concept_id']].append((i, atom))

    print(f"\nconcept_id별 원자 분포 (상위 10):")
    for cid, atoms in sorted(atoms_by_concept.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {cid}: {len(atoms)}개 원자")

    # ── 임베딩 로드 ───────────────────────────────────────
    print("\n[1] 임베딩 준비...")

    # 청크 임베딩: needs_review 포함 전체
    chunk_embeddings = load_chunk_embeddings(chunks)

    # 원자 임베딩
    atom_embeddings = load_atom_embeddings(registry)

    # ── 매핑 수행 ─────────────────────────────────────────
    print("\n[2] 원자 매핑 수행...")

    results = []
    no_match = 0
    low_conf = 0

    for i, chunk in enumerate(chunks):
        if i % 500 == 0:
            print(f"  {i}/{len(chunks)}...")

        concept_id = chunk.get('concept_id')
        chunk_emb  = chunk_embeddings[i].reshape(1, -1)

        # concept_id로 후보 원자 필터링
        candidates = atoms_by_concept.get(concept_id, [])

        if not candidates:
            # concept_id 매치 없음 → 전체 레지스트리에서 검색
            candidates = list(enumerate(registry))
            no_match += 1

        # 후보 임베딩 추출
        cand_indices = [idx for idx, _ in candidates]
        cand_embs    = atom_embeddings[cand_indices]

        # 코사인 유사도 계산
        sims = cosine_similarity(chunk_emb, cand_embs)[0]
        best_local_idx = int(np.argmax(sims))
        best_sim       = float(sims[best_local_idx])
        best_atom      = candidates[best_local_idx][1]

        is_low = best_sim < LOW_CONF_THRESHOLD
        if is_low:
            low_conf += 1

        result = dict(chunk)
        result.update({
            'atom_id':        best_atom['atom_id'],
            'atom_name':      best_atom['canonical_name'],
            'atom_sim':       round(best_sim, 4),
            'low_confidence': is_low,
        })
        results.append(result)

    # ── 저장 ──────────────────────────────────────────────
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # ── 통계 ──────────────────────────────────────────────
    print(f"\n=== 매핑 완료 ===")
    print(f"총 청크: {len(results)}개")
    print(f"concept_id 미매치 (전체 검색): {no_match}개")
    print(f"low_confidence (sim < {LOW_CONF_THRESHOLD}): {low_conf}개")

    # atom_id별 매핑 수 분포
    from collections import Counter
    atom_cnt = Counter(r['atom_id'] for r in results)
    print(f"\n상위 원자 (매핑 수 기준):")
    for atom_id, cnt in atom_cnt.most_common(15):
        atom_name = next((a['canonical_name'] for a in registry if a['atom_id'] == atom_id), '')
        print(f"  {atom_id} ({atom_name[:25]}): {cnt}개")

    sim_vals = [r['atom_sim'] for r in results]
    print(f"\n유사도 분포:")
    for threshold in [0.9, 0.8, 0.7, 0.6, 0.5]:
        cnt = sum(1 for s in sim_vals if s >= threshold)
        print(f"  >= {threshold}: {cnt}개 ({cnt/len(sim_vals)*100:.1f}%)")

    print(f"\n출력: {OUTPUT_FILE}")
    print("다음: python3 phase_A_merge_split.py")


if __name__ == '__main__':
    main()
