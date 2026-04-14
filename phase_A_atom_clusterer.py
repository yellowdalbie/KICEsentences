"""
Phase A-2 Step 1: Concept_id-aware Atom Clustering
===================================================
phaseA_v7_mapped.json의 raw_action을 concept_id별로 클러스터링하여
원자 후보 그룹을 생성한다.

입력: phaseA_v7_mapped.json
출력: .build_cache/phase_A/clusters_raw.json

실행: python3 phase_A_atom_clusterer.py
다음: python3 phase_A_cluster_namer.py
"""

import json, os, numpy as np
from collections import defaultdict
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

MAPPED_FILE   = 'phaseA_v7_mapped.json'
EMBED_CACHE   = '.build_cache/phase_A/atom_cluster_embeddings.npz'
OUTPUT_FILE   = '.build_cache/phase_A/clusters_raw.json'
EMBED_MODEL   = 'dragonkue/BGE-m3-ko'
THRESHOLD     = 0.82   # 코사인 유사도 임계값 (보수적: 분리 편향)

def load_embeddings(texts):
    """임베딩 로드 또는 생성. 텍스트 목록이 캐시와 다르면 재계산."""
    if os.path.exists(EMBED_CACHE):
        cache = np.load(EMBED_CACHE, allow_pickle=True)
        cached_texts = list(cache['texts'])
        if cached_texts == texts:
            print(f"  임베딩 캐시 재사용 ({len(texts)}개)")
            return cache['embeddings']

    print(f"  임베딩 생성 중 ({len(texts)}개)...")
    model = SentenceTransformer(EMBED_MODEL)
    embeddings = model.encode(
        texts, normalize_embeddings=True, show_progress_bar=True, batch_size=64
    )
    os.makedirs(os.path.dirname(EMBED_CACHE), exist_ok=True)
    np.savez(EMBED_CACHE, embeddings=embeddings, texts=np.array(texts, dtype=object))
    print(f"  캐시 저장: {EMBED_CACHE}")
    return embeddings


def cluster_concept(items, embeddings):
    """
    concept_id 내 items를 계층적 클러스터링.
    items: list of (global_index, item_dict)
    embeddings: 전체 normal 항목의 임베딩 배열
    반환: list of member_lists (각 클러스터의 항목 목록)
    """
    if len(items) == 1:
        return [[items[0][1]]]

    indices = [i for i, _ in items]
    embs = embeddings[indices]

    # 코사인 거리 행렬
    sim_matrix  = cosine_similarity(embs)
    np.fill_diagonal(sim_matrix, 1.0)
    dist_matrix = np.clip(1.0 - sim_matrix, 0, None)

    condensed = squareform(dist_matrix, checks=False)
    Z         = linkage(condensed, method='average')
    labels    = fcluster(Z, t=1.0 - THRESHOLD, criterion='distance')

    cluster_map = defaultdict(list)
    for local_idx, (_, item) in enumerate(items):
        cluster_map[labels[local_idx]].append(item)

    return list(cluster_map.values())


def make_member_record(item):
    return {
        'file':               item['file'],
        'step_number':        item['step_number'],
        'raw_action':         item.get('raw_action', ''),
        'canonical_name_v7':  item.get('canonical_name', ''),
        'top1_sim':           round(item.get('top1_sim', 0.0), 4),
    }


def main():
    print("=" * 55)
    print("Phase A-2 Step 1: Atom Clustering")
    print("=" * 55)

    # ── 데이터 로드 ──────────────────────────────────
    with open(MAPPED_FILE) as f:
        data = json.load(f)
    print(f"\n총 항목: {len(data)}개")

    normal  = [x for x in data if not x.get('needs_review')]
    flagged = [x for x in data if x.get('needs_review')]
    print(f"  정상: {len(normal)}개 / needs_review: {len(flagged)}개")

    # ── 임베딩 ───────────────────────────────────────
    print("\n[1] 임베딩 준비...")
    raw_actions = [x.get('raw_action', '') for x in normal]
    embeddings  = load_embeddings(raw_actions)

    # ── concept_id별 클러스터링 ───────────────────────
    print(f"\n[2] concept_id별 계층적 클러스터링 (임계값={THRESHOLD})...")
    by_concept = defaultdict(list)
    for i, item in enumerate(normal):
        by_concept[item['concept_id']].append((i, item))

    all_clusters   = []
    cluster_id     = 0
    concept_stats  = []

    for concept_id in sorted(by_concept.keys()):
        items = by_concept[concept_id]
        groups = cluster_concept(items, embeddings)

        n_clusters = len(groups)
        concept_stats.append((concept_id, len(items), n_clusters))

        for members in groups:
            all_clusters.append({
                'cluster_id':  cluster_id,
                'concept_id':  concept_id,
                'size':        len(members),
                'members':     [make_member_record(m) for m in members],
                # qwen이 채울 필드
                'is_pure':          None,
                'anchor_term':      None,
                'canonical_name':   None,
                'split_proposal':   None,
                'vocab_missing':    False,
            })
            cluster_id += 1

    # ── needs_review 별도 섹션 ────────────────────────
    nr_clusters = []
    for i, item in enumerate(flagged):
        nr_clusters.append({
            'cluster_id':        f'NR-{i}',
            'concept_id':        item.get('concept_id', 'UNKNOWN'),
            'size':              1,
            'members':           [make_member_record(item)],
            'needs_review':      True,
            'is_pure':           None,
            'anchor_term':       None,
            'canonical_name':    None,
            'concept_id_review': None,   # qwen이 concept_id 재검토 결과를 기록
        })

    # ── 저장 ─────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    result = {
        'threshold':          THRESHOLD,
        'total_normal':       len(normal),
        'total_clusters':     len(all_clusters),
        'needs_review_count': len(flagged),
        'clusters':           all_clusters,
        'needs_review':       nr_clusters,
    }
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ── 요약 ─────────────────────────────────────────
    print(f"\n=== 클러스터링 결과 ===")
    print(f"총 클러스터: {len(all_clusters)}개")
    print(f"  단일 항목: {sum(1 for c in all_clusters if c['size']==1)}개")
    print(f"  2개 이상:  {sum(1 for c in all_clusters if c['size']>1)}개")
    print(f"  최대 크기: {max(c['size'] for c in all_clusters)}개")
    print(f"needs_review 별도: {len(flagged)}개")

    print(f"\n--- concept_id별 클러스터 수 (상위 15) ---")
    for cid, n_items, n_cl in sorted(concept_stats, key=lambda x: -x[1])[:15]:
        print(f"  {cid}: {n_items}개 → {n_cl}개 클러스터")

    print(f"\n출력: {OUTPUT_FILE}")
    print("다음: python3 phase_A_cluster_namer.py")

if __name__ == '__main__':
    main()
