"""정적(서버 없는) 오프라인 패키지용 데이터 추출기.

브라우저는 file:// 에서 fetch/XHR 로 로컬 파일을 읽지 못한다(실측 확인).
그래서 모든 데이터를 <script> 로 실을 수 있는 .js 파일로 내보낸다.

숫자 배열은 base64 로 실어 파일 크기를 줄인다.
  - 스텝 인덱스: 스텝이 2,124개뿐이라 uint16 으로 충분
  - 유사도 점수: 0~1 구간이므로 uint16 으로 양자화 (소수점 4자리 정밀도)

출력: dist_static/data/*.js
"""

import base64
import json
import os
import re
import sqlite3
import sys
import unicodedata

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'dist_static', 'data')

DB_FILE = os.path.join(BASE, 'kice_database.sqlite')
VOCAB_NPZ = os.path.join(BASE, 'kice_query_vocab.npz')
MD_REF_DIR = os.path.join(BASE, 'MD_Ref')


def b64(arr):
    """넘파이 배열을 base64 문자열로."""
    return base64.b64encode(np.ascontiguousarray(arr).tobytes()).decode('ascii')


def write_js(name, varname, payload, note=''):
    path = os.path.join(OUT, name)
    body = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    with open(path, 'w', encoding='utf-8') as f:
        if note:
            f.write(f'// {note}\n')
        f.write(f'window.{varname}=')
        f.write(body)
        f.write(';\n')
    size = os.path.getsize(path)
    print(f'  {name:20s} {size/1e6:7.2f} MB  ({varname})')
    return size


def export_db():
    """문항·해설·개념 데이터."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row

    problems = [
        {
            'p': r['problem_id'],
            'y': r['year'],
            'e': r['exam_type'],
            's': r['subject_type'],
            'n': r['question_no'],
            'a': r['answer'] or '',
        }
        for r in conn.execute('SELECT * FROM problems ORDER BY problem_id')
    ]

    concepts = [
        {
            'id': r['id'],
            'u': r['curriculum_unit'] or '',
            'n': r['standard_name'] or '',
        }
        for r in conn.execute('SELECT * FROM concepts ORDER BY id')
    ]

    steps = [
        {
            'i': r['step_id'],
            'p': r['problem_id'],
            'n': r['step_number'],
            't': r['step_title'] or '',
            'c': r['action_concept_id'] or '',
            'a': r['action_text'] or '',
            'r': r['result_text'] or '',
            'h': r['explanation_html'] or '',
            'x': r['explanation_text'] or '',
        }
        for r in conn.execute('SELECT * FROM steps ORDER BY problem_id, step_number')
    ]

    # 트리거 텍스트 (개념유사도 폴백 검색에서 LIKE 대상)
    trig = {}
    for r in conn.execute('''
            SELECT st.step_id, t.trigger_text, t.normalized_text
            FROM step_triggers st JOIN triggers t ON st.trigger_id = t.trigger_id'''):
        trig[str(r['step_id'])] = [r['trigger_text'] or '', r['normalized_text'] or '']
    conn.close()

    print(f'  문항 {len(problems):,} · 스텝 {len(steps):,} · 개념 {len(concepts)} · 트리거 {len(trig):,}')
    return write_js('db.js', 'KL_DB',
                    {'problems': problems, 'concepts': concepts,
                     'steps': steps, 'triggers': trig},
                    '문항·해설·개념 데이터')


def export_vocab():
    """개념유사도 검색표.

    vocab_vectors(13.3MB)는 이 표를 만들 때만 쓰이고 검색에는 쓰이지 않으므로 제외한다.
    """
    d = np.load(VOCAB_NPZ, allow_pickle=True)
    terms = [str(t) for t in d['terms']]
    idx = d['top_k_indices'].astype(np.uint16)      # 스텝 2,124개 → uint16 안전
    scr = d['top_k_scores'].astype(np.float32)

    assert d['top_k_indices'].max() < 65536, '스텝 수가 uint16 범위를 넘음'
    lo, hi = float(scr.min()), float(scr.max())
    q = np.clip(np.round((scr - lo) / (hi - lo) * 65535), 0, 65535).astype(np.uint16)

    payload = {
        'terms': terms,
        'K': int(idx.shape[1]),
        'idx': b64(idx),
        'scr': b64(q),
        'lo': lo, 'hi': hi,
        'stepIds': [int(x) for x in d['step_ids']],
        'problemIds': [str(x) for x in d['problem_ids']],
        'stepNumbers': [int(x) for x in d['step_numbers']],
    }
    print(f'  어휘 {len(terms):,}개 × Top-{idx.shape[1]} · 점수 범위 [{lo:.4f}, {hi:.4f}]')
    return write_js('vocab.js', 'KL_VOCAB', payload, '개념유사도 검색표 (사전 계산)')


def export_mdref():
    """기출표현 검색용 원문."""
    def strip_frontmatter(text):
        if text.startswith('---'):
            end = text.find('---', 3)
            if end != -1:
                return text[end + 3:].lstrip()
        return text

    docs = {}
    for root, _dirs, files in os.walk(MD_REF_DIR):
        for fn in files:
            if not fn.endswith('.md'):
                continue
            pid = unicodedata.normalize('NFC', fn[:-3])
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, MD_REF_DIR)
            try:
                raw = open(full, encoding='utf-8').read()
            except Exception:
                continue
            docs[pid] = [rel.replace(os.sep, '/'), strip_frontmatter(raw)]
    print(f'  원문 {len(docs):,}개')
    return write_js('mdref.js', 'KL_MDREF', docs, '기출표현 검색용 문항 원문')


def main():
    os.makedirs(OUT, exist_ok=True)
    print('=== 정적 패키지 데이터 추출 ===')
    total = 0
    print('\n[1/3] 문항·해설 DB')
    total += export_db()
    print('\n[2/3] 개념유사도 검색표')
    total += export_vocab()
    print('\n[3/3] 기출표현 원문')
    total += export_mdref()
    print(f'\n합계 {total/1e6:.2f} MB → {OUT}')


if __name__ == '__main__':
    main()
