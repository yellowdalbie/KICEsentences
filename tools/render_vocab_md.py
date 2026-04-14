"""
vocab_standard.json → Docs/vocab_standard.md 자동 렌더링
실행: python3 tools/render_vocab_md.py
"""
import json
from pathlib import Path

VOCAB_FILE = 'vocab_standard.json'
OUT_FILE   = 'Docs/vocab_standard.md'

SECTION_LABELS = {
    '10공수1': '공통수학1 (10공수1)',
    '10공수2': '공통수학2 (10공수2)',
    '12대수':  '대수 (12대수)',
    '12미적Ⅰ': '미적분1 (12미적Ⅰ)',
    '12확통':  '확률과 통계 (12확통)',
}

def prefix(cid):
    for p in SECTION_LABELS:
        if cid.startswith(p):
            return p
    return 'etc'

with open(VOCAB_FILE) as f:
    vocab_raw = json.load(f)

banned_terms = vocab_raw.get('_banned_terms', [])
vocab = {k: v for k, v in vocab_raw.items() if not k.startswith('_')}

lines = [
    '# 수학 개념어 사전 (vocab_standard)',
    '> **단일 진실 공급원**: `vocab_standard.json` — 이 문서는 자동 생성됨 (`tools/render_vocab_md.py`)',
    '>',
    '> **수정 절차**: 성취기준 목록은 교육과정에 고정. **공식 용어(`terms`)만** 추가/수정 가능.',
    '> 1. `vocab_standard.json`에서 해당 `concept_id`의 `"terms"` 배열에 용어 추가',
    '> 2. `python3 tools/render_vocab_md.py` 실행하여 이 문서 재생성',
    '',
]

current_section = None
for cid, entry in vocab.items():
    sec = prefix(cid)
    if sec != current_section:
        current_section = sec
        lines.append(f'\n## {SECTION_LABELS.get(sec, sec)}\n')
        lines.append('| concept_id | 성취기준 요약 | 공식 용어 |')
        lines.append('| :--- | :--- | :--- |')
    terms_str = ', '.join(f'**{t}**' if i == 0 else t
                          for i, t in enumerate(entry['terms']))
    name_short = entry['name'][:35] + ('…' if len(entry['name']) > 35 else '')
    lines.append(f'| `{cid}` | {name_short} | {terms_str} |')

if banned_terms:
    lines += [
        '\n---\n',
        '## ⛔ 금지어 목록 (`_banned_terms`)',
        '> 교육과정 삭제 용어 또는 오용 용어. canonical_name에 포함 시 자동 재시도.',
        '',
    ]
    for t in banned_terms:
        lines.append(f'- `{t}`')

Path(OUT_FILE).write_text('\n'.join(lines), encoding='utf-8')
print(f'✅ 렌더링 완료: {OUT_FILE} ({len(vocab)}개 성취기준, 금지어 {len(banned_terms)}개)')
