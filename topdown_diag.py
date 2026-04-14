#!/usr/bin/env python3
"""
탑다운 Phase 1: Sol 파일 전수 진단
====================================
1126개 Sol 파일을 스캔하여 4가지 이상값을 탐지한다.

탐지 항목:
  [A] concept_id 이상 — 존재하지 않는 concept_id
  [B] 포맷 위반     — LaTeX 수식, 보기번호, 방법어 부재, 너무 짧음
  [C] delta 부재    — 같은 concept_id 내 중복/유사 타이틀
  [D] 구조 이상     — 스텝 수 1개 또는 7개 이상

출력:
  topdown_diagnosis.json   — step별 플래그 상세 (Phase 2 Claude 배치 입력)
  topdown_title_index.json — concept_id별 타이틀 목록 (Claude 패턴 추출용)
  topdown_report.txt       — 사람이 읽는 요약 보고서

실행:
  python3 topdown_diag.py           # 텍스트 기반 (빠름)
  python3 topdown_diag.py --embed   # BGE-m3-ko 임베딩으로 [C] 정밀 탐지 (느림)
"""

import json, re, sys, glob, os
from collections import defaultdict
from pathlib import Path

# ── 설정 ─────────────────────────────────────────────────────────
SOL_GLOB      = 'Sol/**/*.md'
CONCEPTS_FILE = 'concepts.json'
OUT_DIAG      = 'topdown_diagnosis.json'
OUT_INDEX     = 'topdown_title_index.json'
OUT_REPORT    = 'topdown_report.txt'
EMBED_CACHE   = '.build_cache/topdown/title_embeddings.npz'
EMBED_MODEL   = 'dragonkue/BGE-m3-ko'

USE_EMBED         = '--embed' in sys.argv
SIM_THRESHOLD_C   = 0.93  # [C] 유사 타이틀 판단 임계값
DUPE_TEXT_RATIO   = 0.90  # [C] 텍스트 기반 단어 겹침 비율

# 심각도 정의
SEVERITY = {
    'A0': 'HIGH',   # concept_id 없음
    'A1': 'HIGH',   # 유효하지 않은 concept_id
    'B1': 'HIGH',   # LaTeX 수식 포함
    'B2': 'HIGH',   # 보기번호 포함
    'B3': 'MEDIUM', # 너무 짧음
    'B4': 'MEDIUM', # 방법어 부재
    'C1': 'MEDIUM', # 텍스트 중복 (exact)
    'C2': 'LOW',    # 유사 타이틀 (임베딩)
    'D1': 'LOW',    # 스텝 1개 파일
    'D2': 'LOW',    # 스텝 7개+ 파일
}

# ── [B] 포맷 위반 패턴 ────────────────────────────────────────────

RE_LATEX   = re.compile(r'\$[^$]+\$|\\\(|\\\[|\\frac|\\sum|\\int|\\lim|\\sqrt')
RE_BOGI    = re.compile(r'[ㄱㄴㄷ][을를은이가]|ㄱ[·,]\s*ㄴ|ㄴ[·,]\s*ㄷ|ㄱ[·,]\s*ㄴ[·,]\s*ㄷ')
RE_METHOD  = re.compile(
    r'이용|활용|적용|분석|변환|도출|판정|결정|산출|구성|추출|비교|역추적|수립|전개|소거|'
    r'치환|연립|계산하여|구하여|활용하여|설정|파악|대입|정리|검토|확인하여|'
    r'으로\s|으로$|로\s|로$|조건으로|법칙으로|정의로|성질로|공식으로|정리로|기반으로|'
    r'통하여|통해|세우기|세워|탐색|판별|확정|도입|귀납|역추|치환하|전환|분류|'
    r'하여\s|하여$|함으로|써서|를 써|로써|공식|정리|법칙|규칙|조건|원리|성질'
)

# ── Sol 파일 파싱 ─────────────────────────────────────────────────

STEP_HDR   = re.compile(r'^## \[Step (\d+)\]\s*(.+)$', re.MULTILINE)
RE_ACTION  = re.compile(r'^\s*-\s*\*\*Action\*\*:\s*\[([^\]]+)\]', re.MULTILINE)
RE_TRIGGER = re.compile(r'^\s*-\s*\*\*Trigger\*\*:\s*\[([^\]]+)\]', re.MULTILINE)
RE_RESULT  = re.compile(r'^\s*-\s*\*\*Result\*\*:\s*(.+)$', re.MULTILINE)


def parse_sol(filepath):
    """Sol 파일 파싱 → step 레코드 리스트."""
    try:
        content = open(filepath, encoding='utf-8').read()
    except Exception:
        return []

    headers = list(STEP_HDR.finditer(content))
    steps = []
    for i, h in enumerate(headers):
        body_start = h.start()
        body_end   = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        body       = content[body_start:body_end]

        action_m  = RE_ACTION.search(body)
        trigger_m = RE_TRIGGER.search(body)
        result_m  = RE_RESULT.search(body)

        steps.append({
            'step':        int(h.group(1)),
            'title':       h.group(2).strip(),
            'concept_id':  action_m.group(1).strip()  if action_m  else '',
            'trigger_cat': trigger_m.group(1).strip() if trigger_m else '',
            'result':      result_m.group(1).strip()  if result_m  else '',
        })
    return steps


# ── 플래그 검사 함수 ──────────────────────────────────────────────

def flag_format(title):
    """[B] 포맷 위반."""
    flags = []
    if RE_LATEX.search(title):
        flags.append(('B1', f'LaTeX 수식 포함: {RE_LATEX.search(title).group()[:20]}'))
    if RE_BOGI.search(title):
        flags.append(('B2', f'보기번호(ㄱㄴㄷ) 포함'))
    if len(title.replace(' ', '')) < 10:
        flags.append(('B3', f'타이틀 너무 짧음 ({len(title)}자)'))
    if not RE_METHOD.search(title):
        flags.append(('B4', '방법어 없음 — 수단(how)이 불명확'))
    return flags


def flag_concept(concept_id, valid_ids):
    """[A] concept_id 이상."""
    flags = []
    if not concept_id:
        flags.append(('A0', 'concept_id 없음 (Action 파싱 실패)'))
    elif concept_id not in valid_ids:
        flags.append(('A1', f'concepts.json에 없는 concept_id: {concept_id}'))
    return flags


RE_PROB_NUM = re.compile(r'_(\d+)(?:\.md)?$')

def flag_step_count(n, filepath=''):
    """
    [D] 스텝 수 이상.
    D1(1개)은 문항번호 10번 이상인 경우만 플래그 (1~9번 단순 문제는 정상).
    """
    if n == 1:
        m = RE_PROB_NUM.search(filepath)
        prob_num = int(m.group(1)) if m else 99
        if prob_num >= 10:
            return [('D1', f'스텝 1개 (문항{prob_num}번) — 병합 후보')]
        return []   # 1~9번: 1-step 정상
    if n >= 7:
        return [('D2', f'스텝 {n}개 — 분리 후보 또는 과도한 세분화')]
    return []


def text_similarity(a, b):
    """단어 집합 Jaccard 유사도."""
    ws_a = set(re.split(r'\s+', a.strip()))
    ws_b = set(re.split(r'\s+', b.strip()))
    if not ws_a or not ws_b:
        return 0.0
    return len(ws_a & ws_b) / len(ws_a | ws_b)


def flag_duplicates_text(titles_in_concept):
    """
    [C1] 텍스트 기반 중복 탐지.
    같은 concept_id 내에서 title이 동일하거나 단어 Jaccard >= DUPE_TEXT_RATIO인 쌍 탐지.
    반환: set of (file, step) 인덱스 — 중복 판정된 항목
    """
    flagged = set()
    items = list(titles_in_concept)  # list of (title, file, step)

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            t_a, f_a, s_a = items[i]
            t_b, f_b, s_b = items[j]
            sim = text_similarity(t_a, t_b)
            if sim >= DUPE_TEXT_RATIO:
                flagged.add((f_a, s_a))
                flagged.add((f_b, s_b))
    return flagged


# ── 임베딩 기반 [C2] 탐지 ─────────────────────────────────────────

def load_or_compute_embeddings(all_titles_flat):
    """BGE-m3-ko 임베딩 로드 또는 계산."""
    import numpy as np
    os.makedirs(os.path.dirname(EMBED_CACHE), exist_ok=True)

    if os.path.exists(EMBED_CACHE):
        cache = np.load(EMBED_CACHE, allow_pickle=True)
        if list(cache['texts']) == all_titles_flat:
            print(f'  임베딩 캐시 재사용 ({len(all_titles_flat)}개)')
            return cache['embeddings']

    print(f'  BGE-m3-ko 임베딩 계산 중 ({len(all_titles_flat)}개)...')
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL)
    embeddings = model.encode(
        all_titles_flat,
        normalize_embeddings=True,
        show_progress_bar=True,
        batch_size=64,
    )
    np.savez(EMBED_CACHE, embeddings=embeddings,
             texts=np.array(all_titles_flat, dtype=object))
    print(f'  캐시 저장: {EMBED_CACHE}')
    return embeddings


def flag_duplicates_embed(titles_in_concept, embed_map):
    """
    [C2] 임베딩 기반 유사 타이틀 탐지.
    embed_map: (file, step) → embedding vector
    """
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    items = list(titles_in_concept)  # (title, file, step)
    if len(items) < 2:
        return set()

    keys    = [(f, s) for _, f, s in items]
    vectors = np.array([embed_map[k] for k in keys])
    sim_mat = cosine_similarity(vectors)

    flagged = set()
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if sim_mat[i, j] >= SIM_THRESHOLD_C:
                flagged.add(keys[i])
                flagged.add(keys[j])
    return flagged


# ── 메인 ─────────────────────────────────────────────────────────

def main():
    print('=' * 60)
    print('탑다운 Phase 1: Sol 파일 전수 진단')
    print('=' * 60)

    # ── concepts.json 로드 ─────────────────────────────────────
    with open(CONCEPTS_FILE, encoding='utf-8') as f:
        concepts_raw = json.load(f)
    valid_ids = {c['id'] for c in concepts_raw}
    print(f'성취기준: {len(valid_ids)}개 로드')

    # ── Sol 파일 전수 파싱 ─────────────────────────────────────
    sol_files = sorted(glob.glob(SOL_GLOB, recursive=True))
    print(f'Sol 파일: {len(sol_files)}개 스캔 중...')

    # 데이터 구조
    # file_records: filepath → {steps: [...], file_flags: [...]}
    file_records = {}
    # concept_titles: concept_id → list of (title, filepath, step_num)
    concept_titles = defaultdict(list)
    # 전체 통계
    total_steps = 0

    for filepath in sol_files:
        rel = os.path.relpath(filepath)
        steps = parse_sol(filepath)
        if not steps:
            continue

        total_steps += len(steps)
        step_records = []

        for s in steps:
            flags = []
            flags += flag_concept(s['concept_id'], valid_ids)
            flags += flag_format(s['title'])
            # [C]는 concept_titles 수집 후 별도 처리
            step_records.append({
                'step':       s['step'],
                'title':      s['title'],
                'concept_id': s['concept_id'],
                'trigger_cat':s['trigger_cat'],
                'flags':      flags,  # (code, detail) list
            })
            if s['concept_id']:
                concept_titles[s['concept_id']].append(
                    (s['title'], rel, s['step'])
                )

        file_flags = flag_step_count(len(steps), rel)
        file_records[rel] = {
            'step_count': len(steps),
            'file_flags': file_flags,
            'steps':      step_records,
        }

    print(f'파싱 완료: {total_steps}개 step, {len(concept_titles)}개 concept_id\n')

    # ── [C1] 텍스트 기반 중복 탐지 ─────────────────────────────
    print('[C1] 텍스트 기반 중복 탐지...')
    c1_flagged = set()
    for cid, items in concept_titles.items():
        flagged = flag_duplicates_text(items)
        c1_flagged |= flagged

    print(f'  C1 탐지: {len(c1_flagged)}개 step')

    # [C1] 플래그를 step_records에 반영
    for rel, rec in file_records.items():
        for sr in rec['steps']:
            key = (rel, sr['step'])
            if key in c1_flagged:
                sr['flags'].append(('C1', '같은 concept_id 내 중복/유사 타이틀 (delta 부재 의심)'))

    # ── [C2] 임베딩 기반 탐지 (선택) ───────────────────────────
    c2_flagged = set()
    if USE_EMBED:
        print('[C2] 임베딩 기반 유사 타이틀 탐지...')
        # 전체 타이틀 리스트 (순서 고정)
        all_keys    = []
        all_titles  = []
        for cid, items in concept_titles.items():
            for title, fp, step in items:
                all_keys.append((fp, step))
                all_titles.append(title)

        embeddings = load_or_compute_embeddings(all_titles)
        embed_map  = {k: embeddings[i] for i, k in enumerate(all_keys)}

        for cid, items in concept_titles.items():
            flagged = flag_duplicates_embed(items, embed_map)
            c2_flagged |= flagged

        # C1이 이미 잡은 것은 C2에서 제외 (중복 플래그 방지)
        c2_only = c2_flagged - c1_flagged
        for rel, rec in file_records.items():
            for sr in rec['steps']:
                key = (rel, sr['step'])
                if key in c2_only:
                    sr['flags'].append(('C2', f'유사 타이틀 (임베딩 sim≥{SIM_THRESHOLD_C})'))

        print(f'  C2 탐지: {len(c2_only)}개 step (C1 제외)')
    else:
        print('[C2] 임베딩 탐지 생략 (--embed 옵션으로 활성화)')

    # ── 출력: topdown_diagnosis.json ───────────────────────────
    print('\n출력 파일 생성 중...')

    diag_output = {
        'meta': {
            'total_files':  len(file_records),
            'total_steps':  total_steps,
            'embed_used':   USE_EMBED,
            'sim_threshold':SIM_THRESHOLD_C,
        },
        'files': {},
    }

    for rel, rec in sorted(file_records.items()):
        diag_output['files'][rel] = {
            'step_count': rec['step_count'],
            'file_flags': [{'code': c, 'detail': d} for c, d in rec['file_flags']],
            'steps': [
                {
                    'step':        sr['step'],
                    'title':       sr['title'],
                    'concept_id':  sr['concept_id'],
                    'trigger_cat': sr['trigger_cat'],
                    'flags': [{'code': c, 'severity': SEVERITY.get(c, '?'), 'detail': d}
                              for c, d in sr['flags']],
                }
                for sr in rec['steps']
            ],
        }

    with open(OUT_DIAG, 'w', encoding='utf-8') as f:
        json.dump(diag_output, f, ensure_ascii=False, indent=2)
    print(f'  → {OUT_DIAG}')

    # ── 출력: topdown_title_index.json ─────────────────────────
    # concept_id별 타이틀 목록 (Phase 2 Claude 배치용)
    # flags를 참조하기 위해 file_records를 역인덱싱
    step_flag_map = {}
    for rel, rec in file_records.items():
        for sr in rec['steps']:
            codes = [f['code'] for f in
                     [{'code': c} for c, d in sr['flags']]]
            step_flag_map[(rel, sr['step'])] = [c for c, d in sr['flags']]

    index_output = {}
    for cid in sorted(concept_titles.keys()):
        items = concept_titles[cid]
        entries = []
        for title, fp, step in sorted(items, key=lambda x: (x[1], x[2])):
            flag_codes = step_flag_map.get((fp, step), [])
            entries.append({
                'title':      title,
                'file':       fp,
                'step':       step,
                'flags':      flag_codes,
                'has_issue':  bool(flag_codes),
            })
        flagged_count = sum(1 for e in entries if e['has_issue'])
        index_output[cid] = {
            'count':         len(entries),
            'flagged_count': flagged_count,
            'titles':        entries,
        }

    with open(OUT_INDEX, 'w', encoding='utf-8') as f:
        json.dump(index_output, f, ensure_ascii=False, indent=2)
    print(f'  → {OUT_INDEX}')

    # ── 통계 집계 ───────────────────────────────────────────────
    flag_counter   = defaultdict(int)
    flagged_steps  = 0
    flagged_files  = 0

    for rel, rec in file_records.items():
        file_has_flag = bool(rec['file_flags'])
        for sr in rec['steps']:
            if sr['flags']:
                flagged_steps += 1
                file_has_flag = True
            for c, d in sr['flags']:
                flag_counter[c] += 1
        for c, d in rec['file_flags']:
            flag_counter[c] += 1
        if file_has_flag:
            flagged_files += 1

    high_count   = sum(v for k, v in flag_counter.items() if SEVERITY.get(k) == 'HIGH')
    medium_count = sum(v for k, v in flag_counter.items() if SEVERITY.get(k) == 'MEDIUM')
    low_count    = sum(v for k, v in flag_counter.items() if SEVERITY.get(k) == 'LOW')

    # ── concept_id별 상위 이상값 ───────────────────────────────
    concept_flag_count = defaultdict(int)
    for rel, rec in file_records.items():
        for sr in rec['steps']:
            if sr['flags'] and sr['concept_id']:
                concept_flag_count[sr['concept_id']] += len(sr['flags'])

    top_concepts = sorted(concept_flag_count.items(), key=lambda x: -x[1])[:15]

    # ── 보고서 텍스트 작성 ────────────────────────────────────
    lines = []
    lines.append('=' * 60)
    lines.append('탑다운 Phase 1 진단 보고서')
    lines.append('=' * 60)
    lines.append('')
    lines.append('[ 전체 현황 ]')
    lines.append(f'  Sol 파일:    {len(file_records)}개')
    lines.append(f'  총 Step:     {total_steps}개')
    lines.append(f'  이상 파일:   {flagged_files}개  ({flagged_files/len(file_records)*100:.1f}%)')
    lines.append(f'  이상 Step:   {flagged_steps}개  ({flagged_steps/total_steps*100:.1f}%)')
    lines.append('')
    lines.append('[ 플래그 유형별 ]')
    lines.append(f'  HIGH   총계: {high_count}개')
    for code in ('A0', 'A1', 'B1', 'B2'):
        if flag_counter[code]:
            lines.append(f'    [{code}] {flag_counter[code]}개')
    lines.append(f'  MEDIUM 총계: {medium_count}개')
    for code in ('B3', 'B4', 'C1', 'C2'):
        if flag_counter[code]:
            lines.append(f'    [{code}] {flag_counter[code]}개')
    lines.append(f'  LOW    총계: {low_count}개')
    for code in ('D1', 'D2'):
        if flag_counter[code]:
            lines.append(f'    [{code}] {flag_counter[code]}개')
    lines.append('')
    lines.append('[ 플래그 코드 설명 ]')
    desc = {
        'A0': 'concept_id 없음',
        'A1': '유효하지 않은 concept_id',
        'B1': 'LaTeX 수식 포함',
        'B2': '보기번호(ㄱㄴㄷ) 포함',
        'B3': '타이틀 너무 짧음',
        'B4': '방법어 없음 (how 불명확)',
        'C1': '같은 concept_id 내 중복 타이틀 (delta 부재)',
        'C2': '유사 타이틀 (임베딩 기반)',
        'D1': '스텝 1개 파일 (병합 후보)',
        'D2': '스텝 7개+ 파일 (분리/과세분화 후보)',
    }
    for code, d in desc.items():
        if flag_counter.get(code, 0):
            sev = SEVERITY.get(code, '?')
            lines.append(f'  [{code}] {sev:6s} — {d}: {flag_counter[code]}건')
    lines.append('')
    lines.append('[ concept_id별 이상 집중도 Top 15 ]')
    lines.append('  (Phase 2 Claude 배치 우선순위 참고)')
    for cid, cnt in top_concepts:
        total_in_cid = len(concept_titles[cid])
        lines.append(f'  {cid:20s} 이상 {cnt}건 / 전체 {total_in_cid}개')
    lines.append('')
    lines.append(f'[ 출력 파일 ]')
    lines.append(f'  {OUT_DIAG}  — step별 플래그 상세')
    lines.append(f'  {OUT_INDEX}  — concept_id별 타이틀 목록')
    lines.append('')
    lines.append('[ 다음 단계 ]')
    lines.append('  python3 topdown_phase2_claude.py')
    lines.append('  → concept_id별로 Claude에게 패턴 추출 + 이상값 재작성 요청')
    lines.append('=' * 60)

    report_text = '\n'.join(lines)
    print('\n' + report_text)

    with open(OUT_REPORT, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f'\n보고서 저장: {OUT_REPORT}')


if __name__ == '__main__':
    main()
