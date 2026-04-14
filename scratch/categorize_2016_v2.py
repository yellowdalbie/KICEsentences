import os
import re
import shutil

sol_dir = "Sol/2016"
ref_dir = "MD_Ref/2016"
excluded_dir = "Sol_Excluded/2016"
os.makedirs(excluded_dir, exist_ok=True)
os.makedirs(sol_dir, exist_ok=True)

# Master list from MD_Ref
all_filenames = sorted(os.listdir(ref_dir))

def categorize(filename, content):
    content_full = content
    # Common Exclusions
    if re.search(r"행렬|일차변환|\\left\(\s*\\begin\{array\}|\\begin\{pmatrix\}|\\det\(|역행렬", content_full):
        return "EXCLUDE: Matrix/Transformation"
    if re.search(r"\\infty|수열의 극한|무한등비급수|급수의 합", content_full):
        return "EXCLUDE: Sequence/Series Limit"
    if re.search(r"지표|가수|정수\s*부분.*소수\s*부분", content_full):
        return "EXCLUDE: Log Legacy"
    if re.search(r"벡터|포물선|타원|쌍곡선|이면각|공간|기하", content_full):
        return "EXCLUDE: Geometry/Vectors"
    if re.search(r"회전체|부피", content_full):
        return "EXCLUDE: Legacy Calculus"
    
    # B-type specific
    if "B_" in filename:
        if re.search(r"미분|적분|함수의 극한|접선", content_full):
            if re.search(r"sin|cos|tan|ln|exp|e\^|\\log|초월함수", content_full, re.I):
                return "EXCLUDE: Calculus II (Transcendentals)"
            if not re.search(r"다항|삼차|사차|이차|일차", content_full):
                if not re.search(r"x\^\{?[234]\}?", content_full):
                    return "EXCLUDE: Calculus II (Non-polynomial)"
    
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
        caution = f"# {f} 해설\n\n> [!CAUTION]\n> 2028 수능 출제 범위 제외({reason})\n\n> 원본 문항 링크: [{f}](../../MD_Ref/2016/{f})\n"
        with open(os.path.join(excluded_dir, f), "w", encoding="utf-8") as out:
            out.write(caution)
        sol_p = os.path.join(sol_dir, f)
        if os.path.exists(sol_p): os.remove(sol_p)
    else:
        keep_count += 1
        # It's a KEEP. 
        # If it's already in Excluded (by mistake), move it back to Sol.
        excl_p = os.path.join(excluded_dir, f)
        sol_p = os.path.join(sol_dir, f)
        if os.path.exists(excl_p):
            if not os.path.exists(sol_p):
                shutil.move(excl_p, sol_p)
            else:
                # If Sol also exists, check if it's a caution block
                with open(sol_p, "r", encoding="utf-8") as check:
                    if "[!CAUTION]" in check.read():
                        shutil.move(excl_p, sol_p) # Overwrite with... wait, excl_p might also be caution.
        # Ensure it exists in Sol (create empty if missing?) 
        # Actually most should already exist in Sol if they were kept.
        if not os.path.exists(sol_p):
            # Create a basic template if missing
            with open(sol_p, "w", encoding="utf-8") as out:
                out.write(f"# {f} 해설\n\n> 원본 문항 링크: [{f}](../../MD_Ref/2016/{f})\n")

print(f"Done 2016 v2. KEEP: {keep_count}, EXCLUDE: {exclude_count}")
