import os
import re
import shutil
import unicodedata

def categorize(filename, content):
    c = content
    # Exclude Geometry
    if re.search(r"벡터|이면각|포물선|타원| 쌍곡선|정사영|공간", c):
        return "EXCLUDE: Geometry/Vectors"
    # Exclude Matrix (just in case)
    if re.search(r"행렬|일차변환|\\begin\{array\}|\\begin\{pmatrix\}", c):
        return "EXCLUDE: Matrix"
    # Exclude Calc II (Transcendentals) - usually in Ga-type
    if "가_" in filename or "B_" in filename:
        # Transcendental triggers
        if re.search(r"sin|cos|tan|ln|exp|e\^|\\log|초월함수", c, re.I):
            if re.search(r"미분|적분|함수의 극한|접선|연속", c):
                return "EXCLUDE: Calculus II (Transcendentals)"
        # Non-polynomial Calc in Ga-type
        if re.search(r"미분|적분|함수의 극한|접선|연속", c):
            if not re.search(r"다항|삼차|사차|이차|일차", c):
                 if not re.search(r"x\^\{?[234]\}?", c):
                      return "EXCLUDE: Calculus II (Non-polynomial)"
    
    # Exclude Sequence Limits / Infinite Series (Legacy Core)
    if re.search(r"\\infty|수열의 극한|무한등비급수|급수의 합", c):
        return "EXCLUDE: Sequence/Series Limit"

    return "KEEP"

years = ["2017", "2018", "2019", "2020"]
for year in years:
    sol_dir = f"Sol/{year}"
    ref_dir = f"MD_Ref/{year}"
    excl_dir = f"Sol_Excluded/{year}"
    if not os.path.exists(ref_dir): continue
    os.makedirs(excl_dir, exist_ok=True)
    os.makedirs(sol_dir, exist_ok=True)

    for f in sorted(os.listdir(ref_dir)):
        if not f.endswith(".md"): continue
        with open(os.path.join(ref_dir, f), "r", encoding="utf-8") as file:
            text = file.read()
            text = unicodedata.normalize('NFC', text) # Ensure NFC comparison
        
        status = categorize(f, text)
        sol_p = os.path.join(sol_dir, f)
        excl_p = os.path.join(excl_dir, f)

        if "EXCLUDE" in status:
            reason = status.split(": ")[1]
            caution = f"# {f} 해설\n\n> [!CAUTION]\n> 2028 수능 출제 범위 제외({reason})\n\n> 원본 문항 링크: [{f}](../../MD_Ref/{year}/{f})\n"
            with open(excl_p, "w", encoding="utf-8") as out:
                out.write(caution)
            if os.path.exists(sol_p): os.remove(sol_p)
        else:
            # KEEP
            if os.path.exists(excl_p):
                if not os.path.exists(sol_p):
                    shutil.move(excl_p, sol_p)
            if not os.path.exists(sol_p):
                with open(sol_p, "w", encoding="utf-8") as out:
                    out.write(f"# {f} 해설\n\n> 원본 문항 링크: [{f}](../../MD_Ref/{year}/{f})\n")
    print(f"Year {year} Categorization Done.")

