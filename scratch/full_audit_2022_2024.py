import os
import unicodedata

sol_base = "/Users/home/vaults/projects/KICEsentences/Sol"
ref_base = "/Users/home/vaults/projects/KICEsentences/MD_Ref"

# Category keywords for mismatch detection
CATEGORIES = {
    "CALCULUS": ["미분", "적분", "함수", "도함수", "연속", "극한", "접선", "극대", "극소", "변화율", "넓이"],
    "PROB_STAT": ["확률", "통계", "분포", "순열", "조합", "배반", "독립", "표본", "평균", "표준편차", "기댓값", "이항"],
    "SEQUENCE": ["수열", "등차", "등비", "급수", "시그마", "귀납"],
    "LOG_EXP": ["로그", "지수", "진수", "거듭제곱"],
    "GEOMETRY": ["삼각형", "사인", "코사인", "도형", "원", "벡터", "평면", "공간"]
}

def normalize(s):
    return unicodedata.normalize('NFC', s)

def get_major_categories(text):
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
                
                ref_cats = get_major_categories(ref_content)
                sol_cats = get_major_categories(sol_content)
                
                if ref_cats and sol_cats:
                    # Mismatch check
                    if not (ref_cats & sol_cats):
                        fatal_errors.append({
                            "file": f"{year}/{f}",
                            "ref_cats": list(ref_cats),
                            "sol_cats": list(sol_cats),
                            "reason": "Category Mismatch"
                        })
                
                # Placeholder check
                placeholders = ["상세 생략", "자료 결과 기반", "매칭 필요", "수치 매칭", "도합"]
                found_placeholders = [p for p in placeholders if p in sol_content]
                if found_placeholders:
                     if f"{year}/{f}" not in [e["file"] for e in fatal_errors]:
                         fatal_errors.append({
                             "file": f"{year}/{f}",
                             "reason": f"Placeholder text found: {found_placeholders}"
                         })
        except Exception as e:
            print(f"Error processing {year}/{f}: {e}")

print(f"Total Fatal/Suspicious Errors found: {len(fatal_errors)}")
for error in fatal_errors:
    print(f"File: {error['file']}")
    print(f"  Reason: {error['reason']}")
    if 'ref_cats' in error:
        print(f"  Ref Cats: {error['ref_cats']} | Sol Cats: {error['sol_cats']}")
