"""
Phase A-2 Step 3: 사람 검토용 마크다운 문서 생성
================================================
clusters_named.json을 읽어 atom_registry_review.md를 생성한다.

검토 우선순위:
  [1] is_pure=false   — qwen이 분리 필요하다고 판단한 클러스터
  [2] vocab_missing   — vocab_standard 확장 검토 필요
  [3] 정상 클러스터   — concept_id 순, 크기 내림차순
  [4] needs_review    — concept_id 재검토 포함

편집 방법:
  - "제안 이름:" 줄을 수정하여 canonical_name 확정
  - "anchor:" 줄을 수정하여 anchor_term 확정
  - 그룹 분리: ### 헤더를 복사하여 새 그룹 추가, member_indices 조정
  - 그룹 병합: 두 섹션 중 하나를 삭제하고 남은 것에 멤버 통합
  - 삭제할 클러스터: "STATUS: DELETE" 줄 추가

입력: .build_cache/phase_A/clusters_named.json
출력: atom_registry_review.md

실행: python3 phase_A_review_builder.py
다음: atom_registry_review.md 편집 후 → python3 phase_A_registry_builder.py
"""

import json
from collections import defaultdict

INPUT_FILE  = '.build_cache/phase_A/clusters_named.json'
OUTPUT_FILE = 'atom_registry_review.md'

# concept_id 정렬 순서 (교육과정 순)
CONCEPT_ORDER_PREFIX = [
    '9수', '10공수1', '10공수2', '12대수', '12미적Ⅰ', '12확통'
]

def concept_sort_key(cid):
    for i, prefix in enumerate(CONCEPT_ORDER_PREFIX):
        if cid.startswith(prefix):
            return (i, cid)
    return (99, cid)


def format_members(members, max_show=6):
    lines = []
    for m in members[:max_show]:
        ra = m.get('raw_action', '').replace('\n', ' ')[:80]
        sim = m.get('top1_sim', 0)
        lines.append(f"  - `{ra}` (sim={sim:.3f})")
    if len(members) > max_show:
        lines.append(f"  - *(+{len(members)-max_show}개 생략)*")
    return '\n'.join(lines)


def write_cluster_section(f, cluster, section_num):
    cid     = cluster['cluster_id']
    concept = cluster['concept_id']
    size    = cluster['size']
    cn      = cluster.get('canonical_name') or '(미결정)'
    anchor  = cluster.get('anchor_term') or '(미결정)'
    note    = cluster.get('note') or ''
    split   = cluster.get('split_proposal')
    vocab_m = cluster.get('vocab_missing', False)

    badges = []
    if cluster.get('is_pure') is False:
        badges.append('⚠️ 분리필요')
    if vocab_m:
        badges.append('🔤 vocab확장검토')
    badge_str = ' '.join(badges)

    f.write(f"### 클러스터 {cid} | {concept} | {size}개 {badge_str}\n\n")
    f.write(f"<!-- cluster_id: {cid} -->\n")
    f.write(f"제안 이름: {cn}\n")
    f.write(f"anchor: {anchor}\n")
    if note:
        f.write(f"note: {note}\n")
    f.write(f"\n**멤버 샘플:**\n")
    f.write(format_members(cluster['members']))
    f.write('\n')

    if split:
        f.write(f"\n**분리 제안:**\n")
        for s in split:
            indices = s.get('member_indices', [])
            f.write(f"- 그룹: `{s.get('canonical_name','')}` (anchor: {s.get('anchor_term','')}) → 멤버: {indices}\n")

    f.write('\n---\n\n')


def main():
    print("Phase A-2 Step 3: Review Document Builder")

    with open(INPUT_FILE) as f:
        data = json.load(f)

    clusters    = data.get('clusters', [])
    nr_clusters = data.get('needs_review', [])

    # phase_A_review.py에서 _delete 표시된 항목 제외
    clusters    = [c for c in clusters    if not c.get('_delete')]
    nr_clusters = [c for c in nr_clusters if not c.get('_delete')]

    impure       = [c for c in clusters if c.get('is_pure') is False]
    vocab_miss   = [c for c in clusters if c.get('vocab_missing') and c.get('is_pure') is not False]
    normal_ok    = [c for c in clusters if c.get('is_pure') is not False and not c.get('vocab_missing')]

    # concept_id별로 그룹화 (정상 클러스터)
    by_concept = defaultdict(list)
    for c in normal_ok:
        by_concept[c['concept_id']].append(c)

    total_review = len(impure) + len(vocab_miss) + len(normal_ok) + len(nr_clusters)

    with open(OUTPUT_FILE, 'w') as f:

        # ── 헤더 ─────────────────────────────────────────
        f.write("# Atom Registry 검토 문서\n\n")
        f.write("> **편집 방법**\n")
        f.write("> - `제안 이름:` 줄을 수정하여 canonical_name 확정\n")
        f.write("> - `anchor:` 줄을 수정하여 anchor_term 확정\n")
        f.write("> - 분리: `###` 섹션 복사 후 `member_indices` 조정\n")
        f.write("> - 병합: 두 섹션 중 하나 삭제\n")
        f.write("> - 삭제: `STATUS: DELETE` 줄 추가\n\n")
        f.write(f"**총 클러스터**: {len(clusters)}개 | ")
        f.write(f"**우선 검토**: {len(impure)+len(vocab_miss)}개 | ")
        f.write(f"**needs_review**: {len(nr_clusters)}개\n\n")
        f.write("---\n\n")

        # ── [1] 분리 필요 ────────────────────────────────
        if impure:
            f.write(f"## [1] 분리 필요 클러스터 ({len(impure)}개) ← 우선 검토\n\n")
            f.write("> qwen이 단일 원자가 아닐 수 있다고 판단함. 분리 제안 확인 후 결정.\n\n")
            for i, c in enumerate(sorted(impure, key=lambda x: concept_sort_key(x['concept_id']))):
                write_cluster_section(f, c, i+1)

        # ── [2] vocab 확장 검토 ──────────────────────────
        if vocab_miss:
            f.write(f"## [2] vocab_standard 확장 검토 ({len(vocab_miss)}개)\n\n")
            f.write("> canonical_name에 vocab_standard 공식 용어가 없음.\n")
            f.write("> vocab_standard.json에 용어를 추가하거나 canonical_name을 수정.\n\n")
            for i, c in enumerate(sorted(vocab_miss, key=lambda x: concept_sort_key(x['concept_id']))):
                write_cluster_section(f, c, i+1)

        # ── [3] 정상 클러스터 (concept_id 순) ───────────
        f.write(f"## [3] 정상 클러스터 ({len(normal_ok)}개)\n\n")
        for concept_id in sorted(by_concept.keys(), key=concept_sort_key):
            concept_clusters = sorted(by_concept[concept_id], key=lambda x: -x['size'])
            f.write(f"### ▶ {concept_id} ({len(concept_clusters)}개 원자)\n\n")
            for c in concept_clusters:
                write_cluster_section(f, c, 0)

        # ── [4] needs_review ─────────────────────────────
        if nr_clusters:
            f.write(f"## [4] needs_review ({len(nr_clusters)}개)\n\n")
            f.write("> V7에서 vocab 검증 실패 또는 LLM 오류로 플래그된 항목.\n")
            f.write("> concept_id_review 필드에 qwen의 재검토 결과가 있음.\n\n")
            for i, c in enumerate(nr_clusters):
                cid     = c['cluster_id']
                concept = c.get('concept_id', 'UNKNOWN')
                reviewed_cid = c.get('concept_id_review') or concept
                changed = c.get('concept_id_changed', False)
                cn      = c.get('canonical_name') or '(미결정)'
                anchor  = c.get('anchor_term') or '(미결정)'
                note    = c.get('note') or ''

                changed_str = f" → **{reviewed_cid}** ⚠️변경" if changed else ''

                f.write(f"### NR {cid} | {concept}{changed_str}\n\n")
                f.write(f"<!-- cluster_id: {cid} -->\n")
                f.write(f"제안 이름: {cn}\n")
                f.write(f"anchor: {anchor}\n")
                if note:
                    f.write(f"note: {note}\n")
                member = c['members'][0] if c.get('members') else {}
                ra = member.get('raw_action', '')
                f.write(f"\n**raw_action**: `{ra[:100]}`\n")
                f.write(f"\n---\n\n")

    # ── 통계 ──────────────────────────────────────────
    print(f"\n=== 검토 문서 생성 완료 ===")
    print(f"출력: {OUTPUT_FILE}")
    print(f"\n검토 필요 항목:")
    print(f"  [1] 분리 필요:         {len(impure)}개")
    print(f"  [2] vocab 확장 검토:   {len(vocab_miss)}개")
    print(f"  [3] 정상 클러스터:     {len(normal_ok)}개")
    print(f"  [4] needs_review:      {len(nr_clusters)}개")
    print(f"\n다음: atom_registry_review.md 편집 후")
    print(f"      python3 phase_A_registry_builder.py")


if __name__ == '__main__':
    main()
