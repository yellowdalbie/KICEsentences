"""
check_cpt_fit.py - Phase 2: CPT 코드 적합성 검증

각 Step의 Action에 사용된 CPT 코드가 실제 내용과 맞는지 검사합니다.
키워드 불일치가 감지된 케이스를 출력하여 수동 검토 목록을 생성합니다.

방법:
  - concepts.keywords + 수동 보강 키워드 사전으로 각 코드의 핵심 개념어 구성
  - Step의 (타이틀 + Trigger + Action 텍스트)에서 해당 코드의 키워드가
    하나도 등장하지 않으면 '불일치 의심'으로 플래그
  - 단, 수식($...$) 내용도 검사 텍스트에 포함

출력:
  - cpt_fit_report.csv : 불일치 의심 케이스 전체
  - 콘솔 요약
"""

import re
import json
import sqlite3
import csv
from pathlib import Path
from collections import defaultdict

SOL_DIR = Path(__file__).parent / "Sol"
DB_PATH  = Path(__file__).parent / "kice_database.sqlite"

# ── CPT 코드별 검사 키워드 (DB keywords + 보강) ──────────────────────────
EXTRA_KEYWORDS = {
    # 중학교
    "9수01-01": ["소수"],
    "9수01-02": ["GCD", "LCM"],
    "9수02-03": ["등식의 성질"],

    # 공통수학1
    "10공수1-01-01": ["전개", "곱셈공식"],
    "10공수1-01-02": ["나머지정리", "인수정리", "나머지"],
    "10공수1-01-03": ["인수분해", "공통인수"],
    "10공수1-02-01": ["허수", "허수단위"],
    "10공수1-02-02": ["판별식", "허근", "실근", "중근"],
    "10공수1-02-03": ["근과 계수", "비에타", "두 근의 합", "두 근의 곱", "두 근"],
    "10공수1-02-04": ["이차방정식", "이차함수"],
    "10공수1-02-05": ["직선의 위치 관계", "교점", "이차함수의 그래프"],
    "10공수1-02-06": ["최대", "최소", "꼭짓점"],
    "10공수1-02-07": ["삼차방정식", "사차방정식", "삼차", "사차"],
    "10공수1-02-08": ["연립이차방정식", "연립이차"],
    "10공수1-02-09": ["연립일차부등식", "부등식", "범위"],
    "10공수1-02-10": ["절댓값", "일차부등식"],
    "10공수1-02-11": ["이차부등식", "연립이차부등식"],
    "10공수1-03-01": ["합의 법칙", "곱의 법칙", "수형도", "경우의 수", "가짓수", "경우 분류"],
    "10공수1-03-02": ["순열", "nPr"],
    "10공수1-03-03": ["조합", "nCr", "이항계수"],

    # 공통수학2
    "10공수2-01-01": ["내분점", "중점", "외분점", "좌표", "내분", "외분"],
    "10공수2-01-02": ["평행", "수직", "기울기"],
    "10공수2-01-03": ["점과 직선 사이의 거리", "수선의 발"],
    "10공수2-01-04": ["원의 방정식", "원의 중심", "반지름"],
    "10공수2-01-05": ["원과 직선", "접선", "위치 관계"],
    "10공수2-01-06": ["평행이동"],
    "10공수2-01-07": ["대칭이동", "x축 대칭", "y축 대칭", "원점 대칭"],
    "10공수2-02-01": ["집합", "원소", "원소나열법"],
    "10공수2-02-02": ["부분집합", "포함관계"],
    "10공수2-02-03": ["교집합", "합집합", "여집합", "벤 다이어그램"],
    "10공수2-02-04": ["명제", "조건", "모든", "어떤"],
    "10공수2-02-05": ["역", "대우"],
    "10공수2-02-06": ["충분조건", "필요조건", "필요충분"],
    "10공수2-02-07": ["귀류법", "대우 증명"],
    "10공수2-02-08": ["절대부등식", "AM-GM"],
    "10공수2-03-01": ["정의역", "치역", "공역", "함수"],
    "10공수2-03-02": ["합성함수"],
    "10공수2-03-03": ["역함수"],
    "10공수2-03-04": ["유리함수", "점근선"],
    "10공수2-03-05": ["무리함수"],

    # 대수(12) - concepts.json 실제 코드 의미 기반
    "12대수01-01": ["거듭제곱근", "n제곱근", "제곱근", "n승근"],
    "12대수01-02": ["지수의 확장", "유리수 지수", "실수 지수", "지수함수", "a^x"],
    "12대수01-03": ["지수법칙", "지수방정식", "지수부등식", "같은 밑", "밑을 통일", "지수비교"],
    "12대수01-04": ["로그", "log", "상용로그", "로그방정식", "로그부등식", "밑변환"],
    "12대수02-01": ["호도법", "라디안", "일반각", "부채꼴", "호의 길이", "θ"],
    "12대수02-02": ["삼각함수", "sin", "cos", "tan", "주기", "삼각", "사인", "코사인"],
    "12대수02-03": ["사인법칙", "코사인법칙", "삼각형 넓이", "삼각형"],
    "12대수03-01": ["수열", "일반항", "n항"],
    "12대수03-02": ["등차수열", "공차", "등차", "등차중항"],
    "12대수03-03": ["등비수열", "공비", "등비", "등비중항"],
    "12대수03-04": ["시그마", "∑", "\\sum", "합 공식", "자연수 거듭제곱", "n항까지의 합", "수열의 합"],
    "12대수03-05": ["계차수열", "군수열", "분수형", "부분분수", "여러 가지 수열", "통분"],
    "12대수03-06": ["점화식", "귀납적 정의", "수학적 귀납법"],

    # 미적Ⅰ - concepts.json 실제 코드 의미 기반 (완전 재작성)
    "12미적Ⅰ-01-01": ["함수의 극한", "극한", "lim", "좌극한", "우극한"],
    "12미적Ⅰ-01-02": ["극한의 성질", "극한값", "극한"],
    "12미적Ⅰ-01-03": ["연속", "불연속", "연속함수"],
    "12미적Ⅰ-01-04": ["중간값 정리", "최대최소 정리", "최대", "최소"],
    "12미적Ⅰ-02-01": ["미분계수", "순간변화율", "평균변화율", "f'(a)", "미분계수의 정의"],
    "12미적Ⅰ-02-02": ["미분가능성", "연속성", "미분가능", "연속"],
    "12미적Ⅰ-02-03": ["도함수", "미분", "f'(x)", "도함수를", "미분하여", "미분하면"],
    "12미적Ⅰ-02-04": ["미분법", "곱의 미분", "다항함수", "곱의 미분법"],
    "12미적Ⅰ-02-05": ["접선의 기울기", "접선의 방정식", "접선", "법선"],
    "12미적Ⅰ-02-06": ["평균값 정리", "롤의 정리"],
    "12미적Ⅰ-02-07": ["증가와 감소", "극대와 극소", "극대", "극소", "극값", "증감표", "증가", "감소", "부호 변화"],
    "12미적Ⅰ-02-08": ["그래프의 개형", "개형", "오목", "볼록", "변곡점", "그래프를 그"],
    "12미적Ⅰ-02-09": ["방정식과 부등식", "근의 개수", "실근의 개수", "교점의 개수"],
    "12미적Ⅰ-02-10": ["속도", "가속도", "위치", "이동거리"],
    "12미적Ⅰ-03-01": ["부정적분", "원시함수", "역도함수", "적분상수", "적분"],
    "12미적Ⅰ-03-02": ["부정적분의 계산", "부정적분", "적분하면", "적분하여"],
    "12미적Ⅰ-03-03": ["정적분의 개념", "정적분의 성질", "정적분"],
    "12미적Ⅰ-03-04": ["부정적분과 정적분", "미적분의 기본정리", "기본정리", "정적분으로 정의된", "주기함수"],
    "12미적Ⅰ-03-05": ["도형의 넓이", "넓이", "곡선으로 둘러싸인", "면적"],
    "12미적Ⅰ-03-06": ["속도", "거리", "이동거리", "위치"],

    # 확통 - concepts.json 실제 코드 의미 기반
    "12확통01-01": ["중복순열", "같은 것이 있는 순열", "원순열"],
    "12확통01-02": ["중복조합", "_nH"],
    "12확통01-03": ["이항정리", "이항계수", "파스칼"],
    "12확통02-01": ["수학적 확률", "통계적 확률", "표본공간", "사건", "경우의 수", "확률"],
    "12확통02-02": ["확률의 덧셈정리", "덧셈정리", "배반사건", "합사건"],
    "12확통02-03": ["여사건의 확률", "여사건", "1-P"],
    "12확통02-04": ["조건부확률", "P(A|B)", "P(B|A)"],
    "12확통02-05": ["독립", "종속", "독립시행", "서로 독립"],
    "12확통02-06": ["확률의 곱셈정리", "곱셈정리"],
    "12확통03-01": ["확률변수", "확률분포", "이산확률변수", "확률질량함수"],
    "12확통03-02": ["기댓값", "분산", "표준편차", "E(X)", "V(X)", "평균", "E("],
    "12확통03-03": ["이항분포", "B(n,p)", "베르누이"],
    "12확통03-04": ["정규분포", "이항분포와의 관계", "표준정규분포", "정규분포표", "z값"],
    "12확통03-05": ["모집단", "표본", "표본추출"],
    "12확통03-06": ["표본평균", "모평균", "표본비율"],
    "12확통03-07": ["모평균 추정", "모비율 추정", "신뢰구간"],
}

def load_cpt_data():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    cur.execute("SELECT id, keywords FROM concepts")
    rows = cur.fetchall()
    conn.close()

    cpt_keywords = {}
    for code, kw_json in rows:
        kws = json.loads(kw_json) if kw_json else []
        extras = EXTRA_KEYWORDS.get(code, [])
        cpt_keywords[code] = [k.lower() for k in kws + extras]
    return cpt_keywords

def parse_sol_file(fpath):
    with open(fpath, encoding="utf-8") as f:
        content = f.read()
    steps = []
    pattern = re.compile(r'## \[Step (\d+)\] (.+?)(?=\n## \[Step |\Z)', re.DOTALL)
    for m in pattern.finditer(content):
        step_num = int(m.group(1))
        body     = m.group(0)
        title    = m.group(2).split('\n')[0].strip()

        trigger_m = re.search(r'- \*\*Trigger\*\*:\s*(.+?)(?=\n- \*\*|\Z)', body, re.DOTALL)
        action_m  = re.search(r'- \*\*Action\*\*:\s*(.+?)(?=\n- \*\*|\Z)', body, re.DOTALL)

        trigger = trigger_m.group(1).strip() if trigger_m else ""
        action  = action_m.group(1).strip() if action_m else ""

        # CPT 코드 추출
        cpt_m   = re.search(r'\[([A-Za-z0-9가-힣ⅠⅡ\-]+)\]', action)
        cpt_code = cpt_m.group(1) if cpt_m else None

        steps.append({
            'num':      step_num,
            'title':    title,
            'trigger':  trigger,
            'action':   action,
            'cpt_code': cpt_code,
        })
    return steps

def check_fit(step, cpt_keywords):
    code = step['cpt_code']
    if not code or code not in cpt_keywords:
        return None  # 코드 없으면 검사 불가 (lint가 이미 잡음)

    keywords = cpt_keywords[code]
    if not keywords:
        return None  # 키워드 없으면 검사 불가

    # 검사할 텍스트: 타이틀 + trigger + action (소문자, LaTeX 포함)
    text = (step['title'] + ' ' + step['trigger'] + ' ' + step['action']).lower()

    # 키워드가 하나라도 매칭되면 OK
    for kw in keywords:
        if kw.lower() in text:
            return None

    return f"키워드 미매칭 (코드: {code}, 키워드: {', '.join(keywords[:5])})"

def main():
    cpt_keywords = load_cpt_data()
    md_files     = sorted(SOL_DIR.rglob("*.md"))
    print(f"검사 대상: {len(md_files)}개 파일")

    suspects = []

    for fpath in md_files:
        rel   = str(fpath.relative_to(SOL_DIR))
        steps = parse_sol_file(fpath)
        for step in steps:
            result = check_fit(step, cpt_keywords)
            if result:
                suspects.append({
                    'file':    rel,
                    'step':    step['num'],
                    'title':   step['title'],
                    'code':    step['cpt_code'],
                    'reason':  result,
                    'action':  step['action'][:80],
                })

    print(f"\n불일치 의심: {len(suspects)}건\n")

    # 코드별 집계
    from collections import Counter
    by_code = Counter(s['code'] for s in suspects)
    print("=== 의심 코드 빈도 TOP 20 ===")
    for code, cnt in by_code.most_common(20):
        print(f"  {code:<25} {cnt:4d}건")

    # 상세 출력 (처음 50건)
    print(f"\n=== 의심 케이스 (처음 50건) ===")
    for s in suspects[:50]:
        print(f"  [{s['file']}] Step{s['step']}")
        print(f"    타이틀: {s['title'][:60]}")
        print(f"    코드:   {s['code']}")
        print(f"    이유:   {s['reason']}")
        print()

    # CSV 저장
    out_csv = Path(__file__).parent / "cpt_fit_report.csv"
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['파일', 'Step', '타이틀', 'CPT코드', '이유', 'Action(앞80자)'])
        for s in suspects:
            w.writerow([s['file'], s['step'], s['title'], s['code'], s['reason'], s['action']])
    print(f"📄 CSV 저장: {out_csv}")
    print(f"총 {len(suspects)}건 / {len(md_files)}개 파일")

if __name__ == "__main__":
    main()
