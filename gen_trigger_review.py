import sqlite3
from collections import defaultdict

conn = sqlite3.connect('kice_database.sqlite')
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT t.trigger_id, t.trigger_text, t.normalized_text,
           GROUP_CONCAT(DISTINCT p.problem_id) as problems
    FROM triggers t
    JOIN step_triggers st ON t.trigger_id = st.trigger_id
    JOIN steps s ON st.step_id = s.step_id
    JOIN problems p ON s.problem_id = p.problem_id
    GROUP BY t.trigger_id
    ORDER BY t.normalized_text, t.trigger_id
''').fetchall()
conn.close()

groups = defaultdict(list)
for r in rows:
    groups[r['normalized_text']].append(r)

lines = ['# 고유 트리거 전체 목록 - 중간 점검용', '']
lines.append(f'총 **{len(rows)}개** 트리거 | **{len(groups)}개** 정규화 카테고리')
lines.append('')
lines.append('> 각 행의 **#번호**가 DB상 고유 트리거 ID입니다. 해당 번호를 언급하여 코멘트해 주세요.')
lines.append('')

for norm, items in sorted(groups.items()):
    lines.append(f'## {norm} ({len(items)}개)')
    lines.append('')
    lines.append('| ID | 트리거 원문 | 출처 문항 |')
    lines.append('|---:|------------|----------|')
    for r in items:
        problems_str = r['problems'] if r['problems'] else '-'
        trigger_escaped = r['trigger_text'].replace('|', r'\|')
        lines.append(f'| **#{r["trigger_id"]}** | {trigger_escaped} | {problems_str} |')
    lines.append('')

with open('trigger_review.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f'Done! trigger_review.md created with {len(rows)} triggers in {len(groups)} categories.')
