import os
import re
import shutil

sol_dir = "Sol/2014"
ref_dir = "MD_Ref/2014"
excluded_dir = "Sol_Excluded/2014"
os.makedirs(excluded_dir, exist_ok=True)

# List all problems
all_filenames = set(os.listdir(sol_dir)) | set(os.listdir(excluded_dir))

def categorize(filename, content):
    content_full = content
    # Common Exclusions
    if re.search(r"행렬|일차변환|A=\\(begin|left)|B=\\(begin|left)", content_full):
        return "EXCLUDE: Matrix/Transformation"
    if re.search(r"\\infty|수열의 극한|무한등비급수|급수의 합", content_full):
        return "EXCLUDE: Sequence/Series Limit"
    if re.search(r"지표|가수|정수\s*부분.*소수\s*부분", content_full):
        return "EXCLUDE: Log Legacy"
    if re.search(r"벡터|포물선|타원|쌍곡선|이면각|공간|기하", content_full):
        return "EXCLUDE: Geometry/Vectors"
    
    # B-type specific differentiation/integration
    if "B_" in filename:
        if re.search(r"미분|적분|함수의 극한|접선", content_full):
            # If specifically transcendental keywords exist
            if re.search(r"sin|cos|tan|ln|exp|e\^|\\log|초월함수", content_full, re.I):
                return "EXCLUDE: Calculus II (Transcendentals)"
            # If it doesn't mention polynomial terms, likely it is Calc II in B-type
            if not re.search(r"다항|삼차|사차|이차|일차", content_full):
                # But check for basic polynomial patterns like x^3, x^2
                if not re.search(r"x\^\{?[234]\}?", content_full):
                    return "EXCLUDE: Calculus II (Non-polynomial)"
    
    return "KEEP"

for f in sorted(list(all_filenames)):
    if not f.endswith(".md"): continue
    ref_path = os.path.join(ref_dir, f)
    if not os.path.exists(ref_path): continue
    
    with open(ref_path, "r", encoding="utf-8") as file:
        ref_text = file.read()
    
    status = categorize(f, ref_text)
    
    if "EXCLUDE" in status:
        reason = status.split(": ")[1]
        caution = f"# {f} 해설\n\n> [!CAUTION]\n> 2028 수능 출제 범위 제외({reason})\n\n> 원본 문항 링크: [{f}](../../MD_Ref/2014/{f})\n"
        # Write to Excluded
        with open(os.path.join(excluded_dir, f), "w", encoding="utf-8") as out:
            out.write(caution)
        # Delete from Sol if exists
        sol_p = os.path.join(sol_dir, f)
        if os.path.exists(sol_p): os.remove(sol_p)
    else:
        # It's a KEEP. 
        # Move from Excluded to Sol if it was there
        excl_p = os.path.join(excluded_dir, f)
        sol_p = os.path.join(sol_dir, f)
        if os.path.exists(excl_p):
            # If Sol doesn't exist or is a caution block, we need to RESTORE.
            # For now, just move it and print which ones need restoration.
            if os.path.exists(sol_p):
                with open(sol_p, "r", encoding="utf-8") as check:
                    if "[!CAUTION]" in check.read():
                        shutil.move(excl_p, sol_p) # Overwrite with... wait, excl_p is also a caution block if it was excluded.
                        print(f"NEED_RESTORE: {f}")
            else:
                shutil.move(excl_p, sol_p)
                print(f"NEED_RESTORE: {f}")

