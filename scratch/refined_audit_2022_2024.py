import os
import unicodedata

sol_base = "/Users/home/vaults/projects/KICEsentences/Sol"
ref_base = "/Users/home/vaults/projects/KICEsentences/MD_Ref"

CATEGORIES = {
    "CALCULUS": ["미분", "적분", "도함수", "연속", "극한", "접선", "극대", "극소", "변화율", "함수"],
    "PROB_STAT": ["확률", "통계", "분포", "순열", "조합", "배반", "독립", "표본", "평균", "표준편차", "기댓값", "이항", "순서쌍", "개수"],
    "SEQUENCE": ["수열", "등차", "등비", "급수", "시그마", "귀납"],
    "LOG_EXP": ["로그", "지수", "진수", "거듭제곱"],
    "GEOMETRY": ["삼각형", "사인", "코사인", "탄젠트", "도형", "원", "벡터", "평면", "공간", "외심", "내심"]
}

def normalize(s):
    return unicodedata.normalize('NFC', s)

def get_major_categories(text, is_ref=False):
    # Remove footer/verification info for Ref files
    if is_ref:
        text = text.split("* 확인 사항")[0]
        text = text.split("이어서,")[0]
        
    found = set()
    text_norm = normalize(text)
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in text_norm:
                found.add(cat)
                break
    return found

years = ["2022", "2023", "2024"]
fatal_errors = []

for year in years:
    sol_dir = os.path.join(sol_base, year)
    if not os.path.exists(sol_dir):
        continue
        
    for f in os.listdir(sol_dir):
        if not f.endswith(".md"):
            continue
            
        sol_path = os.path.join(sol_dir, f)
        ref_path = os.path.join(ref_base, year, f)
        
        if not os.path.exists(ref_path):
            continue
            
        try:
            with open(sol_path, "r", encoding="utf-8") as s_f, open(ref_path, "r", encoding="utf-8") as r_f:
                sol_content = s_f.read()
                ref_content = r_f.read()
                
                ref_cats = get_major_categories(ref_content, is_ref=True)
                sol_cats = get_major_categories(sol_content)
                
                if ref_cats and sol_cats:
                    # Specific critical mismatches:
                    # Prob/Stat vs Calculus
                    if ("PROB_STAT" in ref_cats and "CALCULUS" in sol_cats and "PROB_STAT" not in sol_cats):
                        fatal_errors.append({"file": f"{year}/{f}", "reason": "Prob/Stat problem has Calculus solution"})
                    if ("CALCULUS" in ref_cats and "PROB_STAT" in sol_cats and "CALCULUS" not in sol_cats):
                        fatal_errors.append({"file": f"{year}/{f}", "reason": "Calculus problem has Prob/Stat solution"})
                    # Sequence vs others (less critical but still suspicious)
                    if ("SEQUENCE" in ref_cats and not (sol_cats & {"SEQUENCE", "CALCULUS"})):
                         fatal_errors.append({"file": f"{year}/{f}", "reason": "Sequence problem has unrelated solution"})
                         
                # Low quality placeholders
                placeholders = ["상세 생략", "자료 결과 기반", "매칭 필요", "수치 매칭"]
                for p in placeholders:
                    if p in sol_content:
                        fatal_errors.append({"file": f"{year}/{f}", "reason": f"Placeholder: {p}"})
                        break
        except Exception as e:
            pass

print(f"Total Serious Errors found: {len(fatal_errors)}")
for error in fatal_errors:
    print(f"File: {error['file']} | Reason: {error['reason']}")
