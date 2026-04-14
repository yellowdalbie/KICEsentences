#!/usr/bin/env python3
"""
탑다운 Phase 2: Claude API 배치 — 패턴 가이드 + 재작성 제안
============================================================
각 concept_id별로 기존 step_title 전체를 보여주고 Claude에게:
  1. 해당 성취기준에서 자주 나오는 '정석 패턴' 3~7개 추출
  2. B4 플래그(방법어 없음) 건에 대한 구체적 title 수정 제안
  3. C1 플래그(delta 부재 중복) 건에 대한 delta 추가 가이드라인

출력:
  topdown_pattern_guide.json       — concept_id별 정석 패턴 목록
  topdown_rewrite_proposals.json   — 건별 수정 제안 (B4/C1)
  topdown_phase2_log.jsonl         — 처리 로그 (--resume 지원)

실행:
  python3 topdown_phase2_claude.py              # 전체 실행
  python3 topdown_phase2_claude.py --resume     # 처리된 concept_id 건너뜀
  python3 topdown_phase2_claude.py --dry-run    # API 미호출, 구조만 확인
  python3 topdown_phase2_claude.py --only 12미적Ⅰ-01-02   # 특정 ID만
"""

import json, os, sys, time
from pathlib import Path
from collections import defaultdict

# ── 설정 ─────────────────────────────────────────────────────
DIAG_FILE       = 'topdown_diagnosis.json'
TITLE_IDX_FILE  = 'topdown_title_index.json'
VOCAB_FILE      = 'vocab_standard.json'
CONCEPTS_FILE   = 'concepts.json'

PATTERN_OUT     = 'topdown_pattern_guide.json'
PROPOSAL_OUT    = 'topdown_rewrite_proposals.json'
LOG_FILE        = 'topdown_phase2_log.jsonl'

MODEL           = 'claude-sonnet-4-6'
MAX_TOKENS      = 4096
REQUEST_DELAY   = 1.0   # 초 (rate limit 여유)


# ── 데이터 로드 ───────────────────────────────────────────────

def load_all():
    with open(DIAG_FILE, encoding='utf-8') as f:
        diag = json.load(f)
    with open(VOCAB_FILE, encoding='utf-8') as f:
        vocab_raw = json.load(f)
    with open(CONCEPTS_FILE, encoding='utf-8') as f:
        concepts_list = json.load(f)

    # concepts: id → {curriculum_unit, standard_name, keywords}
    concepts = {c['id']: c for c in concepts_list}

    # vocab: concept_id → {name, terms}
    vocab = {k: v for k, v in vocab_raw.items() if not k.startswith('_')}

    return diag, vocab, concepts


def build_concept_data(diag: dict) -> dict:
    """
    concept_id별로:
      - all_titles: 전체 step_title 목록 (파일/스텝 정보 포함)
      - b4_items: B4 플래그 건
      - c1_items: C1 플래그 건
    """
    data = defaultdict(lambda: {'all_titles': [], 'b4_items': [], 'c1_items': []})

    for fp, rec in diag['files'].items():
        for step in rec.get('steps', []):
            cid = step.get('concept_id', '')
            if not cid:
                continue
            entry = {
                'file': fp,
                'step': step['step'],
                'title': step['title'],
                'trigger_cat': step.get('trigger_cat', ''),
            }
            data[cid]['all_titles'].append(entry)

            for fl in step.get('flags', []):
                if fl['code'] == 'B4':
                    data[cid]['b4_items'].append({**entry, 'detail': fl['detail']})
                elif fl['code'] == 'C1':
                    data[cid]['c1_items'].append({**entry, 'detail': fl['detail']})

    return dict(data)


def load_resume_log() -> set:
    """이미 처리된 concept_id 집합 반환."""
    done = set()
    if not os.path.exists(LOG_FILE):
        return done
    with open(LOG_FILE, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get('status') == 'ok':
                    done.add(rec['concept_id'])
            except json.JSONDecodeError:
                pass
    return done


def append_log(record: dict):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')


# ── 프롬프트 구성 ─────────────────────────────────────────────

def build_prompt(concept_id: str, cdata: dict, concepts: dict, vocab: dict) -> str:
    meta = concepts.get(concept_id, {})
    standard_name = meta.get('standard_name', '(성취기준명 없음)')
    curriculum_unit = meta.get('curriculum_unit', '')
    vocab_info = vocab.get(concept_id, {})
    vocab_terms = vocab_info.get('terms', [])

    all_titles  = cdata['all_titles']
    b4_items    = cdata['b4_items']
    c1_items    = cdata['c1_items']

    lines = []
    lines.append(f'## 성취기준: {concept_id}')
    lines.append(f'- 단원: {curriculum_unit}')
    lines.append(f'- 내용: {standard_name}')
    if vocab_terms:
        lines.append(f'- 핵심 용어: {", ".join(vocab_terms)}')
    lines.append('')

    # 전체 타이틀 목록
    lines.append(f'### 현재 step_title 전체 ({len(all_titles)}개)')
    lines.append('(파일명 | 스텝 | 타이틀 | Trigger 카테고리)')
    for i, e in enumerate(all_titles, 1):
        fname = Path(e['file']).stem
        flag_mark = ''
        # B4/C1 여부 표시
        is_b4 = any(x['file'] == e['file'] and x['step'] == e['step'] for x in b4_items)
        is_c1 = any(x['file'] == e['file'] and x['step'] == e['step'] for x in c1_items)
        if is_b4:
            flag_mark = ' [B4]'
        elif is_c1:
            flag_mark = ' [C1]'
        lines.append(f'{i:3d}. {fname} | Step{e["step"]} | {e["title"]}{flag_mark} | [{e["trigger_cat"]}]')
    lines.append('')

    # B4 목록
    if b4_items:
        lines.append(f'### B4 플래그 건 ({len(b4_items)}개) — 방법어/행동어 불명확')
        lines.append('이 타이틀들은 "무엇을"만 있고 "어떻게"(방법)가 없습니다.')
        for e in b4_items:
            fname = Path(e['file']).stem
            lines.append(f'  - {fname} Step{e["step"]}: "{e["title"]}"')
            lines.append(f'    ({e["detail"]})')
        lines.append('')

    # C1 목록
    if c1_items:
        lines.append(f'### C1 플래그 건 ({len(c1_items)}개) — delta 부재 (문제별 구체성 없음)')
        lines.append('이 타이틀들은 같은 성취기준 내에서 너무 유사하여 어떤 문제인지 구분이 안 됩니다.')
        for e in c1_items:
            fname = Path(e['file']).stem
            lines.append(f'  - {fname} Step{e["step"]}: "{e["title"]}"')
        lines.append('')

    # 요청
    lines.append('---')
    lines.append('## 요청')
    lines.append('')
    lines.append('위 정보를 바탕으로 다음 두 가지를 JSON 형식으로 반환하세요.')
    lines.append('')
    lines.append('### 1. 정석 패턴 (canonical_patterns)')
    lines.append(f'이 성취기준({concept_id})에서 반복적으로 등장하는 풀이 패턴을 3~7개 추출하세요.')
    lines.append('각 패턴은 "어떤 수학적 기법/성질을 사용해서 무엇을 구하는가"를 간결하게 표현합니다.')
    lines.append('예: "부정형 극한을 인수분해로 분모·분자 약분하여 극한값 산출"')
    lines.append('규칙: LaTeX 수식 금지 / 보기번호 금지 / 15자 이상 40자 이하 권장')
    lines.append('')
    lines.append('### 2. 수정 제안 (rewrite_proposals)')
    lines.append('B4 및 C1 건에 대해 개선된 타이틀을 제안하세요.')
    lines.append('- B4: 방법어를 추가하여 "어떻게"가 명확해지도록')
    lines.append('- C1: 해당 문제 특유의 조건/구조를 반영하여 delta가 생기도록')
    lines.append('  (단, C1 건은 파일별 원본 Sol 내용을 모르므로 가능하면 타이틀만으로 추론 가능한 delta를 제안)')
    lines.append('')
    lines.append('**반드시 아래 JSON 형식만 출력하세요. 설명 텍스트 없이 JSON만:**')
    lines.append('')
    lines.append('```json')
    lines.append('{')
    lines.append('  "canonical_patterns": [')
    lines.append('    "패턴 설명 1",')
    lines.append('    "패턴 설명 2"')
    lines.append('  ],')
    lines.append('  "rewrite_proposals": [')
    lines.append('    {')
    lines.append('      "file": "파일경로",')
    lines.append('      "step": 1,')
    lines.append('      "flag": "B4",')
    lines.append('      "original": "기존 타이틀",')
    lines.append('      "proposed": "수정 제안 타이틀",')
    lines.append('      "reason": "수정 이유 한 줄"')
    lines.append('    }')
    lines.append('  ]')
    lines.append('}')
    lines.append('```')

    return '\n'.join(lines)


# ── Claude API 호출 ───────────────────────────────────────────

def call_claude(prompt: str, dry_run: bool = False) -> dict | None:
    if dry_run:
        return {
            'canonical_patterns': ['[DRY-RUN] 패턴 1', '[DRY-RUN] 패턴 2'],
            'rewrite_proposals': []
        }

    import anthropic
    client = anthropic.Anthropic()

    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{'role': 'user', 'content': prompt}]
    )

    raw = msg.content[0].text.strip()

    # JSON 블록 추출
    if '```json' in raw:
        start = raw.index('```json') + 7
        end   = raw.index('```', start)
        raw = raw[start:end].strip()
    elif '```' in raw:
        start = raw.index('```') + 3
        end   = raw.index('```', start)
        raw = raw[start:end].strip()

    return json.loads(raw)


# ── 결과 저장 ─────────────────────────────────────────────────

def merge_output(pattern_guide: dict, proposals: list,
                 concept_id: str, result: dict):
    patterns = result.get('canonical_patterns', [])
    rewrites = result.get('rewrite_proposals', [])

    pattern_guide[concept_id] = patterns

    for rw in rewrites:
        rw['concept_id'] = concept_id
        proposals.append(rw)


def save_outputs(pattern_guide: dict, proposals: list):
    with open(PATTERN_OUT, 'w', encoding='utf-8') as f:
        json.dump(pattern_guide, f, ensure_ascii=False, indent=2)

    with open(PROPOSAL_OUT, 'w', encoding='utf-8') as f:
        json.dump(proposals, f, ensure_ascii=False, indent=2)


# ── 메인 ─────────────────────────────────────────────────────

def main():
    dry_run = '--dry-run' in sys.argv
    resume  = '--resume'  in sys.argv

    only_id = None
    if '--only' in sys.argv:
        idx = sys.argv.index('--only')
        if idx + 1 < len(sys.argv):
            only_id = sys.argv[idx + 1]

    print('=' * 60)
    print('탑다운 Phase 2: Claude API 패턴 추출')
    print('=' * 60)
    if dry_run:
        print('  [DRY-RUN 모드] API 미호출')
    if resume:
        print('  [RESUME 모드] 이미 처리된 concept_id 건너뜀')
    print()

    diag, vocab, concepts = load_all()
    concept_data = build_concept_data(diag)

    # 플래그 있는 concept_id만 처리 대상
    flagged_ids = sorted(
        [cid for cid, cd in concept_data.items() if cd['b4_items'] or cd['c1_items']],
        key=lambda cid: -(len(concept_data[cid]['b4_items']) + len(concept_data[cid]['c1_items']))
    )

    if only_id:
        if only_id not in concept_data:
            print(f'오류: {only_id} 을(를) 데이터에서 찾을 수 없습니다.')
            sys.exit(1)
        flagged_ids = [only_id]

    print(f'처리 대상 concept_id: {len(flagged_ids)}개')
    for cid in flagged_ids:
        cd = concept_data[cid]
        print(f'  {cid}: C1={len(cd["c1_items"])} B4={len(cd["b4_items"])}')
    print()

    # resume: 기처리 목록 로드
    done_ids = load_resume_log() if resume else set()
    if done_ids:
        print(f'이미 처리됨: {len(done_ids)}개 건너뜀')

    # 기존 출력 로드 (append 모드)
    pattern_guide: dict = {}
    proposals: list = []

    if resume:
        if os.path.exists(PATTERN_OUT):
            with open(PATTERN_OUT, encoding='utf-8') as f:
                pattern_guide = json.load(f)
        if os.path.exists(PROPOSAL_OUT):
            with open(PROPOSAL_OUT, encoding='utf-8') as f:
                proposals = json.load(f)

    # 처리 루프
    total = len(flagged_ids)
    processed = 0

    for i, cid in enumerate(flagged_ids, 1):
        if cid in done_ids:
            print(f'[{i}/{total}] {cid} — 건너뜀 (이미 처리됨)')
            continue

        cd = concept_data[cid]
        meta = concepts.get(cid, {})
        print(f'[{i}/{total}] {cid} ({meta.get("standard_name", "")[:30]}...)')
        print(f'  타이틀 총 {len(cd["all_titles"])}개 | C1={len(cd["c1_items"])} B4={len(cd["b4_items"])}')

        prompt = build_prompt(cid, cd, concepts, vocab)

        try:
            result = call_claude(prompt, dry_run=dry_run)
        except Exception as e:
            print(f'  [ERROR] API 오류: {e}')
            append_log({'concept_id': cid, 'status': 'error', 'error': str(e)})
            continue

        if result is None:
            print(f'  [ERROR] 응답 파싱 실패')
            append_log({'concept_id': cid, 'status': 'error', 'error': 'parse_failed'})
            continue

        n_patterns  = len(result.get('canonical_patterns', []))
        n_proposals = len(result.get('rewrite_proposals', []))
        print(f'  → 패턴 {n_patterns}개 / 수정 제안 {n_proposals}건')

        merge_output(pattern_guide, proposals, cid, result)
        save_outputs(pattern_guide, proposals)

        append_log({
            'concept_id': cid,
            'status': 'ok',
            'n_patterns': n_patterns,
            'n_proposals': n_proposals,
        })

        processed += 1

        if not dry_run and i < total:
            time.sleep(REQUEST_DELAY)

    # ── 최종 요약 ──────────────────────────────────────────────
    print()
    print('=' * 60)
    print(f'완료: {processed}개 concept_id 처리')
    total_patterns  = sum(len(v) for v in pattern_guide.values())
    total_proposals = len(proposals)
    b4_p = sum(1 for p in proposals if p.get('flag') == 'B4')
    c1_p = sum(1 for p in proposals if p.get('flag') == 'C1')
    print(f'  정석 패턴: {total_patterns}개')
    print(f'  수정 제안: {total_proposals}건 (B4={b4_p} / C1={c1_p})')
    print()
    print(f'출력 파일:')
    print(f'  {PATTERN_OUT}')
    print(f'  {PROPOSAL_OUT}')
    print(f'  {LOG_FILE}')


if __name__ == '__main__':
    main()
