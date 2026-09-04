"""정적 패키지용 '유사 스텝' 표 사전 계산.

유사 스텝 검색은 1024차원 스텝 벡터(8.7MB)와 트리거 벡터(13.5MB)가 필요해
그대로 패키지에 넣으면 22MB가 늘어난다. 결과는 스텝마다 고정이므로 빌드 때
미리 계산해 상위 N개만 저장하면 1MB 아래로 줄어든다.

정확성을 위해 서버가 쓰는 HybridSearchEngine 을 그대로 불러 사용한다.
따라서 결과가 온라인과 동일하다.

출력: dist_static/data/similar.js
"""

import base64
import json
import os
import sys
import time

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'dist_static', 'data')
TOP_N = 50

sys.path.insert(0, BASE)
from search_engine import HybridSearchEngine  # noqa: E402


def load_vec_data():
    """dashboard.py 의 _vec_data 구성을 그대로 재현한다."""
    d = np.load(os.path.join(BASE, 'kice_step_vectors.npz'), allow_pickle=True)
    vec = {
        'step_ids': d['step_ids'],
        'vectors': d['vectors'],
        'concept_ids': d['concept_ids'],
        'problem_ids': d['problem_ids'],
        'step_numbers': d['step_numbers'],
        'step_texts': d['step_texts'],
    }

    clusters_path = os.path.join(BASE, 'step_clusters.json')
    if os.path.exists(clusters_path):
        with open(clusters_path, encoding='utf-8') as f:
            cl = json.load(f)
        mapping = {}
        for cid, info in (cl.get('clusters') or {}).items():
            for sid in info.get('step_ids', []):
                mapping[int(sid)] = int(cid)
        vec['step_cluster_ids'] = np.array(
            [mapping.get(int(s), -1) for s in vec['step_ids']], dtype=np.int32)

    tvec_path = os.path.join(BASE, 'trigger_category_vectors.npz')
    if os.path.exists(tvec_path):
        t = np.load(tvec_path, allow_pickle=True)
        tv = t['step_trigger_vecs']
        t_ids = {int(s): i for i, s in enumerate(t['step_ids'])}
        arr = np.zeros((len(vec['step_ids']), tv.shape[1]), dtype=np.float32)
        for i, s in enumerate(vec['step_ids']):
            row = t_ids.get(int(s))
            if row is not None:
                arr[i] = tv[row]
        vec['step_trigger_vecs'] = arr
    return vec


def main():
    os.makedirs(OUT, exist_ok=True)
    print('=== 유사 스텝 표 사전 계산 ===')
    vec = load_vec_data()
    eng = HybridSearchEngine(vec)
    step_ids = [int(s) for s in vec['step_ids']]
    n = len(step_ids)
    print(f'  대상 스텝 {n:,}개 · 각 Top-{TOP_N}')

    ids = np.zeros((n, TOP_N), dtype=np.uint16)     # 스텝 배열의 '인덱스'
    scores = np.zeros((n, TOP_N), dtype=np.float32)
    pos = {sid: i for i, sid in enumerate(step_ids)}

    t0 = time.time()
    for i, sid in enumerate(step_ids):
        res = eng.search_steps(sid, top_k=TOP_N)
        rows = res.get('results', [])
        for j, r in enumerate(rows[:TOP_N]):
            ids[i, j] = pos.get(int(r['step_id']), 0)
            scores[i, j] = float(r.get('hybrid_score', r.get('score', 0.0)))
        if (i + 1) % 250 == 0:
            el = time.time() - t0
            print(f'    {i+1:,}/{n:,}  ({el:.0f}초 경과, 남은 예상 {el/(i+1)*(n-i-1):.0f}초)')

    lo, hi = float(scores.min()), float(scores.max())
    q = np.clip(np.round((scores - lo) / (hi - lo + 1e-12) * 65535), 0, 65535).astype(np.uint16)

    payload = {
        'N': TOP_N,
        'stepIds': step_ids,
        'idx': base64.b64encode(ids.tobytes()).decode('ascii'),
        'scr': base64.b64encode(q.tobytes()).decode('ascii'),
        'lo': lo, 'hi': hi,
    }
    path = os.path.join(OUT, 'similar.js')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('// 유사 스텝 표 (빌드 시 사전 계산 — 온라인과 동일 결과)\n')
        f.write('window.KL_SIMILAR=')
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print(f'\n  similar.js  {os.path.getsize(path)/1e6:.2f} MB  '
          f'(점수 범위 [{lo:.4f}, {hi:.4f}], {time.time()-t0:.0f}초 소요)')


if __name__ == '__main__':
    main()
