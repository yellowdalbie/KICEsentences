"""
Phase A-3: Sol Step 병합/분리 후보 자동 생성
=============================================
phaseA_final_mapped.json (원자 재분류 완료)을 읽어
Sol 파일별 Step 구조에서 병합/분리 후보를 탐지한다.

[병합 신호] 동일 Sol Step 내 연속 청크가 같은 atom_id
[분리 신호] 동일 Sol Step 내 청크들이 서로 다른 atom_id

출력: merge_split_proposals.json
      (Phase C에서 사람이 Sol 파일 재작성 시 참고)

주의: 이 스크립트는 후보 목록만 생성한다.
      실제 Sol 파일 구조 변경은 Phase C에서 사람이 결정한다.

입력: phaseA_final_mapped.json + atom_registry.json
출력: merge_split_proposals.json

실행: python3 phase_A_merge_split.py  (Phase A-3 완료 후)
"""

import json
from collections import defaultdict

FINAL_MAPPED  = 'phaseA_final_mapped.json'
REGISTRY_FILE = 'atom_registry.json'
OUTPUT_FILE   = 'merge_split_proposals.json'

def main():
    print("Phase A-3: Merge/Split Candidate Detection")

    with open(FINAL_MAPPED) as f:
        mapped = json.load(f)

    with open(REGISTRY_FILE) as f:
        registry = json.load(f)

    atom_map = {a['atom_id']: a for a in registry}

    # ── Sol 파일별, Step별로 청크 그룹화 ──────────────────
    # key: (file, step_number) → list of chunks
    by_step = defaultdict(list)
    for item in mapped:
        key = (item['file'], item.get('sol_step_number', item['step_number']))
        by_step[key].append(item)

    merge_proposals = []
    split_proposals = []

    for (sol_file, sol_step), chunks in sorted(by_step.items()):
        if len(chunks) < 2:
            continue

        atom_ids = [c.get('atom_id') for c in chunks]

        # 병합 신호: 모든 청크가 같은 atom_id
        if len(set(atom_ids)) == 1 and atom_ids[0] is not None:
            atom = atom_map.get(atom_ids[0], {})
            merge_proposals.append({
                'type':          'MERGE',
                'file':          sol_file,
                'sol_step':      sol_step,
                'chunk_count':   len(chunks),
                'atom_id':       atom_ids[0],
                'canonical_name': atom.get('canonical_name', ''),
                'description':   f"Step {sol_step}의 {len(chunks)}개 청크가 모두 같은 원자 "
                                 f"[{atom_ids[0]}] → 단일 Step으로 통합 검토",
                'chunks':        [{'step_number': c['step_number'],
                                   'raw_action':  c.get('raw_action','')[:60]}
                                  for c in chunks],
            })

        # 분리 신호: 청크들이 서로 다른 atom_id
        elif len(set(a for a in atom_ids if a)) > 1:
            atom_names = {aid: atom_map.get(aid, {}).get('canonical_name', aid)
                          for aid in set(atom_ids) if aid}
            split_proposals.append({
                'type':        'SPLIT',
                'file':        sol_file,
                'sol_step':    sol_step,
                'chunk_count': len(chunks),
                'atom_ids':    list(set(a for a in atom_ids if a)),
                'description': f"Step {sol_step}에 {len(set(a for a in atom_ids if a))}개 다른 원자 "
                               f"→ Step 분리 검토",
                'chunks':      [{'step_number': c['step_number'],
                                 'atom_id':     c.get('atom_id'),
                                 'canonical_name': atom_map.get(c.get('atom_id'),{}).get('canonical_name',''),
                                 'raw_action':  c.get('raw_action','')[:60]}
                                for c in chunks],
            })

    result = {
        'total_merge_candidates': len(merge_proposals),
        'total_split_candidates': len(split_proposals),
        'merge_proposals': sorted(merge_proposals, key=lambda x: x['file']),
        'split_proposals': sorted(split_proposals, key=lambda x: x['file']),
    }

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n=== 병합/분리 후보 탐지 완료 ===")
    print(f"병합 후보 (MERGE): {len(merge_proposals)}개")
    print(f"분리 후보 (SPLIT): {len(split_proposals)}개")

    if merge_proposals:
        print(f"\n병합 후보 상위 5개:")
        for p in merge_proposals[:5]:
            print(f"  {p['file']} Step{p['sol_step']}: {p['canonical_name'][:40]}")

    if split_proposals:
        print(f"\n분리 후보 상위 5개:")
        for p in split_proposals[:5]:
            print(f"  {p['file']} Step{p['sol_step']}: {p['atom_ids']}")

    print(f"\n출력: {OUTPUT_FILE}")
    print("이 파일은 Phase C (Sol 파일 재검토) 시 참고 자료로 사용됩니다.")
    print("실제 Step 구조 변경은 지침서 작성 후 사람이 최종 결정합니다.")


if __name__ == '__main__':
    main()
