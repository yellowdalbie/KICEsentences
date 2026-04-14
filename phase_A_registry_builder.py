"""
Phase A-2 Step 4: atom_registry.json 생성
==========================================
사람이 편집 완료한 atom_registry_review.md를 파싱하여
atom_registry.json을 생성한다.

입력: atom_registry_review.md (편집 완료)
      .build_cache/phase_A/clusters_named.json (멤버 정보)
출력: atom_registry.json

실행: python3 phase_A_registry_builder.py
다음: Phase A-3 (재분류 스크립트)
"""

import json, re, sys
from collections import defaultdict

REVIEW_FILE   = 'atom_registry_review.md'
NAMED_FILE    = '.build_cache/phase_A/clusters_named.json'
OUTPUT_FILE   = 'atom_registry.json'

# atom_id prefix: concept_id → 짧은 코드
CONCEPT_PREFIX = {
    '9수':     'MID',
    '10공수1': 'CM1',
    '10공수2': 'CM2',
    '12대수':  'ALG',
    '12미적Ⅰ': 'CA1',
    '12확통':  'STA',
}

def concept_to_prefix(concept_id):
    for prefix, code in CONCEPT_PREFIX.items():
        if concept_id.startswith(prefix):
            return code
    return 'ETC'


def parse_review_md(path):
    """
    마크다운에서 클러스터 섹션 파싱.
    반환: list of {cluster_id, concept_id, canonical_name, anchor_term, status}
    """
    with open(path) as f:
        content = f.read()

    # 섹션 분리: ### 으로 시작하는 헤더
    sections = re.split(r'\n(?=### )', content)

    entries = []
    for section in sections:
        if '<!-- cluster_id:' not in section:
            continue

        # STATUS: DELETE 확인
        if 'STATUS: DELETE' in section:
            continue

        # cluster_id 추출
        m = re.search(r'<!-- cluster_id: (.+?) -->', section)
        if not m:
            continue
        cluster_id_raw = m.group(1).strip()
        # 숫자면 int로
        try:
            cluster_id = int(cluster_id_raw)
        except ValueError:
            cluster_id = cluster_id_raw  # NR-N 형태

        # 헤더에서 concept_id 추출
        header_m = re.search(r'### (?:클러스터|NR) .+?\| (.+?) \|', section)
        if not header_m:
            # needs_review 헤더 형식
            header_m = re.search(r'### NR .+?\| (.+?)(?:\n| →)', section)
        concept_id = header_m.group(1).strip() if header_m else 'UNKNOWN'

        # concept_id_review (NR 항목) 처리
        changed_m = re.search(r'→ \*\*(.+?)\*\*', section)
        if changed_m:
            concept_id = changed_m.group(1).strip()

        # 제안 이름 (사람이 편집한 값)
        cn_m = re.search(r'^제안 이름: (.+)$', section, re.MULTILINE)
        canonical_name = cn_m.group(1).strip() if cn_m else None

        # anchor_term
        anchor_m = re.search(r'^anchor: (.+)$', section, re.MULTILINE)
        anchor_term = anchor_m.group(1).strip() if anchor_m else None

        if not canonical_name or canonical_name == '(미결정)':
            print(f"  [경고] cluster {cluster_id}: canonical_name 미결정 → 건너뜀")
            continue

        entries.append({
            'cluster_id':    cluster_id,
            'concept_id':    concept_id,
            'canonical_name': canonical_name,
            'anchor_term':   anchor_term,
        })

    return entries


def load_instance_counts(named_file, entries):
    """clusters_named.json에서 각 cluster_id의 size를 가져온다."""
    with open(named_file) as f:
        named = json.load(f)

    size_map = {}
    for c in named.get('clusters', []) + named.get('needs_review', []):
        size_map[c['cluster_id']] = c.get('size', 1)

    return size_map


def assign_atom_ids(entries):
    """concept_id별로 순번을 매겨 atom_id를 부여한다."""
    counter = defaultdict(int)
    result  = []

    # concept_id 순서대로 정렬 후 번호 부여
    sorted_entries = sorted(entries, key=lambda x: x['concept_id'])

    for e in sorted_entries:
        prefix = concept_to_prefix(e['concept_id'])
        counter[e['concept_id']] += 1
        atom_id = f"{prefix}-{counter[e['concept_id']]:03d}"
        result.append({**e, 'atom_id': atom_id})

    return result


def main():
    print("Phase A-2 Step 4: Registry Builder")
    print(f"  검토 파일: {REVIEW_FILE}")

    # 파싱
    entries = parse_review_md(REVIEW_FILE)
    print(f"  파싱된 원자 수: {len(entries)}개")

    if not entries:
        print("[오류] 파싱된 항목이 없습니다. 검토 파일을 확인하세요.")
        sys.exit(1)

    # instance_count 추가
    size_map = load_instance_counts(NAMED_FILE, entries)
    for e in entries:
        e['instance_count'] = size_map.get(e['cluster_id'], 0)

    # atom_id 부여
    registry = assign_atom_ids(entries)

    # 저장
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    # 요약
    by_concept = defaultdict(list)
    for a in registry:
        by_concept[a['concept_id']].append(a)

    print(f"\n=== atom_registry 생성 완료 ===")
    print(f"총 원자 수: {len(registry)}개")
    print(f"concept_id 수: {len(by_concept)}개")
    print(f"\nconcept_id별 원자 수 (상위 10):")
    for cid, atoms in sorted(by_concept.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {cid}: {len(atoms)}개")
    print(f"\n출력: {OUTPUT_FILE}")
    print("다음: Phase A-3 재분류 스크립트")


if __name__ == '__main__':
    main()
