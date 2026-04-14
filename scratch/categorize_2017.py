import os
import re
import shutil

sol_dir = "Sol/2017"
ref_dir = "MD_Ref/2017"
excluded_dir = "Sol_Excluded/2017"
os.makedirs(excluded_dir, exist_ok=True)
os.makedirs(sol_dir, exist_ok=True)

all_filenames = sorted(os.listdir(ref_dir))

def categorize(filename, content):
    content_full = content
    # Common Exclusions (though Matrix is rare now)
    if re.search(r"행렬|일차변환|\\left\(\s*\\begin\{array\}|\\begin\{pmatrix\}|\\det\(|역행렬", content_full):
        return "EXCLUDE: Matrix"
    if re.search(r"벡터|이면각|포물선|타원|쌍곡선|정사영|공간", content_full):
        return "EXCLUDE: Geometry/Vectors"
    
    # Ga-type specific differentiation/integration (always transcendental or non-core calc)
    if "가_" in filename:
        if re.search(r"미분|적분|함수의 극한|접선|연속", content_full):
            # If not explicitly polynomial and has transcendental themes
            if re.search(r"sin|cos|tan|ln|exp|e\^|\\log|초월함수", content_full, re.I):
                return "EXCLUDE: Calculus II (Transcendentals)"
            # Almost all differentiation in Ga-type from 2017 is Calculus II
            if not re.search(r"다항|삼차|사차", content_full):
                 return "EXCLUDE: Calculus II (Transcendentals)"

    return "KEEP"

keep_count = 0
exclude_count = 0

for f in all_filenames:
    if not f.endswith(".md"): continue
    ref_path = os.path.join(ref_dir, f)
    with open(ref_path, "r", encoding="utf-8") as file:
        ref_text = file.read()
    
    status = categorize(f, ref_text)
    
    if "EXCLUDE" in status:
        exclude_count += 1
        reason = status.split(": ")[1]
        caution = f"# {f} 해설\n\n> [!CAUTION]\n> 2028 수능 출제 범위 제외({reason})\n\n> 원본 문항 링크: [{f}](../../MD_Ref/2017/{f})\n"
        with open(os.path.join(excluded_dir, f), "w", encoding="utf-8") as out:
            out.write(caution)
        sol_p = os.path.join(sol_dir, f)
        if os.path.exists(sol_p): os.remove(sol_p)
    else:
        keep_count += 1
        sol_p = os.path.join(sol_dir, f)
        if not os.path.exists(sol_p):
            with open(sol_p, "w", encoding="utf-8") as out:
                out.write(f"# {f} 해설\n\n> 원본 문항 링크: [{f}](../../MD_Ref/2017/{f})\n")

print(f"Done 2017. KEEP: {keep_count}, EXCLUDE: {exclude_count}")
