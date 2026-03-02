#!/usr/bin/env python3
"""audit_titles.py: Sol/ 디렉토리의 모든 Step 타이틀을 추출하고 위반 여부를 분류한다."""

import os
import re
import json

SOL_DIR = "/Users/home/vaults/projects/KICEsentences/Sol"

# 원칙 적용 제외 (허용 목록)
WHITELIST = {
    "함수의 그래프를 이용하여 좌극한과 우극한 구하기",
    "함수의 그래프를 이용하여 좌극한과 우극한 판독하기",
}

# 알려진 위반 패턴 목록
KNOWN_VIOLATIONS = {
    # 명시적 금지 패턴
    "최종 연산", "조건 분석", "합산",
    # 행위만 있는 타이틀
    "대입하여 계산", "대입으로 결정 후 계산",
    "곱의 미분법 적용", "기함수 적분 성질 적용",
    "이항분포 기댓값 공식 적용",
    # 대상/결과 없음
    "연립방정식 풀어 결정", "방정식 풀어 값 결정", "방정식 풀기",
    "덧셈정리로 분리", "덧셈정리로 계산",
    "여사건 공식으로 산출", "여사건 확률 계산",
    "조건부 확률 계산", "확률 계산 전확률 공식",
    "극한 조건으로 및 도함수 결정",
    "나머지 계수 결정 후 계산",
    "부정적분으로 결정",
    "항등식으로 계산",
    "사분면으로 부호 결정",
    "자연수 제곱합·합 공식으로 산출",
    "일반항에 대입하여 산출",
    "값 계산",
    "평균변화율 계산",
    "우극한·좌극한 계산",
    "적분으로 도출",
    "조건으로 결정",
    "시그마 식 변환",
    "공비 결정 및 일반항 적용",
    "적화 공식으로 변환",
    "여사건 조건으로 결정",
    "독립 조건으로 결정",
    "전체 분배 경우의 수",
    "다항함수 미분 후 산출",
    "가속도 조건으로 결정",
    "표준화 역산으로 결정",
    "표본평균 표준화로 산출",
    "남은 문자들에 중복조합 분배하여 연산하기",
    "근과 계수 관계로 간소화",
    "조건에서 공비 결정",
    "첫째항 결정 후 계산",
    "수열의 귀납적 정의를 이용하여 식 구하기",
    "수열의 합을 이용하여 식 구하기",
    "함수의 정의를 이용하여 식의 값 구하기",
    "점화식에 따라 항 순서대로 계산",
    "최댓값과 최솟값 파악",
    "합 계산",
    "곱의 미분법으로 도출",
    "확률 분해로 산출",
    "두 시그마 조건에서 산출",
    "삼각형 OCB 넓이 조건으로 결정 후 산출",
    "로그의 밑을 통일하여 방정식 변환",
    "이차방정식 풀고 진수 조건 확인",
    "극댓값 극솟값 계산 후 합산",
    "도출된 식에 값 대입하기",
    "삼각함수 값 대입으로 산출",
    "극값 좌표 차이로 산출",
    "도함수를 적분하여 결정",
    "삼각함수 성분으로 산출",
    "접선 기울기 계산",
    "수직인 직선의 절편",
    "연립방정식으로 결정",
    "극한식을 미분계수로 인식",
    "도함수에 대입하여 계산",
    "도함수에 대입하여 산출",
    "가지 색 모두 받는 학생이 있는 경우 계산",
    "같은 것이 있는 순열을 위한 요소 배열 연산",
    "각 인수에서 필요한 항 추출",
    "계수 합산",
    "항의 비 조건으로 공비 결정",
    "조건으로 첫째항 도출 및 계산",
    "인 경우 나열",
    "값에 따른 경우 분류",
    "속도 함수 분석",
    "교점 계산",
    "x절편 구하기",
    # 렌더링 소실 타이틀 (LaTeX 변수가 사라진 것)
    "을 코사인 부등식으로 변환",
    "두 시그마 조건에서 와 의 관계식 수립",
    "전체 일대일함수 수 및 가 조건 적용",
    "나 조건 만족 경우 계산 후 확률 적용",
    "등차수열 성질로 결정",
    "초기 조건으로 구한 에 대입",
    "내분점 좌표 조건으로 에 대한 방정식 수립",
    "가 의 배수인 모든 경우 열거",
    "부등식 풀어 조건을 만족하는 자연수 의 합 계산",
    "인 경우 계산 후 조건부 확률 적용",
    "의 성질을 이용한 식의 분리",
    "경우의 수를 이용하여 순서쌍의 개수 구하기",
}


def check_violation(title):
    """위반 유형 반환. 위반 없으면 None."""
    if title in WHITELIST:
        return None
    if '$' in title:
        return "LaTeX"
    if title in KNOWN_VIOLATIONS:
        return "Known"
    # 조사로 시작하는 잘린 타이틀
    if re.match(r'^[을를이가의은는에서와과]\s', title):
        return "Truncated"
    return None


results = []

for year in sorted(os.listdir(SOL_DIR)):
    year_dir = os.path.join(SOL_DIR, year)
    if not os.path.isdir(year_dir):
        continue
    for fname in sorted(os.listdir(year_dir)):
        if not fname.endswith('.md'):
            continue
        fpath = os.path.join(year_dir, fname)
        with open(fpath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for lineno, line in enumerate(lines, 1):
            m = re.match(r'^## \[Step \d+\]\s+(.+)$', line.rstrip())
            if m:
                title = m.group(1).strip()
                vtype = check_violation(title)
                results.append({
                    'file': fpath,
                    'line': lineno,
                    'title': title,
                    'violation': vtype
                })

violations = [r for r in results if r['violation']]
ok_list = [r for r in results if not r['violation']]

print(f"전체 Step 수: {len(results)}")
print(f"위반: {len(violations)}")
print(f"준수: {len(ok_list)}")
print()

# 파일별로 그룹화
by_file = {}
for v in violations:
    f = v['file']
    if f not in by_file:
        by_file[f] = []
    by_file[f].append(v)

print(f"위반 파일 수: {len(by_file)}")
print()
print("=== 위반 목록 (파일:라인 [유형] 타이틀) ===")
for fpath in sorted(by_file.keys()):
    for v in by_file[fpath]:
        rel = fpath.replace("/Users/home/vaults/projects/KICEsentences/", "")
        print(f"{rel}:{v['line']} [{v['violation']}] {v['title']}")

# JSON으로도 저장
with open('/Users/home/vaults/projects/KICEsentences/audit_violations.json', 'w', encoding='utf-8') as f:
    json.dump({'violations': violations, 'ok': ok_list}, f, ensure_ascii=False, indent=2)

print()
print("audit_violations.json 저장 완료")
