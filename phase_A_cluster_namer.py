"""
Phase A-2 Step 2: qwen Cluster Naming (vocab_standard 연동)
===========================================================
클러스터별로 qwen에게 단일 원자 판단 + delta 없는 canonical_name 생성을 요청한다.
vocab_standard의 공식 용어(anchor_term)를 반드시 포함하도록 강제한다.

최적화: 단일-멤버 클러스터(size=1)는 BATCH_SIZE개 묶음으로 한 번에 처리
        멀티-멤버 클러스터(size>1)는 개별 처리 (is_pure 판단 필요)

입력: .build_cache/phase_A/clusters_raw.json + vocab_standard.json
출력: .build_cache/phase_A/clusters_named.json

실행: python3 phase_A_cluster_namer.py
다음: python3 phase_A_review_builder.py
"""

import json, os, re, time, requests
from collections import defaultdict

INPUT_FILE    = '.build_cache/phase_A/clusters_raw.json'
OUTPUT_FILE   = '.build_cache/phase_A/clusters_named.json'
VOCAB_FILE    = 'vocab_standard.json'
OLLAMA_URL    = 'http://localhost:11434/api/chat'
OLLAMA_MODEL  = 'qwen2.5-coder:14b'
SAVE_INTERVAL = 30     # N개마다 중간 저장
MAX_RETRY     = 2      # vocab 검증 실패 시 재시도
MAX_MEMBERS_SHOWN = 8  # 프롬프트에 보여줄 최대 멤버 수
BATCH_SIZE    = 5      # 단일-멤버 클러스터 배치 크기 (10→5, 타임아웃 방지)
TIMEOUT_BATCH = 240    # 배치 호출 타임아웃 (초)
TIMEOUT_SINGLE = 150   # 개별 호출 타임아웃 (초)

# ── vocab_standard 로드 ──────────────────────────────────────

def load_vocab(vocab_file):
    with open(vocab_file) as f:
        raw = json.load(f)
    banned = raw.get('_banned_terms', [])
    concept_terms = {}
    for cid, entry in raw.items():
        if cid.startswith('_'):
            continue
        terms = entry.get('terms', []) if isinstance(entry, dict) else []
        if terms:
            concept_terms[cid] = terms
    return concept_terms, banned

# ── LLM 호출 ─────────────────────────────────────────────────

def call_qwen(prompt, timeout=150):
    try:
        res = requests.post(OLLAMA_URL, json={
            'model': OLLAMA_MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': False,
            'format': 'json',
        }, timeout=timeout)
        res.raise_for_status()
        return json.loads(res.json()['message']['content'])
    except Exception as e:
        print(f"    [!] LLM 오류: {e}")
        return None

# ── vocab 검증 ───────────────────────────────────────────────

def validate_vocab(canonical_name, terms, banned):
    cn = canonical_name or ''
    if any(b in cn for b in banned):
        return 'banned'
    if terms and not any(t in cn for t in terms):
        return 'missing'
    return 'ok'

# ── 단일-멤버 배치 프롬프트 ───────────────────────────────────

def build_prompt_batch(concept_id, items, concept_terms, banned):
    """
    items: list of (cluster_id, raw_action)
    각 항목에 대해 canonical_name + anchor_term 생성을 한번에 요청.
    """
    terms      = concept_terms.get(concept_id, [])
    terms_str  = ', '.join(terms) if terms else '(없음)'
    banned_str = ', '.join(banned[:10]) if banned else '(없음)'

    lines = '\n'.join(
        f'{i+1}. "{ra}"'
        for i, (_, ra) in enumerate(items)
    )

    # 예시 응답 구조 (items 래퍼 - Ollama format:json은 객체만 허용)
    example_items = ', '.join(
        f'{{"idx": {i+1}, "anchor_term": "공식용어", "canonical_name": "원자이름", "note": ""}}'
        for i in range(len(items))
    )

    return f"""다음은 수능 수학 해설에서 개념 [{concept_id}] 하위의 스텝들입니다.
각 스텝에 대해 delta(문항 특수 정보) 없는 원자 이름을 생성하세요.

[스텝 목록]
{lines}

[공식 용어 (anchor_term 후보)]: {terms_str}
[사용 금지 용어]: {banned_str}

규칙:
- canonical_name: 문항 특수 정보(변수명·수치·구하는 대상) 제거, 수학적 조작만 표현
- anchor_term: 공식 용어 중 1개 (없으면 가장 적합한 수학 용어)
- LaTeX 금지, 30자 이내

다음 JSON으로만 응답하라 (items 배열 길이={len(items)}):
{{"items": [{example_items}]}}"""

# ── 멀티-멤버 클러스터 프롬프트 ──────────────────────────────

def build_prompt_normal(cluster, concept_terms, banned):
    concept_id  = cluster['concept_id']
    terms       = concept_terms.get(concept_id, [])
    banned_list = banned

    members = cluster['members']
    sample  = members[:MAX_MEMBERS_SHOWN]
    lines   = '\n'.join(
        f"{i+1}. \"{m['raw_action']}\""
        for i, m in enumerate(sample)
    )
    extra = f"\n   ... 외 {len(members)-len(sample)}개" if len(members) > MAX_MEMBERS_SHOWN else ''

    terms_str  = ', '.join(terms)  if terms  else '(없음)'
    banned_str = ', '.join(banned_list[:10]) if banned_list else '(없음)'

    return f"""다음은 수능 수학 해설에서 같은 개념 [{concept_id}] 하위의 유사 스텝들입니다.

[스텝 목록]
{lines}{extra}

[이 개념의 공식 용어(anchor_term 후보)]: {terms_str}
[사용 금지 용어]: {banned_str}

판단 기준:
1. 이 스텝들이 수학적으로 하나의 조작(원자)인가?
2. canonical_name: 문항 특수 정보(특정 변수명·수치·구하는 대상)를 제거한 원자 이름
   - 공식 용어 중 1개를 anchor_term으로 반드시 포함
   - LaTeX 금지, 30자 이내
3. anchor_term: canonical_name에서 중심이 되는 공식 용어 1개

다음 JSON으로만 응답하라:
{{
  "is_pure": true 또는 false,
  "anchor_term": "공식 용어 1개",
  "canonical_name": "원자 이름",
  "split_proposal": null 또는 [{{"canonical_name":"...", "anchor_term":"...", "member_indices":[1,3,...]}}],
  "note": ""
}}"""

# ── needs_review 프롬프트 ─────────────────────────────────────

def build_prompt_needs_review(cluster, concept_terms, banned):
    cid        = cluster.get('concept_id', 'UNKNOWN')
    member     = cluster['members'][0]
    raw_action = member.get('raw_action', '')
    cn_v7      = member.get('canonical_name_v7', '')
    terms      = concept_terms.get(cid, [])
    terms_str  = ', '.join(terms) if terms else '(없음)'
    banned_str = ', '.join(banned[:10]) if banned else '(없음)'

    return f"""다음은 원자 분류에 실패한(needs_review) 수능 수학 해설 스텝입니다.

[스텝]
raw_action: "{raw_action}"
v7 생성 이름(참고): "{cn_v7}"
현재 배정된 concept_id: {cid}

[{cid} 공식 용어]: {terms_str}
[사용 금지 용어]: {banned_str}

질문:
1. 이 스텝에 가장 맞는 concept_id는 무엇인가? (현재 값이 맞으면 유지)
2. delta 없는 원자 이름(canonical_name)은?
   - 공식 용어 포함, LaTeX 금지, 30자 이내

다음 JSON으로만 응답하라:
{{
  "concept_id": "재검토 결과 concept_id",
  "anchor_term": "공식 용어 1개",
  "canonical_name": "원자 이름",
  "concept_id_changed": true 또는 false,
  "note": ""
}}"""

# ── 배치 결과 파싱 ────────────────────────────────────────────

def parse_batch_result(raw, n_expected):
    """
    raw: LLM 응답 (dict 또는 list)
    배열 형태로 반환. 실패 시 None 리스트.
    """
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        # {"items": [...]} 또는 {"1": {...}, "2": {...}} 형태 처리
        for key in ['items', 'results', 'list']:
            if key in raw and isinstance(raw[key], list):
                items = raw[key]
                break
        else:
            # dict of idx → entry
            items = []
            for i in range(1, n_expected + 1):
                entry = raw.get(str(i)) or raw.get(i)
                if entry and isinstance(entry, dict):
                    entry['idx'] = i
                    items.append(entry)
    else:
        return None

    # idx 정렬 및 패딩
    indexed = {(item.get('idx', i+1)): item for i, item in enumerate(items)}
    result = []
    for i in range(1, n_expected + 1):
        result.append(indexed.get(i))
    return result

# ── 메인 ─────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("Phase A-2 Step 2: qwen Cluster Naming (Batch Mode)")
    print("=" * 55)

    with open(INPUT_FILE) as f:
        data = json.load(f)

    concept_terms, banned = load_vocab(VOCAB_FILE)

    clusters    = data['clusters']
    nr_clusters = data.get('needs_review', [])

    single_clusters = [c for c in clusters if c['size'] == 1]
    multi_clusters  = [c for c in clusters if c['size'] > 1]

    # 배치 수 계산
    n_batches = (len(single_clusters) + BATCH_SIZE - 1) // BATCH_SIZE
    total_calls = n_batches + len(multi_clusters) + len(nr_clusters)

    print(f"\n단일-멤버 클러스터: {len(single_clusters)}개 → {n_batches}개 배치 (x{BATCH_SIZE})")
    print(f"멀티-멤버 클러스터: {len(multi_clusters)}개 (개별)")
    print(f"needs_review:  {len(nr_clusters)}개 (개별)")
    print(f"총 LLM 호출 예정: {total_calls}회 (원래: {len(clusters)+len(nr_clusters)}회)")

    # 이어하기
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE) as f:
            saved = json.load(f)
        done_ids = {c['cluster_id'] for c in saved.get('clusters', [])
                    if c.get('canonical_name')}
        done_nr  = {c['cluster_id'] for c in saved.get('needs_review', [])
                    if c.get('canonical_name')}
        print(f"이어하기: 완료 {len(done_ids)}개 클러스터 / {len(done_nr)}개 NR")
    else:
        done_ids, done_nr = set(), set()
        saved = {'clusters': list(clusters), 'needs_review': list(nr_clusters)}

    cluster_map = {c['cluster_id']: c for c in saved['clusters']}
    nr_map      = {c['cluster_id']: c for c in saved['needs_review']}

    processed  = 0
    call_num   = len(done_ids) // BATCH_SIZE + len(done_nr)  # 이어하기 시 시작 번호 근사

    # ── [1] 단일-멤버 배치 처리 ─────────────────────────────
    print(f"\n[1] 단일-멤버 클러스터 배치 처리 ({n_batches}개 배치)...")

    # concept_id별로 그룹화 후 배치 생성
    single_by_concept = defaultdict(list)
    for c in single_clusters:
        if c['cluster_id'] not in done_ids:
            single_by_concept[c['concept_id']].append(c)

    batch_num = 0
    for concept_id in sorted(single_by_concept.keys()):
        pending = single_by_concept[concept_id]
        for batch_start in range(0, len(pending), BATCH_SIZE):
            batch = pending[batch_start:batch_start + BATCH_SIZE]
            batch_num += 1
            call_num  += 1

            cids   = [c['cluster_id'] for c in batch]
            items  = [(c['cluster_id'], c['members'][0]['raw_action']) for c in batch]
            terms  = concept_terms.get(concept_id, [])

            print(f"  ({call_num}/{total_calls}) 배치 {batch_num}/{n_batches} [{concept_id}] {len(batch)}개", flush=True)

            result_list = None
            for attempt in range(MAX_RETRY + 1):
                prompt = build_prompt_batch(concept_id, items, concept_terms, banned)
                if attempt > 0:
                    terms_str = ', '.join(terms) if terms else '(없음)'
                    prompt += f"\n\n[재시도 {attempt}] canonical_name에 반드시 다음 중 하나를 포함: {terms_str}"
                    print(f"    → vocab 재시도 {attempt}/{MAX_RETRY} (필요 용어: {terms_str[:40]})", flush=True)

                raw = call_qwen(prompt, timeout=TIMEOUT_BATCH)
                if not raw:
                    print(f"    ✗ LLM 오류/타임아웃 (시도 {attempt+1}/{MAX_RETRY+1})", flush=True)
                    time.sleep(2)
                    continue

                result_list = parse_batch_result(raw, len(batch))
                if result_list is None:
                    print(f"    ✗ JSON 파싱 실패 (시도 {attempt+1}/{MAX_RETRY+1})", flush=True)
                    time.sleep(1)
                    continue

                # vocab 검증
                all_ok = True
                for r in result_list:
                    if r is None:
                        continue
                    cn = (r.get('canonical_name') or '')
                    status = validate_vocab(cn, terms, banned)
                    if status != 'ok':
                        all_ok = False
                        break

                if all_ok:
                    break
                else:
                    time.sleep(1)

            # 결과 저장 + 항목별 출력
            ok_count = 0
            fail_count = 0
            for i, (cluster_id, raw_action) in enumerate(items):
                r = (result_list[i] if result_list and i < len(result_list) else None)
                target = cluster_map[cluster_id]
                ra_short = raw_action[:45].replace('\n', ' ')
                if r:
                    cn     = r.get('canonical_name', '')
                    anchor = r.get('anchor_term', '')
                    vocab_ok = validate_vocab(cn, terms, banned) == 'ok'
                    target.update({
                        'is_pure':        True,
                        'anchor_term':    anchor,
                        'canonical_name': cn or None,
                        'split_proposal': None,
                        'note':           r.get('note', ''),
                        'vocab_missing':  not vocab_ok,
                    })
                    if cn:
                        vocab_flag = ' [vocab없음]' if not vocab_ok else ''
                        print(f"    [{i+1}] \"{ra_short}\" → {cn}{vocab_flag}", flush=True)
                        ok_count += 1
                    else:
                        print(f"    [{i+1}] \"{ra_short}\" → (이름 없음)", flush=True)
                        fail_count += 1
                else:
                    target.update({
                        'is_pure': True, 'anchor_term': None,
                        'canonical_name': None, 'split_proposal': None,
                        'note': 'LLM 실패', 'vocab_missing': True,
                    })
                    print(f"    [{i+1}] \"{ra_short}\" → ✗ 실패 (다음 재실행 시 재처리)", flush=True)
                    fail_count += 1

            summary = f"  → 완료 {ok_count}개" + (f", 실패 {fail_count}개" if fail_count else "")
            print(summary, flush=True)

            processed += len(batch)
            if processed % SAVE_INTERVAL == 0:
                _save(saved, OUTPUT_FILE)
                print(f"    [저장] {processed}개 완료")

            time.sleep(0.2)

    # ── [2] 멀티-멤버 클러스터 개별 처리 ───────────────────
    print(f"\n[2] 멀티-멤버 클러스터 처리 ({len(multi_clusters)}개)...")
    for i, cluster in enumerate(multi_clusters):
        cid = cluster['cluster_id']
        if cid in done_ids:
            continue

        concept_id = cluster['concept_id']
        terms      = concept_terms.get(concept_id, [])
        n          = cluster['size']
        call_num  += 1

        # 멤버 raw_action 목록 출력
        member_previews = [m['raw_action'][:40].replace('\n',' ')
                           for m in cluster['members'][:MAX_MEMBERS_SHOWN]]
        print(f"  ({call_num}/{total_calls}) cluster {cid} [{concept_id}] {n}개멤버", flush=True)
        for j, mp in enumerate(member_previews):
            print(f"    입력[{j+1}] \"{mp}\"", flush=True)

        result = None
        for attempt in range(MAX_RETRY + 1):
            prompt = build_prompt_normal(cluster, concept_terms, banned)
            if attempt > 0:
                terms_str = ', '.join(terms) if terms else '(없음)'
                prompt += f"\n\n[재시도 {attempt}] canonical_name에 반드시 다음 중 하나를 포함: {terms_str}"
                print(f"    → vocab 재시도 {attempt}/{MAX_RETRY} (필요: {terms_str[:40]})", flush=True)

            raw = call_qwen(prompt, timeout=TIMEOUT_SINGLE)
            if not raw:
                print(f"    ✗ LLM 오류/타임아웃 (시도 {attempt+1}/{MAX_RETRY+1})", flush=True)
                time.sleep(2)
                continue

            cn     = raw.get('canonical_name', '')
            status = validate_vocab(cn, terms, banned)

            if status == 'ok':
                result = raw
                break
            elif status == 'banned':
                print(f"    ✗ 금지어 포함: \"{cn}\" (시도 {attempt+1})", flush=True)
                time.sleep(1)
            else:
                print(f"    ✗ vocab 불일치: \"{cn}\" (필요: {', '.join(terms[:3])})", flush=True)
                time.sleep(1)

        if result is None:
            result = {'is_pure': None, 'anchor_term': None,
                      'canonical_name': None, 'split_proposal': None, 'note': 'LLM 실패'}
            vocab_ok = False
        else:
            vocab_ok = validate_vocab(result.get('canonical_name',''), terms, banned) == 'ok'

        target = cluster_map[cid]
        target.update({
            'is_pure':        result.get('is_pure'),
            'anchor_term':    result.get('anchor_term'),
            'canonical_name': result.get('canonical_name'),
            'split_proposal': result.get('split_proposal'),
            'note':           result.get('note', ''),
            'vocab_missing':  not vocab_ok,
        })

        cn_display = (result.get('canonical_name') or '(실패)')[:35]
        pure_flag  = ' [분리필요]' if result.get('is_pure') is False else ''
        vocab_flag = ' [vocab없음]' if not vocab_ok else ''
        print(f"  → {cn_display}{pure_flag}{vocab_flag}", flush=True)

        processed += 1
        if processed % SAVE_INTERVAL == 0:
            _save(saved, OUTPUT_FILE)

        time.sleep(0.3)

    # ── [3] needs_review 처리 ───────────────────────────────
    print(f"\n[3] needs_review 처리 ({len(nr_clusters)}개)...")
    for i, nr in enumerate(nr_clusters):
        cid = nr['cluster_id']
        if cid in done_nr:
            continue

        concept_id = nr.get('concept_id', 'UNKNOWN')
        terms      = concept_terms.get(concept_id, [])
        call_num  += 1
        ra_short = (nr['members'][0].get('raw_action','')[:50]).replace('\n',' ')
        print(f"  ({call_num}/{total_calls}) NR {cid} [{concept_id}]", flush=True)
        print(f"    입력: \"{ra_short}\"", flush=True)

        result = None
        for attempt in range(MAX_RETRY + 1):
            prompt = build_prompt_needs_review(nr, concept_terms, banned)
            if attempt > 0:
                terms_str = ', '.join(terms) if terms else '(없음)'
                prompt += f"\n\n[재시도 {attempt}] anchor_term과 canonical_name에 다음 용어 포함 필수: {terms_str}"
                print(f"    → vocab 재시도 {attempt}/{MAX_RETRY}", flush=True)

            raw = call_qwen(prompt, timeout=TIMEOUT_SINGLE)
            if not raw:
                print(f"    ✗ LLM 오류/타임아웃 (시도 {attempt+1}/{MAX_RETRY+1})", flush=True)
                time.sleep(2)
                continue

            cn      = raw.get('canonical_name', '')
            new_cid = raw.get('concept_id', concept_id)
            new_terms = concept_terms.get(new_cid, terms)
            status  = validate_vocab(cn, new_terms, banned)

            if status == 'ok':
                result = raw
                break
            else:
                print(f"    ✗ vocab 불일치: \"{cn}\"", flush=True)
                time.sleep(1)

        if result is None:
            result = {'concept_id': concept_id, 'anchor_term': None,
                      'canonical_name': None, 'concept_id_changed': False,
                      'note': 'LLM 실패'}

        target = nr_map[cid]
        new_cid = result.get('concept_id', concept_id)
        target.update({
            'concept_id_review':  new_cid,
            'concept_id_changed': result.get('concept_id_changed', False),
            'anchor_term':        result.get('anchor_term'),
            'canonical_name':     result.get('canonical_name'),
            'note':               result.get('note', ''),
            'vocab_missing':      validate_vocab(
                result.get('canonical_name',''),
                concept_terms.get(new_cid, []), banned
            ) != 'ok',
        })

        cn_display  = (result.get('canonical_name') or '(실패)')[:35]
        cid_changed = f" [concept_id: {concept_id}→{new_cid}]" if result.get('concept_id_changed') else ''
        print(f"  → {cn_display}{cid_changed}", flush=True)

        time.sleep(0.3)

    # ── 최종 저장 ────────────────────────────────────────────
    _save(saved, OUTPUT_FILE)

    # ── 통계 요약 ─────────────────────────────────────────────
    clusters_done  = [c for c in saved['clusters'] if c.get('canonical_name')]
    impure         = [c for c in clusters_done if c.get('is_pure') is False]
    vocab_missing  = [c for c in clusters_done if c.get('vocab_missing')]
    nr_done        = [c for c in saved['needs_review'] if c.get('canonical_name')]
    nr_changed     = [c for c in nr_done if c.get('concept_id_changed')]

    print(f"\n=== 완료 요약 ===")
    print(f"처리 완료: {len(clusters_done)}/{len(clusters)}개 클러스터")
    print(f"  is_pure=false (분리 필요):      {len(impure)}개")
    print(f"  vocab_missing (vocab 확장 검토): {len(vocab_missing)}개")
    print(f"needs_review 처리: {len(nr_done)}/{len(nr_clusters)}개")
    print(f"  concept_id 변경: {len(nr_changed)}개")
    print(f"\n출력: {OUTPUT_FILE}")
    print("다음: python3 phase_A_review_builder.py")


def _save(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
