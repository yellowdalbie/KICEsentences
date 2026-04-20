"""
compare_search.py
=================
A/B 실험: 3-tier vs 1-tier 임베딩 검색 결과 비교

사용법:
    python3 compare_search.py              # 대화형 모드 (step_id 직접 입력)
    python3 compare_search.py --list 20   # 무작위 20개 step 목록 출력
    python3 compare_search.py --id 123    # step_id=123으로 바로 비교
"""

import argparse
import sqlite3
import random
import numpy as np

VEC_3TIER = 'kice_step_vectors.npz'
VEC_1TIER = 'kice_step_vectors_1tier.npz'
DB_FILE   = 'kice_database.sqlite'
TOP_K     = 10


def load_vec(path):
    data = np.load(path, allow_pickle=True)
    return {k: data[k] for k in data.files}


def cosine_search(vec_data, q_idx, top_k):
    q_vec = vec_data['vectors'][q_idx]
    sims  = np.dot(vec_data['vectors'], q_vec)
    sims[q_idx] = -1.0
    top   = np.argsort(sims)[::-1][:top_k]
    return [(int(vec_data['step_ids'][i]),
             str(vec_data['problem_ids'][i]),
             int(vec_data['step_numbers'][i]),
             str(vec_data['concept_ids'][i]),
             round(float(sims[i]), 4)) for i in top]


def get_title(conn, step_id):
    row = conn.execute(
        "SELECT step_title FROM steps WHERE step_id=?", (step_id,)
    ).fetchone()
    return row[0] if row else '(없음)'


def compare(conn, a_data, b_data, step_id):
    ids_a = a_data['step_ids']
    matches = np.where(ids_a == step_id)[0]
    if len(matches) == 0:
        print(f"  step_id {step_id}를 찾을 수 없습니다.")
        return

    q_idx   = int(matches[0])
    q_title = get_title(conn, step_id)
    q_prob  = str(a_data['problem_ids'][q_idx])
    q_cpt   = str(a_data['concept_ids'][q_idx])

    print(f"\n{'='*70}")
    print(f"  쿼리  step_id={step_id}  문항={q_prob}")
    print(f"  타이틀: {q_title}")
    print(f"  CPT:   {q_cpt}")
    print(f"{'='*70}")

    res_a = cosine_search(a_data, q_idx, TOP_K)

    ids_b = b_data['step_ids']
    q_idx_b = int(np.where(ids_b == step_id)[0][0])
    res_b = cosine_search(b_data, q_idx_b, TOP_K)

    print(f"\n{'─'*34} A: 3-tier {'─'*26}  {'─'*34} B: 1-tier {'─'*26}")
    header = f"  {'순위':<4} {'step':>5} {'문항':<24} {'CPT':<22} {'유사도':>6}"
    print(f"{header}  {header}")
    print(f"  {'─'*66}  {'─'*66}")

    for rank, (ra, rb) in enumerate(zip(res_a, res_b), 1):
        sid_a, pid_a, sno_a, cpt_a, sim_a = ra
        sid_b, pid_b, sno_b, cpt_b, sim_b = rb
        ta = get_title(conn, sid_a)[:30]
        tb = get_title(conn, sid_b)[:30]
        same_a = '✓' if cpt_a == q_cpt else ' '
        same_b = '✓' if cpt_b == q_cpt else ' '
        line_a = f"  {rank:<4} {sid_a:>5} {pid_a:<16}[S{sno_a}] {same_a}{cpt_a:<20} {sim_a:>6.4f}"
        line_b = f"  {rank:<4} {sid_b:>5} {pid_b:<16}[S{sno_b}] {same_b}{cpt_b:<20} {sim_b:>6.4f}"
        print(f"{line_a}  {line_b}")

    print(f"\n  타이틀 상세")
    print(f"  {'순위':<4} {'A (3-tier)':<40}  {'B (1-tier)':<40}")
    print(f"  {'─'*86}")
    for rank, (ra, rb) in enumerate(zip(res_a, res_b), 1):
        ta = get_title(conn, ra[0])[:38]
        tb = get_title(conn, rb[0])[:38]
        print(f"  {rank:<4} {ta:<40}  {tb:<40}")

    # CPT 일치율 요약
    match_a = sum(1 for r in res_a if r[3] == q_cpt)
    match_b = sum(1 for r in res_b if r[3] == q_cpt)
    print(f"\n  CPT 일치 (top-{TOP_K}):  A(3-tier)={match_a}/{TOP_K}   B(1-tier)={match_b}/{TOP_K}")


def list_steps(conn, n):
    rows = conn.execute(
        "SELECT step_id, problem_id, step_number, action_concept_id, step_title "
        "FROM steps WHERE step_title IS NOT NULL ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()
    print(f"\n{'step_id':>8}  {'문항':<24}  {'S#':>3}  {'CPT':<24}  타이틀")
    print('─' * 90)
    for r in rows:
        print(f"{r[0]:>8}  {r[1]:<24}  {r[2]:>3}  {r[3] or '':24}  {(r[4] or '')[:35]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', type=int, metavar='N', help='무작위 N개 step 목록')
    parser.add_argument('--id',   type=int, metavar='STEP_ID', help='지정 step_id 비교')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_FILE)

    if args.list:
        list_steps(conn, args.list)
        conn.close()
        return

    import os
    if not os.path.exists(VEC_1TIER):
        print(f"[오류] {VEC_1TIER} 없음 → 먼저 python3 build_vectors_1tier.py 실행")
        conn.close()
        return

    print("벡터 파일 로드 중...")
    a_data = load_vec(VEC_3TIER)
    b_data = load_vec(VEC_1TIER)

    if args.id:
        compare(conn, a_data, b_data, args.id)
    else:
        # 대화형 모드
        print("\n[ A/B 비교 도구 ]  종료: q 또는 Ctrl+C")
        print("step_id를 모르면 먼저:  python3 compare_search.py --list 30")
        while True:
            try:
                raw = input("\n비교할 step_id 입력 (q=종료): ").strip()
                if raw.lower() == 'q':
                    break
                compare(conn, a_data, b_data, int(raw))
            except (ValueError, KeyboardInterrupt):
                break

    conn.close()


if __name__ == '__main__':
    main()
