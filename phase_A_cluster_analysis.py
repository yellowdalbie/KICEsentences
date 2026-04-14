"""
Phase A - Cluster Analysis Script
목적: raw_chunks의 logical_action들을 벡터 클러스터링하여
      자연 군집 구조를 파악하고 LLM 리뷰 대상(대표점)을 추출

실행: .venv/bin/python phase_A_cluster_analysis.py
출력: .build_cache/phase_A/cluster_analysis.json
      .build_cache/phase_A/cluster_review_targets.json (LLM 검토 대상)
"""

import json
import numpy as np
import os
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity

RAW_CHUNKS_FILE = '.build_cache/phase_A/raw_chunks_cache_v3_ollama.json'
CLUSTER_OUTPUT = '.build_cache/phase_A/cluster_analysis.json'
REVIEW_TARGETS = '.build_cache/phase_A/cluster_review_targets.json'
EMBED_MODEL_NAME = 'dragonkue/BGE-m3-ko'

def main():
    print("=" * 55)
    print("🔭 Phase A Cluster Analysis")
    print("=" * 55)

    # 1. 데이터 로드
    with open(RAW_CHUNKS_FILE, 'r') as f:
        data = json.load(f)

    # is_core_jump=True 청크만 추출
    items = []
    for file_item in data:
        fpath = file_item.get('file', '')
        for c in file_item.get('chunks', []):
            if not isinstance(c, dict): continue
            if not c.get('is_core_jump'): continue
            items.append({
                'file': fpath,
                'step_number': c.get('step_number', 0),
                'logical_action': c.get('logical_action', ''),
                'sub_calculations': c.get('sub_calculations', [])
            })

    print(f"\n총 분석 대상: {len(items)}개 핵심 청크")

    # 2. 임베딩 생성
    print("\n[1] 임베딩 생성 중 (BGE-M3)...")
    model = SentenceTransformer(EMBED_MODEL_NAME)
    actions = [it['logical_action'] for it in items]
    embeddings = model.encode(actions, normalize_embeddings=True, show_progress_bar=True)
    print(f"    임베딩 shape: {embeddings.shape}")

    # 3. 최적 클러스터 수 탐색 (실루엣 스코어 기반)
    print("\n[2] 최적 클러스터 수 탐색 (k=10~80)...")
    best_k, best_score = 30, -1
    # 빠른 탐색을 위해 subset 사용
    np.random.seed(42)
    sample_idx = np.random.choice(len(embeddings), min(500, len(embeddings)), replace=False)
    sample_emb = embeddings[sample_idx]

    scores = {}
    for k in [15, 20, 25, 30, 35, 40, 50, 60]:
        km = KMeans(n_clusters=k, random_state=42, n_init=5, max_iter=100)
        labels = km.fit_predict(sample_emb)
        score = silhouette_score(sample_emb, labels)
        scores[k] = round(score, 4)
        print(f"    k={k}: silhouette={score:.4f}")
        if score > best_score:
            best_score = score
            best_k = k

    print(f"\n    ✅ 최적 k = {best_k} (실루엣 스코어: {best_score:.4f})")

    # 4. 전체 데이터에 최적 k 적용
    print(f"\n[3] 전체 {len(embeddings)}개에 KMeans(k={best_k}) 적용 중...")
    km_final = KMeans(n_clusters=best_k, random_state=42, n_init=10, max_iter=300)
    cluster_labels = km_final.fit_predict(embeddings)

    # 5. 클러스터별 대표점(centroid에 가장 가까운 실제 항목) 추출
    print("\n[4] 클러스터 대표점 추출...")
    cluster_data = {}
    for k in range(best_k):
        cluster_data[k] = {'members': [], 'representative': None}

    for i, label in enumerate(cluster_labels):
        cluster_data[label]['members'].append({
            'idx': i,
            'file': items[i]['file'],
            'step_number': items[i]['step_number'],
            'logical_action': items[i]['logical_action']
        })

    centroid_vecs = km_final.cluster_centers_

    review_targets = []
    for k in range(best_k):
        members = cluster_data[k]['members']
        if not members:
            continue

        # 해당 클러스터 멤버들의 임베딩
        member_indices = [m['idx'] for m in members]
        member_embs = embeddings[member_indices]
        centroid = centroid_vecs[k].reshape(1, -1)

        # centroid에 가장 가까운 실제 항목 = 대표점
        sims = cosine_similarity(member_embs, centroid).flatten()
        best_local_idx = np.argmax(sims)
        rep = members[best_local_idx]

        # 다양한 샘플 (대표 외 최대 4개 무작위 선택)
        np.random.seed(k)
        sample_size = min(4, len(members) - 1)
        other_indices = [i for i in range(len(members)) if i != best_local_idx]
        sampled = np.random.choice(other_indices, sample_size, replace=False).tolist() if other_indices else []
        samples = [members[i]['logical_action'] for i in sampled]

        cluster_data[k]['representative'] = rep
        cluster_data[k]['size'] = len(members)
        cluster_data[k]['sample_actions'] = samples

        review_targets.append({
            'cluster_id': k,
            'size': len(members),
            'representative_action': rep['logical_action'],
            'sample_actions': samples,
            'proposed_canonical_name': None,  # LLM 리뷰 후 채울 항목
            'assigned_concept_id': None
        })

    # 크기 내림차순 정렬
    review_targets.sort(key=lambda x: -x['size'])

    # 6. 저장
    os.makedirs('.build_cache/phase_A', exist_ok=True)

    # 전체 클러스터 분석 저장 (items에 cluster label 추가)
    labeled_items = []
    for i, item in enumerate(items):
        labeled_items.append({**item, 'cluster_id': int(cluster_labels[i])})

    with open(CLUSTER_OUTPUT, 'w') as f:
        json.dump({'k': best_k, 'silhouette_scores': scores, 'items': labeled_items}, f, ensure_ascii=False, indent=2)

    with open(REVIEW_TARGETS, 'w') as f:
        json.dump(review_targets, f, ensure_ascii=False, indent=2)

    # 7. 결과 요약 출력
    print("\n[5] 클러스터 구성 요약 (크기 Top 15):")
    for t in review_targets[:15]:
        print(f"    Cluster {t['cluster_id']:2d} ({t['size']:3d}개): {t['representative_action'][:60]}")

    print(f"\n✅ 완료!")
    print(f"   클러스터 분석: {CLUSTER_OUTPUT}")
    print(f"   LLM 리뷰 대상 ({best_k}개): {REVIEW_TARGETS}")
    print(f"\n💡 다음 단계: phase_A_cluster_labeler.py 로 {best_k}개 대표점에만 LLM 호출하여 canonical_name 부여")

if __name__ == '__main__':
    main()
