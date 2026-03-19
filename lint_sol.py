"""
lint_sol.py - Sol/ 디렉토리 전체 구조적 품질 검증 스크립트

검사 항목:
  T1. 타이틀 LaTeX 포함 ($ 사용)
  T2. 타이틀 Unicode 첨자 변수 (₀~₉)
  T3. 타이틀 18자 미만
  T4. 타이틀 빈칸번호 (가)/(나)/(다) 포함
  T5. 타이틀 보기번호 (ㄱ/ㄴ/ㄷ 검증/확인/판별)

  F1. Trigger 필드 누락
  F2. Trigger 카테고리 [...] 형식 누락
  F3. Action 필드 누락
  F4. Action CPT 코드 없음 (유효 코드 목록 기준)
  F5. Result 필드 누락
  F6. Result 내용 비어있음

  E1. Explanation 블록 누락 (마지막 Step 포함)
  E2. Explanation 내용 너무 짧음 (20자 미만, LaTeX 포함 기준)

  A1. 마지막 Step Explanation에 정답 표기 누락
  A2. Step 번호 불연속
"""

import re
import os
import sqlite3
import csv
from pathlib import Path
from collections import Counter, defaultdict

# ── 설정 ──────────────────────────────────────────
SOL_DIR = Path(__file__).parent / "Sol"
DB_PATH  = Path(__file__).parent / "kice_database.sqlite"

# ── 유효 CPT 코드 로드 ──────────────────────────
def load_valid_cpt_codes():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT id FROM concepts")
    codes = {r[0] for r in cur.fetchall()}
    conn.close()
    return codes

# ── 파일 파싱 ──────────────────────────────────────
def parse_sol_file(fpath):
    """Sol 파일을 Step 단위로 파싱"""
    with open(fpath, encoding="utf-8") as f:
        content = f.read()

    steps = []
    pattern = re.compile(r'## \[Step (\d+)\] (.+?)(?=\n## \[Step |\Z)', re.DOTALL)
    for m in pattern.finditer(content):
        step_num = int(m.group(1))
        body     = m.group(0)
        title    = m.group(2).split('\n')[0].strip()

        # Trigger: 줄 내용 전체 (멀티라인 허용)
        trigger_m = re.search(r'- \*\*Trigger\*\*:\s*(.+?)(?=\n- \*\*|\Z)', body, re.DOTALL)
        trigger   = trigger_m.group(1).strip() if trigger_m else None

        # Action
        action_m = re.search(r'- \*\*Action\*\*:\s*(.+?)(?=\n- \*\*|\Z)', body, re.DOTALL)
        action   = action_m.group(1).strip() if action_m else None

        # Result
        result_m = re.search(r'- \*\*Result\*\*:\s*(.+?)(?=\n- \*\*|\n>|\Z)', body, re.DOTALL)
        result   = result_m.group(1).strip() if result_m else None

        # Explanation: "> " 로 시작하는 줄들을 모두 모음
        expl_lines  = re.findall(r'^> (.+)', body, re.MULTILINE)
        explanation = '\n'.join(expl_lines).strip()

        steps.append({
            'num':         step_num,
            'title':       title,
            'trigger':     trigger,
            'action':      action,
            'result':      result,
            'explanation': explanation,
        })

    return steps

# ── 정답 패턴 ───────────────────────────────────
ANSWER_RE = re.compile(
    r'정답은'
    r'|따라서.*[①②③④⑤]'
    r'|정답.*[①②③④⑤]'
    r'|[①②③④⑤].*입니다'
    r'|\*\*[①②③④⑤]\*\*'
    r'|답은\s*\*\*'          # 답은 **숫자**
    r'|\*\*\d+\*\*\s*입니다'  # **117** 입니다
    r'|\\mathbf\{[^}]+\}'    # \mathbf{117}  (LaTeX bold = 강조 정답)
    r'|따라서\s+\d'           # 따라서 숫자
    r'|정답.*\d'              # 정답 ... 숫자
)

# ── 검사 함수들 ───────────────────────────────────
def check_title(title):
    issues = []
    if '$' in title:
        issues.append('T1:타이틀LaTeX')
    if re.search(r'[₀₁₂₃₄₅₆₇₈₉]', title):
        issues.append('T2:타이틀첨자변수')
    if len(title) < 18:
        issues.append(f'T3:타이틀짧음({len(title)}자)')
    if re.search(r'\([가나다라마]\)', title):
        issues.append('T4:타이틀빈칸번호')
    if re.search(r'[ㄱㄴㄷ].*(검증|확인|판별|참|거짓)', title):
        issues.append('T5:타이틀보기번호')
    return issues

def check_trigger(trigger):
    if trigger is None:
        return ['F1:Trigger누락']
    if not re.search(r'\[.+?\]', trigger):
        return ['F2:Trigger카테고리형식없음']
    return []

def check_action(action, valid_codes):
    if action is None:
        return ['F3:Action누락']
    # 유효 CPT 코드 직접 검색
    found = any(f'[{code}]' in action for code in valid_codes)
    if not found:
        return ['F4:ActionCPT코드없음']
    return []

def check_result(result):
    if result is None:
        return ['F5:Result누락']
    # LaTeX 수식도 내용으로 간주 → 공백 제거 후 길이 확인
    stripped = result.strip()
    if len(stripped) == 0:
        return ['F6:Result비어있음']
    return []

def check_explanation(explanation):
    if not explanation or len(explanation.strip()) < 5:
        return ['E1:Explanation누락']
    # 헤더(📝) 제거 후 실제 내용 길이 (LaTeX 포함 그대로)
    clean = re.sub(r'\*\*📝.*?\*\*', '', explanation).strip()
    if len(clean) < 20:
        return [f'E2:Explanation너무짧음({len(clean)}자)']
    return []

def check_answer(explanation):
    if not ANSWER_RE.search(explanation):
        return ['A1:정답표기없음']
    return []

# ── 메인 ─────────────────────────────────────────
def main():
    valid_codes = load_valid_cpt_codes()

    all_issues = []  # (rel_path, step_num, code, detail)

    md_files = sorted(SOL_DIR.rglob("*.md"))
    print(f"검사 대상: {len(md_files)}개 파일")

    for fpath in md_files:
        rel   = str(fpath.relative_to(SOL_DIR))
        steps = parse_sol_file(fpath)

        if not steps:
            all_issues.append((rel, 0, 'PARSE:Step없음', ''))
            continue

        # Step 번호 연속성
        nums     = [s['num'] for s in steps]
        expected = list(range(1, len(nums) + 1))
        if nums != expected:
            all_issues.append((rel, 0, 'A2:Step번호불연속', str(nums)))

        for i, step in enumerate(steps):
            num     = step['num']
            is_last = (i == len(steps) - 1)

            for code in check_title(step['title']):
                all_issues.append((rel, num, code, step['title'][:70]))
            for code in check_trigger(step['trigger']):
                all_issues.append((rel, num, code, (step['trigger'] or '')[:70]))
            for code in check_action(step['action'], valid_codes):
                all_issues.append((rel, num, code, (step['action'] or '')[:70]))
            for code in check_result(step['result']):
                all_issues.append((rel, num, code, (step['result'] or '')[:70]))
            for code in check_explanation(step['explanation']):
                all_issues.append((rel, num, code, ''))

            if is_last:
                for code in check_answer(step['explanation']):
                    all_issues.append((rel, num, code, ''))

    # ── 결과 출력 ─────────────────────────────────
    if not all_issues:
        print("\n✅ 구조적 이슈 없음. 모든 파일 통과.")
        return

    by_code = Counter(c for _, _, c, _ in all_issues)
    by_file = defaultdict(list)
    for rel, num, code, detail in all_issues:
        by_file[rel].append((num, code, detail))

    print(f"\n총 {len(all_issues)}개 이슈 / {len(by_file)}개 파일\n")

    print("=== 이슈 유형 요약 ===")
    for code, cnt in sorted(by_code.items(), key=lambda x: -x[1]):
        print(f"  {code:<40} {cnt:5d}건")

    print(f"\n=== 파일별 상세 ({len(by_file)}개 파일) ===")
    for rel in sorted(by_file.keys()):
        for num, code, detail in sorted(by_file[rel]):
            step_str = f"Step{num}" if num else "전체"
            det      = f"  → {detail}" if detail else ""
            print(f"  [{rel}] {step_str} | {code}{det}")

    # CSV 저장
    out_csv = Path(__file__).parent / "lint_report.csv"
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['파일', 'Step', '이슈코드', '내용'])
        for rel, num, code, detail in all_issues:
            w.writerow([rel, num, code, detail])
    print(f"\n📄 CSV 저장: {out_csv}")

if __name__ == "__main__":
    main()
