"""
build_trigger_clusters.py
=========================
트리거 카테고리명을 BGE-m3-ko로 임베딩하고 계층적 클러스터링으로 묶습니다.

트리거 형식: "[카테고리명] 구체조건(LaTeX)"
→ "[카테고리명]" 부분만 추출하여 임베딩 (뒤의 LaTeX/수식 무시)
→ 같은 수학적 상황을 서로 다른 표현으로 기술한 카테고리들을 하나의 클러스터로 묶음

출력:
  trigger_clusters.json  - {"trigger_text": cluster_id, ...}  (2258개 트리거 전체)
  step_clusters.json     - {"step_id": cluster_id, ...}       (스텝별 주 클러스터)

사용법:
  python3 build_trigger_clusters.py
  python3 build_trigger_clusters.py --threshold 0.80
  python3 build_trigger_clusters.py --threshold 0.90

클러스터링 방식:
  - 1017개 고유 카테고리명 → BGE 임베딩 → average linkage 계층적 클러스터링
  - 임계값이 높을수록 잘게 쪼개짐 (0.90), 낮을수록 크게 묶임 (0.80)
"""

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict

import numpy as np
from sentence_transformers import SentenceTransformer
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist

DB_FILE = 'kice_database.sqlite'
MODEL_NAME = 'dragonkue/BGE-m3-ko'
TRIGGER_CLUSTERS_FILE = 'trigger_clusters.json'
STEP_CLUSTERS_FILE = 'step_clusters.json'
TRIGGER_VECS_FILE = 'trigger_category_vectors.npz'

# "[카테고리명]" 에서 카테고리명 추출
_CAT_PATTERN = re.compile(r'^\[([^\]]+)\]')


def extract_category(trigger_text: str) -> str:
    """트리거 텍스트에서 브라켓 카테고리명만 추출. 없으면 전체 반환."""
    m = _CAT_PATTERN.match(trigger_text)
    return m.group(1).strip() if m else trigger_text.strip()


def load_data(conn):
    """트리거 텍스트 전체와 step_id → 첫 번째 트리거 매핑 로드"""
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute('SELECT trigger_id, trigger_text FROM triggers ORDER BY trigger_id')
    triggers = cur.fetchall()

    # step_id → 첫 번째 trigger_text (trigger_id 오름차순 기준)
    cur.execute('''
        SELECT st.step_id, t.trigger_text
        FROM step_triggers st
        JOIN triggers t ON st.trigger_id = t.trigger_id
        ORDER BY st.step_id, st.trigger_id
    ''')
    rows = cur.fetchall()

    step_primary_trigger = {}
    for row in rows:
        sid = row['step_id']
        if sid not in step_primary_trigger:
            step_primary_trigger[sid] = row['trigger_text']

    return triggers, step_primary_trigger


def embed_categories(unique_categories: list) -> np.ndarray:
    """BGE-m3-ko로 카테고리명 임베딩 (L2 정규화)"""
    print(f"[1/4] BGE-m3-ko 모델 로드 중...")
    model = SentenceTransformer(MODEL_NAME)
    print(f"[2/4] {len(unique_categories)}개 고유 카테고리명 임베딩 중...")
    vectors = model.encode(
        unique_categories,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    return vectors


def cluster_categories(vectors: np.ndarray, threshold: float) -> np.ndarray:
    """average linkage 계층적 클러스터링. cluster label 배열(1-indexed) 반환"""
    print(f"[3/4] 계층적 클러스터링 중 (threshold={threshold})...")
    if len(vectors) == 1:
        return np.array([1])
    dist_condensed = pdist(vectors, metric='cosine')
    Z = linkage(dist_condensed, method='average')
    distance_threshold = 1.0 - threshold
    return fcluster(Z, t=distance_threshold, criterion='distance')


def print_stats(labels, unique_categories, threshold):
    n_clusters = len(set(labels))
    size_dist = Counter(labels)
    sizes = sorted(size_dist.values(), reverse=True)
    singletons = sum(1 for s in sizes if s == 1)
    median_size = sizes[len(sizes) // 2]
    print(f"\n  [threshold={threshold}] 결과")
    print(f"  고유 카테고리명  : {len(unique_categories)}개")
    print(f"  클러스터 수      : {n_clusters}개")
    print(f"  최대 클러스터    : {sizes[0]}개")
    print(f"  중앙값           : {median_size}개")
    print(f"  싱글톤           : {singletons}개 ({singletons/n_clusters*100:.1f}%)")

    # 상위 5개 클러스터 내용 출력
    cluster_members = defaultdict(list)
    for cat, label in zip(unique_categories, labels):
        cluster_members[label].append(cat)

    top5 = sorted(cluster_members.items(), key=lambda x: -len(x[1]))[:5]
    print(f"\n  상위 5개 클러스터:")
    for cid, members in top5:
        print(f"    [클러스터 {cid}] {len(members)}개:")
        for m in members[:4]:
            print(f"      - {m}")
        if len(members) > 4:
            print(f"      ... +{len(members)-4}개")


def main():
    parser = argparse.ArgumentParser(description='트리거 카테고리 클러스터링')
    parser.add_argument('--threshold', type=float, default=0.85,
                        help='코사인 유사도 임계값 (기본값: 0.85, 범위: 0.70~0.95)')
    args = parser.parse_args()

    print(f"=== 트리거 클러스터링 (threshold={args.threshold}) ===\n")

    conn = sqlite3.connect(DB_FILE)
    triggers, step_primary_trigger = load_data(conn)
    conn.close()

    trigger_texts = [row['trigger_text'] for row in triggers]
    print(f"트리거 전체: {len(trigger_texts)}개")
    print(f"스텝 매핑 수: {len(step_primary_trigger)}개")

    # 카테고리명 추출 및 고유화
    cat_map = {t: extract_category(t) for t in trigger_texts}  # trigger → category
    unique_categories = sorted(set(cat_map.values()))
    print(f"고유 카테고리명: {len(unique_categories)}개\n")

    # 임베딩
    vectors = embed_categories(unique_categories)

    # 클러스터링
    labels = cluster_categories(vectors, args.threshold)
    print_stats(labels, unique_categories, args.threshold)

    # category → cluster_id 매핑
    cat_to_cluster = {cat: int(labels[i]) for i, cat in enumerate(unique_categories)}

    # trigger_clusters.json: trigger_text → cluster_id
    trigger_cluster_map = {
        t: cat_to_cluster[cat]
        for t, cat in cat_map.items()
    }
    with open(TRIGGER_CLUSTERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(trigger_cluster_map, f, ensure_ascii=False, indent=2)

    # step_clusters.json: step_id(str) → cluster_id
    # trigger_category_vectors.npz: category → L2 정규화 벡터 (연속 유사도 계산용)
    step_cluster_map = {}
    # step_id(str) → category 벡터 인덱스
    step_cat_idx_map = {}  # step_id → index in unique_categories
    cat_to_idx = {cat: i for i, cat in enumerate(unique_categories)}

    missing = 0
    for step_id, trigger_text in step_primary_trigger.items():
        cat = cat_map.get(trigger_text)
        if cat is not None and trigger_text in trigger_cluster_map:
            step_cluster_map[str(step_id)] = trigger_cluster_map[trigger_text]
            step_cat_idx_map[str(step_id)] = cat_to_idx[cat]
        else:
            missing += 1

    with open(STEP_CLUSTERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(step_cluster_map, f, ensure_ascii=False, indent=2)

    # trigger_category_vectors.npz 저장
    # step_trigger_vecs: step_id 순서로 정렬된 트리거 카테고리 벡터 배열
    sorted_step_ids = sorted(step_cat_idx_map.keys(), key=lambda x: int(x))
    step_ids_arr = np.array([int(s) for s in sorted_step_ids], dtype=np.int32)
    step_vecs_arr = np.array(
        [vectors[step_cat_idx_map[s]] for s in sorted_step_ids],
        dtype=np.float32
    )
    np.savez(
        TRIGGER_VECS_FILE,
        step_ids=step_ids_arr,
        step_trigger_vecs=step_vecs_arr,
        categories=np.array(unique_categories, dtype=object),
        category_vecs=vectors.astype(np.float32),
    )

    print(f"\n[4/4] 저장 완료")
    print(f"  {TRIGGER_CLUSTERS_FILE}  ({len(trigger_cluster_map)}개 트리거)")
    print(f"  {STEP_CLUSTERS_FILE}  ({len(step_cluster_map)}개 스텝)")
    print(f"  {TRIGGER_VECS_FILE}  ({len(step_ids_arr)}개 스텝 트리거 벡터)")
    if missing:
        print(f"  [경고] 매핑 누락: {missing}개 스텝")

    print(f"\n완료! 다음 단계: dashboard.py 재시작")


if __name__ == '__main__':
    main()
