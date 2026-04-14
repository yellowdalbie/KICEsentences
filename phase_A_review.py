"""
Phase A-2: 원자 클러스터 대화형 검토 도구
==========================================
clusters_named.json을 읽어 터미널에서 키보드로 검토/수정한다.

키 조작:
  n / →   다음 항목
  p / ←   이전 항목
  ] / [   다음/이전 멤버 Sol 보기 (멀티 멤버 클러스터)
  e       canonical_name 편집
  a       anchor_term 편집
  v       anchor_term을 vocab_standard.terms에 추가
  m       이전 스텝 병합 지시 (단순 계산 스텝)
  d       삭제 표시 (STATUS: DELETE)
  u       병합/삭제 취소
  o       vocab_missing 플래그 수동 해제 (OK로 표시)
  f       보기 모드 전환: 플래그만 ↔ 전체
  s       현재 상태 저장 (자동저장도 됨)
  q       저장 후 종료

입력: .build_cache/phase_A/clusters_named.json
      vocab_standard.json
수정: 두 파일 모두 저장 (즉시 반영)
"""

import json, os, re, sys, tty, termios, shutil

NAMED_FILE    = '.build_cache/phase_A/clusters_named.json'
VOCAB_FILE    = 'vocab_standard.json'
CONCEPTS_FILE = 'concepts.json'

# concept_id 픽커: 과목 폴더 정의 (표시명, id prefix)
CONCEPT_FOLDERS = [
    ('공통수학1', '10공수1'),
    ('공통수학2', '10공수2'),
    ('대수',      '12대수'),
    ('미적분Ⅰ',   '12미적Ⅰ'),
    ('확통',      '12확통'),
    ('중학교',    '9수'),
]

# ── ANSI 색상 ────────────────────────────────────────────────
R   = '\033[31m'    # 빨강
G   = '\033[32m'    # 초록
Y   = '\033[33m'    # 노랑
B   = '\033[34m'    # 파랑
M   = '\033[35m'    # 마젠타
C   = '\033[36m'    # 시안
W   = '\033[97m'    # 밝은 흰색
RB  = '\033[91m'    # 밝은 빨강 (긴급)
GB  = '\033[92m'    # 밝은 초록
YB  = '\033[93m'    # 밝은 노랑
BB  = '\033[94m'    # 밝은 파랑
MB  = '\033[95m'    # 밝은 마젠타
CB  = '\033[96m'    # 밝은 시안
BLD = '\033[1m'     # 굵게
DIM = '\033[2m'     # 흐리게
UL  = '\033[4m'     # 밑줄 (편집 가능 표시)
INV = '\033[7m'     # 반전 (강조)
RST = '\033[0m'     # 리셋
CLR = '\033[2J\033[H'  # 화면 지우기

def color(text, *codes):
    return ''.join(codes) + str(text) + RST

def hr(char='─'):
    w = shutil.get_terminal_size((80, 24)).columns
    return char * w

# ── 한글 자판 → 영문 키 매핑 (한/영 미전환 상태에서도 단축키 작동) ──
_KO_MAP = {
    'ㅂ': 'q', 'ㅈ': 'w', 'ㄷ': 'e', 'ㄱ': 'r', 'ㅅ': 't',
    'ㅛ': 'y', 'ㅕ': 'u', 'ㅑ': 'i', 'ㅐ': 'o', 'ㅔ': 'p',
    'ㅁ': 'a', 'ㄴ': 's', 'ㅇ': 'd', 'ㄹ': 'f', 'ㅎ': 'g',
    'ㅗ': 'h', 'ㅓ': 'j', 'ㅏ': 'k', 'ㅣ': 'l',
    'ㅋ': 'z', 'ㅌ': 'x', 'ㅊ': 'c', 'ㅍ': 'v',
    'ㅠ': 'b', 'ㅜ': 'n', 'ㅡ': 'm',
}

# ── 단일 키 입력 ─────────────────────────────────────────────
def getch():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        # 이스케이프 시퀀스 (화살표 키)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                return {'A': 'UP', 'B': 'DOWN', 'C': 'RIGHT', 'D': 'LEFT'}.get(ch3, ch)
        # 한글 자모 → 영문 키 변환
        return _KO_MAP.get(ch, ch)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

def input_line(prompt):
    """raw mode 해제 후 일반 input 받기"""
    print(prompt, end='', flush=True)
    return input()

# ── concept_id 픽커 ──────────────────────────────────────────

def pick_concept_id(current_id, concepts):
    """
    화살표 키로 concept_id를 선택하는 2단계 TUI 픽커.
    반환: 선택된 id (str) 또는 None (취소/Esc)

    1단계 — 과목 폴더 목록
    2단계 — 과목 내 성취기준 목록 (단원 구분선 포함)
    """
    w = shutil.get_terminal_size((80, 24)).columns

    # 폴더별 데이터 구성
    folders = []
    for fname, prefix in CONCEPT_FOLDERS:
        items = [c for c in concepts if c['id'].startswith(prefix)]
        # 단원(unit) 순서 보존
        units_order, units_map = [], {}
        for c in items:
            unit = c['curriculum_unit'].split(' - ', 1)[-1]
            if unit not in units_map:
                units_map[unit] = []
                units_order.append(unit)
            units_map[unit].append(c)
        folders.append({'name': fname, 'prefix': prefix,
                        'units': units_order, 'units_map': units_map,
                        'count': len(items)})

    def build_item_rows(folder_idx):
        """폴더 내 row 리스트 생성. type: 'back'|'sep'|'item'"""
        folder = folders[folder_idx]
        rows = [{'type': 'back', 'label': '← 폴더 목록으로'}]
        for unit in folder['units']:
            rows.append({'type': 'sep', 'label': unit})
            for c in folder['units_map'][unit]:
                rows.append({'type': 'item', 'id': c['id'],
                             'name': c['standard_name']})
        return rows

    def selectable(row):
        return row['type'] in ('back', 'item')

    def move_sel(rows, cur, direction):
        i = cur + direction
        while 0 <= i < len(rows):
            if selectable(rows[i]):
                return i
            i += direction
        return cur

    def first_sel(rows, prefer_id=None):
        """선호 id가 있으면 그 위치로, 없으면 첫 번째 'item' (back 제외) 으로."""
        if prefer_id:
            for i, r in enumerate(rows):
                if r.get('id') == prefer_id:
                    return i
        # back 버튼 제외하고 첫 item으로 이동
        for i, r in enumerate(rows):
            if r.get('type') == 'item':
                return i
        return 0

    level         = 'folder'
    folder_cur    = 0
    item_rows     = []
    item_cur      = 0
    active_folder = 0

    # 현재 concept_id가 속한 폴더로 초기 커서 이동
    for i, (fname, prefix) in enumerate(CONCEPT_FOLDERS):
        if current_id.startswith(prefix):
            folder_cur = i
            break

    while True:
        print(CLR, end='')

        # ── 1단계: 폴더 목록 ──────────────────────────────────
        if level == 'folder':
            header = color(' concept_id 선택 ', CB, BLD, INV)
            print(f"{header}  {color(f'현재: {current_id}', DIM)}")
            print(color(hr('─'), DIM))
            for i, folder in enumerate(folders):
                is_cur = (i == folder_cur)
                arrow  = color('▶ ', YB, BLD) if is_cur else '  '
                name   = color(folder['name'], W, BLD) if is_cur else color(folder['name'], C)
                count  = color(f"({folder['count']}개)", DIM)
                print(f"  {arrow}{name}  {count}")
            print(color(hr('─'), DIM))
            print(f"  {color('↑↓', YB)}:이동  "
                  f"{color('→/Enter', GB)}:열기  "
                  f"{color('Esc/q', DIM)}:취소")

            ch = getch()
            if ch in ('UP',):
                folder_cur = max(0, folder_cur - 1)
            elif ch in ('DOWN',):
                folder_cur = min(len(folders) - 1, folder_cur + 1)
            elif ch in ('RIGHT', '\r', '\n'):
                active_folder = folder_cur
                item_rows = build_item_rows(active_folder)
                item_cur  = first_sel(item_rows, current_id)
                level = 'item'
            elif ch in ('\x1b', 'q'):
                return None

        # ── 2단계: 성취기준 목록 ─────────────────────────────
        else:
            folder = folders[active_folder]
            header = color(f' {folder["name"]} ', CB, BLD, INV)
            print(f"{header}  {color(f'현재: {current_id}', DIM)}")
            print(color(hr('─'), DIM))

            # 스크롤: item_cur 중심으로 최대 22줄
            WINDOW = 22
            start = max(0, item_cur - WINDOW // 2)
            end   = min(len(item_rows), start + WINDOW)
            if end - start < WINDOW:
                start = max(0, end - WINDOW)

            if start > 0:
                print(color(f'  ▲ 위 {start}개', DIM))

            for i in range(start, end):
                row    = item_rows[i]
                is_cur = (i == item_cur)
                if row['type'] == 'sep':
                    print(f"\n  {color('── ' + row['label'] + ' ──', CB, DIM)}")
                elif row['type'] == 'back':
                    arrow = color('◀ ', YB, BLD) if is_cur else '  '
                    label = color(row['label'], YB) if is_cur else color(row['label'], DIM)
                    print(f"  {arrow}{label}")
                elif row['type'] == 'item':
                    arrow    = color('▶ ', YB, BLD) if is_cur else '  '
                    id_str   = color(row['id'], W, BLD) if is_cur else color(row['id'], CB)
                    cur_mark = color(' ✓', GB, BLD) if row['id'] == current_id else ''
                    name_w   = w - len(row['id']) - 12
                    name_str = color(row['name'][:name_w], DIM)
                    print(f"  {arrow}{id_str}{cur_mark}  {name_str}")

            if end < len(item_rows):
                print(color(f'  ▼ 아래 {len(item_rows) - end}개', DIM))

            print(color(hr('─'), DIM))
            print(f"  {color('↑↓', YB)}:이동  "
                  f"{color('Enter', GB)}:선택  "
                  f"{color('←/Esc', DIM)}:뒤로")

            ch = getch()
            if ch in ('UP',):
                item_cur = move_sel(item_rows, item_cur, -1)
            elif ch in ('DOWN',):
                item_cur = move_sel(item_rows, item_cur, 1)
            elif ch in ('\r', '\n'):
                row = item_rows[item_cur]
                if row['type'] == 'item':
                    return row['id']
                elif row['type'] == 'back':
                    level = 'folder'
            elif ch in ('LEFT', '\x1b'):
                level = 'folder'
            elif ch == 'q':
                return None


# ── Sol 파일 파싱 ────────────────────────────────────────────
def _read_sol(file_path):
    """Sol 파일 읽기. 경로 보정 포함."""
    candidates = [file_path, file_path.lstrip('./'), os.path.join('.', file_path.lstrip('./'))]
    for p in candidates:
        try:
            with open(p, encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            continue
    return None

def _split_sol_steps(content):
    """## [Step N] 기준으로 섹션 분리. 반환: list of (step_num, title, body_lines)"""
    pattern = re.compile(r'^(## \[Step (\d+)\]\s*(.+?))$', re.MULTILINE)
    steps   = []
    headers = list(pattern.finditer(content))
    for i, m in enumerate(headers):
        step_num = int(m.group(2))
        title    = m.group(3).strip()
        start    = m.start()
        end      = headers[i+1].start() if i+1 < len(headers) else len(content)
        body     = content[start:end].strip().split('\n')
        steps.append((step_num, title, body))
    return steps

def find_sol_neighbors(file_path, raw_action):
    """
    raw_action에 해당하는 Sol Step과 그 앞/뒤 스텝을 반환.
    반환: (cur_info, prev_info, next_info)
      각 info = (step_num, title, body_lines) 또는 None
    """
    content = _read_sol(file_path)
    if not content:
        return None, None, None
    steps = _split_sol_steps(content)
    if not steps:
        return None, None, None

    ra_key = re.sub(r'[^\w가-힣]', '', raw_action[:40]).lower()
    best_idx, best_score = 0, 0
    for idx, (step_num, title, body) in enumerate(steps):
        for line in body:
            if '**Action**' not in line:
                continue
            line_key = re.sub(r'[^\w가-힣]', '', line).lower()
            score = sum(1 for c in ra_key if c in line_key) / max(len(ra_key), 1)
            if score > best_score:
                best_score, best_idx = score, idx

    cur_info  = steps[best_idx]
    prev_info = steps[best_idx - 1] if best_idx > 0 else None
    next_info = steps[best_idx + 1] if best_idx < len(steps) - 1 else None
    return cur_info, prev_info, next_info


def pick_merge_direction(cur_info, prev_info, next_info):
    """
    이전/현재/이후 스텝을 보여주고 병합 방향을 키보드로 선택.
    반환: (target_step_num, direction) 또는 (None, None) — 취소
      direction: 'up' | 'down'
    """
    w = shutil.get_terminal_size((80, 24)).columns

    def fmt_step_preview(info, label_color, label):
        """스텝 정보를 3줄(Trigger/Action/Result)로 요약."""
        num, title, body = info
        lines = [f" {color(f'[{label} Step {num}]', *label_color)}  "
                 f"{color(title or '', DIM)}"]
        for line in body[1:]:
            stripped = line.strip()
            if stripped.startswith('- **Trigger**'):
                lines.append(color('   ' + line[:w-5], BB))
            elif stripped.startswith('- **Action**'):
                lines.append(color('   ' + line[:w-5], YB, BLD))
            elif stripped.startswith('- **Result**'):
                lines.append(color('   ' + line[:w-5], GB))
        return lines

    while True:
        print(CLR, end='')
        print(color(' 병합 방향 선택 ', MB, BLD, INV))
        print(color(hr('─'), DIM))

        # 이전 스텝
        if prev_info:
            for l in fmt_step_preview(prev_info, (MB, BLD), '이전'):
                print(l)
            print(color(f"  → ↑ 또는 p: 위 Step {prev_info[0]}으로 병합", MB))
        else:
            print(color(' ▲ (첫 스텝 — 이전 없음)', DIM))

        print()
        # 현재 스텝 (검토 중)
        for l in fmt_step_preview(cur_info, (YB, BLD, INV), '현재'):
            print(l)

        print()
        # 다음 스텝
        if next_info:
            for l in fmt_step_preview(next_info, (CB, BLD), '다음'):
                print(l)
            print(color(f"  → ↓ 또는 n: 아래 Step {next_info[0]}으로 병합", CB))
        else:
            print(color(' ▼ (마지막 스텝 — 다음 없음)', DIM))

        print(color(hr('─'), DIM))
        hints = []
        if prev_info:
            hints.append(color(f'↑/p: Step {prev_info[0]}으로', MB, BLD))
        if next_info:
            hints.append(color(f'↓/n: Step {next_info[0]}으로', CB, BLD))
        hints.append(color('Esc/q: 취소', DIM))
        print('  ' + '   '.join(hints))

        ch = getch()
        if ch in ('UP', 'p') and prev_info:
            return prev_info[0], 'up'
        elif ch in ('DOWN', 'n') and next_info:
            return next_info[0], 'down'
        elif ch in ('\x1b', 'q'):
            return None, None

def load_sol_step(file_path, raw_action):
    """
    Sol 파일에서 raw_action과 가장 잘 매칭되는 [Step N] 섹션을 찾아 반환.
    step_number는 chunk 순번이라 Sol Step 번호와 다를 수 있으므로
    Action 라인 텍스트로 매칭한다.

    반환: (step_num, title, lines) 또는 (None, None, [])
    """
    content = _read_sol(file_path)
    if content is None:
        return None, None, []

    steps = _split_sol_steps(content)
    if not steps:
        return None, None, []

    # raw_action의 앞 30자 키워드로 Action 라인 매칭
    ra_key = re.sub(r'[^\w가-힣]', '', raw_action[:40]).lower()

    best_step, best_title, best_body, best_score = None, None, [], 0
    for step_num, title, body in steps:
        for line in body:
            if '**Action**' not in line:
                continue
            line_key = re.sub(r'[^\w가-힣]', '', line).lower()
            # 공통 문자 수로 유사도 추정
            common = sum(1 for c in ra_key if c in line_key)
            score  = common / max(len(ra_key), 1)
            if score > best_score:
                best_score = score
                best_step, best_title, best_body = step_num, title, body

    if best_score < 0.2:
        # 매칭 실패 시 첫 번째 스텝 반환
        if steps:
            return steps[0][0], steps[0][1], steps[0][2]
        return None, None, []

    return best_step, best_title, best_body

def fmt_sol_lines(lines, w, raw_action):
    """Sol 스텝 라인을 화면 폭에 맞게 포맷."""
    out = []
    ra_key = raw_action[:30].lower()
    for line in lines:
        truncated = line[:w - 4]
        if line.startswith('- **Trigger**'):
            out.append(color('  ' + truncated, BB))          # 파랑: Trigger
        elif line.startswith('- **Action**'):
            out.append(color('  ' + truncated, YB, BLD))     # 밝은노랑+굵게: Action (핵심)
        elif line.startswith('- **Result**'):
            out.append(color('  ' + truncated, GB))          # 밝은초록: Result
        elif line.startswith('## [Step'):
            out.append(color('  ' + truncated, W, BLD))
        elif line.startswith('>'):
            out.append(DIM + '  ' + truncated + RST)
        else:
            out.append('  ' + truncated)
    return out

# ── 데이터 로드/저장 ─────────────────────────────────────────
def load_data():
    with open(NAMED_FILE) as f:
        data = json.load(f)
    with open(VOCAB_FILE) as f:
        vocab = json.load(f)
    with open(CONCEPTS_FILE) as f:
        concepts = json.load(f)
    return data, vocab, concepts

def save_data(data, vocab):
    with open(NAMED_FILE, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(VOCAB_FILE, 'w') as f:
        json.dump(vocab, f, ensure_ascii=False, indent=2)

# ── 화면 렌더링 ──────────────────────────────────────────────
def render(cluster, idx, total, mode, vocab, modified_count, sol_member_idx=0):
    w = shutil.get_terminal_size((80, 24)).columns

    cid        = cluster['cluster_id']
    concept_id = cluster['concept_id']
    members    = cluster.get('members', [])
    canon_raw  = cluster.get('canonical_name')
    anchor_raw = cluster.get('anchor_term')
    is_pure    = cluster.get('is_pure')
    vocab_miss = cluster.get('vocab_missing', False)
    deleted    = cluster.get('_delete', False)
    reviewed   = cluster.get('_reviewed', False)
    merge_into = cluster.get('_merge_into')   # 병합 지시: 이전 스텝 번호
    no_canon   = not canon_raw   # canonical_name 자체가 없음 → 최우선 수정

    terms  = vocab.get(concept_id, {}).get('terms', []) if isinstance(vocab.get(concept_id), dict) else []

    # ── 헤더 ───────────────────────────────────────────────────
    # 헤더 배경: 삭제=빨강반전 / 미검토+플래그=노랑반전 / 검토완료=초록반전 / 일반=기본
    if deleted:
        hdr_bg = f'\033[41m{BLD}'
    elif merge_into is not None:
        hdr_bg = f'\033[45m{BLD}'           # 마젠타 배경: 병합 지시
    elif no_canon or (vocab_miss and is_pure is False):
        hdr_bg = f'\033[41m{BLD}'
    elif vocab_miss or is_pure is False:
        hdr_bg = f'\033[43m\033[30m{BLD}'
    elif reviewed:
        hdr_bg = f'\033[42m\033[30m{BLD}'
    else:
        hdr_bg = f'{DIM}'

    mode_str = '플래그만' if mode == 'flag' else '전체보기'
    review_str = '  ✓검토완료' if reviewed else ''

    print(CLR, end='')
    print(hdr_bg + hr('━') + RST)
    print(hdr_bg
          + f"  #{idx+1}/{total}  [{mode_str}]  수정:{modified_count}개"
          + f"  클러스터#{cid}  멤버{len(members)}개{review_str}"
          + RST)
    print(hdr_bg + hr('━') + RST)

    # ── 상태 플래그 배너 (문제 있을 때만) ─────────────────────
    banners = []
    if deleted:
        banners.append(color(f' 🗑  삭제 예정  ', RB, BLD, INV))
    if merge_into is not None:
        merge_dir  = cluster.get('_merge_direction', 'up')
        dir_arrow  = '↑' if merge_dir == 'up' else '↓'
        banners.append(color(f' 🔀  {dir_arrow} Step {merge_into}에 병합 예정  ', MB, BLD, INV))
    if no_canon and merge_into is None:
        banners.append(color(f' ✗  canonical_name 없음 → [e] 필수  ', RB, BLD))
    elif vocab_miss and is_pure is False:
        banners.append(color(f' ⚠  vocab없음 + 분리필요 → 두 가지 모두 처리  ', RB, BLD))
    elif vocab_miss:
        banners.append(color(f' ⚠  vocab없음 → [e][a][v] 중 택일  ', YB, BLD))
    elif is_pure is False:
        banners.append(color(f' ✂  분리 필요  ', MB, BLD))
    if banners:
        print(' ' + '  '.join(banners))
        print(color(hr('─'), DIM))

    # ── 개념 정보 ──────────────────────────────────────────────
    print(f" {color('concept_id', DIM)} : {color(concept_id, CB, BLD)}  ")
    if terms:
        # 각 term이 canonical_name에 있는지 색으로 표시
        term_display = []
        for t in terms:
            if canon_raw and t in canon_raw:
                term_display.append(color(t, GB, BLD))   # 매칭된 term → 밝은초록+굵게
            else:
                term_display.append(color(t, DIM))        # 미매칭 → 흐리게
        print(f" {color('terms', DIM)}      : {' · '.join(term_display)}")
    else:
        print(f" {color('terms', DIM)}      : {color('vocab_standard에 없음', YB)}")

    print(color(hr('─'), DIM))

    # ── 멤버 목록 ──────────────────────────────────────────────
    sol_member_idx = min(sol_member_idx, len(members) - 1)
    cur_member = members[sol_member_idx]
    nav_hint = f"  {color(f'{sol_member_idx+1}/{len(members)}', CB)}  {color('[  ]: 전환', DIM)}" if len(members) > 1 else ''
    print(f" {color('멤버', DIM)}{nav_hint}")
    for i, m in enumerate(members[:6]):
        ra      = m.get('raw_action', '').replace('\n', ' ')
        sim_val = m.get('top1_sim', 0)
        sim_c   = GB if sim_val >= 0.6 else (YB if sim_val >= 0.4 else RB)
        sim_str = color(f'sim={sim_val:.3f}', sim_c)
        if i == sol_member_idx:
            # 현재 선택 멤버: 밝게
            print(f"   {color('▶', YB, BLD)} {color(ra[:w-16], W)}  {sim_str}")
        else:
            print(f"     {color(ra[:w-16], DIM)}  {sim_str}")
    if len(members) > 6:
        print(f"   {color(f'... 외 {len(members)-6}개', DIM)}")

    # ── Sol 뷰어 ───────────────────────────────────────────────
    sol_file = cur_member.get('file', '')
    sol_ra   = cur_member.get('raw_action', '')
    if sol_file and sol_ra:
        sol_step, sol_title, sol_lines = load_sol_step(sol_file, sol_ra)
        fname = os.path.basename(sol_file)
        print(color(hr('·'), DIM))
        if sol_lines:
            print(f" {color('[Sol]', CB, BLD)} {color(fname, W)}  "
                  f"{color(f'Step {sol_step}', YB, BLD)}  {color(sol_title or '', DIM)}")
            formatted = fmt_sol_lines(sol_lines[1:], w, sol_ra)
            for l in formatted:
                if any(k in l for k in ['Trigger', 'Action', 'Result']):
                    print(l)
            expl = [l for l in formatted[1:] if l.strip().startswith(DIM)]
            if expl:
                print(f"  {color(f'[해설 {len(expl)}줄]', DIM)}")
        else:
            print(f" {color('[Sol]', DIM)} {color(fname, DIM)} — {color('스텝 파싱 실패', R)}")

        # 이전/이후 스텝 미리보기 (병합 판단용)
        _, prev_info, next_info = find_sol_neighbors(sol_file, sol_ra)
        has_neighbor = (prev_info is not None or next_info is not None)
        if has_neighbor:
            if prev_info:
                prev_action = next((l for l in prev_info[2] if '**Action**' in l), '')
                print(f" {color(f'[이전 Step {prev_info[0]}]', MB)}  "
                      f"{color(prev_info[1] or '', DIM)}")
                print(f"   {color(prev_action[:w-6], DIM)}")
            if next_info:
                next_action = next((l for l in next_info[2] if '**Action**' in l), '')
                print(f" {color(f'[다음 Step {next_info[0]}]', CB)}  "
                      f"{color(next_info[1] or '', DIM)}")
                print(f"   {color(next_action[:w-6], DIM)}")
            if merge_into is None:
                print(f"   {color('→ [m] 병합 방향 선택', MB)}")

    print(color(hr('─'), DIM))

    # ── canonical_name / anchor_term (핵심 편집 영역) ──────────
    # canonical_name 색상 결정
    if no_canon:
        cn_color = (RB, BLD, INV)    # 반전 빨강: 즉시 수정 필요
        cn_text  = '(없음)  ← [e] 필수 입력'
    elif vocab_miss:
        cn_color = (YB, BLD, UL)     # 밑줄 노랑: 수정 권장
        cn_text  = canon_raw
    else:
        cn_color = (GB, BLD, UL)     # 밑줄 초록: OK (편집 가능)
        cn_text  = canon_raw

    # anchor_term 색상 결정
    if not anchor_raw:
        an_color = (RB, BLD)
        an_text  = '(없음)  ← [a] 입력'
    elif vocab_miss:
        an_color = (YB, UL)          # 밑줄 노랑: vocab 추가 가능
        an_text  = anchor_raw
    else:
        an_color = (CB, UL)          # 밑줄 시안: 편집 가능
        an_text  = anchor_raw

    label_cn = color(' [e] canonical_name', YB)
    label_an = color(' [a] anchor_term   ', CB)
    print(f"{label_cn} : {color(cn_text, *cn_color)}")
    print(f"{label_an} : {color(an_text, *an_color)}")

    # vocab 매칭 안내
    if vocab_miss and terms:
        print(f"       {color('→ terms에서 선택:', DIM)} "
              + '  '.join(color(f'[{t}]', YB) for t in terms[:5]))
        if not anchor_raw or anchor_raw not in terms:
            print(f"       {color('[v] anchor_term을 vocab에 추가  |  [o] 이 항목 OK로 표시', Y)}")

    # ── 키 안내 ────────────────────────────────────────────────
    print(color(hr('━'), DIM))
    nav   = f"{color('n/→',YB)}:다음  {color('p/←',YB)}:이전  {color('[/]',CB)}:Sol멤버"
    edit  = f"{color('e',YB,BLD)}:이름  {color('a',CB,BLD)}:anchor  {color('c',MB,BLD)}:개념변경  {color('v',GB,BLD)}:vocab추가  {color('o',DIM)}:OK"
    mgmt  = f"{color('m',MB)}:병합  {color('d',RB)}:삭제  {color('u',DIM)}:취소  {color('f',DIM)}:모드전환  {color('s',DIM)}:저장  {color('q',DIM)}:종료"
    print(f" {nav}   {edit}")
    print(f" {mgmt}")
    print(color(hr('━'), DIM))

# ── 메인 루프 ────────────────────────────────────────────────
def build_view(data, mode):
    """현재 모드에 따라 표시할 cluster 인덱스 목록 반환"""
    clusters = data.get('clusters', []) + data.get('needs_review', [])
    if mode == 'flag':
        indices = [i for i, c in enumerate(clusters)
                   if (c.get('vocab_missing') or c.get('is_pure') is False)
                   and not c.get('_reviewed')]
    else:
        indices = list(range(len(clusters)))
    return clusters, indices

def main():
    if not os.path.exists(NAMED_FILE):
        print(f"오류: {NAMED_FILE} 없음. phase_A_cluster_namer.py 먼저 실행하세요.")
        sys.exit(1)

    data, vocab, concepts = load_data()
    clusters_all = data.get('clusters', []) + data.get('needs_review', [])

    mode = 'flag'   # 'flag' | 'all'
    clusters, view_indices = build_view(data, mode)
    pos            = 0   # view_indices 내 현재 위치
    sol_member_idx = 0   # 현재 클러스터에서 Sol을 보여줄 멤버 인덱스
    modified_count = 0

    if not view_indices:
        print(color("플래그 항목이 없습니다. [f]로 전체 보기로 전환하세요.", G))
        mode = 'all'
        clusters, view_indices = build_view(data, mode)

    while True:
        if not view_indices:
            print(CLR + color("표시할 항목이 없습니다.", Y))
            ch = getch()
            if ch in ('q', '\x03'):
                break
            continue

        pos = max(0, min(pos, len(view_indices) - 1))
        cluster = clusters[view_indices[pos]]
        render(cluster, pos, len(view_indices), mode, vocab, modified_count, sol_member_idx)

        ch = getch()

        # 이동
        if ch in ('n', 'RIGHT', '\r', '\n'):
            if pos < len(view_indices) - 1:
                pos += 1
                sol_member_idx = 0
            else:
                print(f"\n  {color('마지막 항목입니다.', Y)}", flush=True)
                import time; time.sleep(0.8)
        elif ch in ('p', 'LEFT'):
            pos = max(0, pos - 1)
            sol_member_idx = 0

        # Sol 멤버 전환 (멀티 멤버 클러스터)
        elif ch == ']':
            n_members = len(clusters[view_indices[pos]].get('members', []))
            sol_member_idx = min(sol_member_idx + 1, n_members - 1)
        elif ch == '[':
            sol_member_idx = max(0, sol_member_idx - 1)

        # 병합 방향 선택 후 지시
        elif ch == 'm':
            cur_member = clusters[view_indices[pos]]['members'][sol_member_idx]
            sol_file   = cur_member.get('file', '')
            sol_ra     = cur_member.get('raw_action', '')
            cur_info, prev_info, next_info = find_sol_neighbors(sol_file, sol_ra)
            if cur_info is None:
                print(f"\n  {color('Sol 파일을 찾을 수 없습니다.', R)}", flush=True)
                import time; time.sleep(1)
            elif prev_info is None and next_info is None:
                print(f"\n  {color('단독 스텝이라 병합할 대상이 없습니다.', Y)}", flush=True)
                import time; time.sleep(1)
            else:
                target_num, direction = pick_merge_direction(cur_info, prev_info, next_info)
                if target_num is not None:
                    cluster['_merge_into']        = target_num
                    cluster['_merge_direction']   = direction   # 'up' | 'down'
                    cluster['_reviewed']          = True
                    modified_count += 1

        # 편집: canonical_name
        elif ch == 'e':
            print(CLR)
            old = cluster.get('canonical_name', '')
            print(f"  현재: {color(old, Y)}")
            print(f"  terms: {', '.join(vocab.get(cluster['concept_id'], {}).get('terms', []) if isinstance(vocab.get(cluster['concept_id']), dict) else [])}")
            new = input_line(f"  새 canonical_name (Enter=유지): ").strip()
            if new:
                cluster['canonical_name'] = new
                # vocab 재검증
                terms = vocab.get(cluster['concept_id'], {}).get('terms', []) if isinstance(vocab.get(cluster['concept_id']), dict) else []
                banned = vocab.get('_banned_terms', [])
                cluster['vocab_missing'] = not any(t in new for t in terms) if terms else False
                cluster['_reviewed'] = True
                modified_count += 1

        # 편집: anchor_term
        elif ch == 'a':
            print(CLR)
            old = cluster.get('anchor_term', '')
            print(f"  현재 anchor: {color(old, Y)}")
            new = input_line(f"  새 anchor_term (Enter=유지): ").strip()
            if new:
                cluster['anchor_term'] = new
                cluster['_reviewed'] = True
                modified_count += 1

        # vocab_standard에 anchor_term 추가
        elif ch == 'v':
            anchor = cluster.get('anchor_term', '').strip()
            cid    = cluster['concept_id']
            if not anchor:
                print(f"\n  {color('anchor_term이 없습니다. [a]로 먼저 입력하세요.', R)}", flush=True)
                import time; time.sleep(1)
            else:
                if not isinstance(vocab.get(cid), dict):
                    vocab[cid] = {'terms': []}
                terms = vocab[cid].setdefault('terms', [])
                if anchor not in terms:
                    terms.append(anchor)
                    save_data(data, vocab)
                    cluster['vocab_missing'] = False
                    cluster['_reviewed'] = True
                    modified_count += 1
                    print(f"\n  {color(f'✓ \"{anchor}\" → {cid}.terms 추가됨', G)}", flush=True)
                else:
                    print(f"\n  {color(f'\"{anchor}\"은 이미 terms에 있습니다.', DIM)}", flush=True)
                import time; time.sleep(0.8)

        # 플래그 수동 해제 (OK)
        elif ch == 'o':
            cluster['vocab_missing'] = False
            cluster['_reviewed'] = True
            modified_count += 1
            # 플래그 모드면 view 재구성 후 같은 위치 유지
            if mode == 'flag':
                clusters, view_indices = build_view(data, mode)

        # concept_id 변경 (화살표 픽커) — 변경 후 같은 클러스터에 머뭄
        elif ch == 'c':
            old_cid = cluster.get('concept_id', '')
            new_cid = pick_concept_id(old_cid, concepts)
            if new_cid and new_cid != old_cid:
                cluster['concept_id'] = new_cid
                # vocab_missing 재검증 (reviewed 표시 및 뷰 재구성 없음)
                terms = (vocab.get(new_cid, {}).get('terms', [])
                         if isinstance(vocab.get(new_cid), dict) else [])
                cn    = cluster.get('canonical_name') or ''
                cluster['vocab_missing'] = (not any(t in cn for t in terms)) if terms else False
                modified_count += 1

        # 삭제 표시
        elif ch == 'd':
            cluster['_delete'] = True
            cluster['_reviewed'] = True
            modified_count += 1

        # 삭제/병합 취소
        elif ch == 'u':
            cluster['_delete']     = False
            cluster['_merge_into'] = None
            modified_count += 1

        # 보기 모드 전환
        elif ch == 'f':
            mode = 'all' if mode == 'flag' else 'flag'
            clusters, view_indices = build_view(data, mode)
            pos = 0

        # 저장
        elif ch == 's':
            save_data(data, vocab)
            print(f"\n  {color('저장 완료', G)}", flush=True)
            import time; time.sleep(0.5)

        # 종료
        elif ch in ('q', '\x03'):
            save_data(data, vocab)
            total_clusters = data.get('clusters', [])
            reviewed = sum(1 for c in total_clusters if c.get('_reviewed'))
            deleted  = sum(1 for c in total_clusters if c.get('_delete'))
            print(CLR)
            print(color("=== 저장 완료 ===", G))
            print(f"  검토 완료: {reviewed}개  |  삭제 표시: {deleted}개  |  수정: {modified_count}개")
            print(f"\n다음: python3 phase_A_review_builder.py")
            break

    # _reviewed / _delete 결과를 review_builder가 활용할 수 있도록 이미 저장됨

if __name__ == '__main__':
    main()
