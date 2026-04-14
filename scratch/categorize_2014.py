import os
import re
import shutil

sol_dir = "Sol/2014"
ref_dir = "MD_Ref/2014"
excluded_dir = "Sol_Excluded/2014"
os.makedirs(excluded_dir, exist_ok=True)

# List of files in Sol/2014 and Sol_Excluded/2014 to consider
all_files = set(os.listdir(sol_dir)) | set(os.listdir(excluded_dir))

def get_status(filename, content):
    # Exclusion triggers
    if re.search(r"행렬|일차변환|A=\\(begin|left)|B=\\(begin|left)", content):
        return "EXCLUDE: Matrix/Transformation"
    if re.search(r"\\infty|수열의 극한|무한등비급수|급수의 합", content):
        return "EXCLUDE: Sequence/Series Limit (Legacy/Elective)"
    if re.search(r"지표|가수|정수\s*부분.*소수\s*부분", content):
        return "EXCLUDE: Log Legacy (Integer/Fraction parts)"
    if re.search(r"벡터|포물선|타원|쌍곡선|이면각|공간|기하", content):
        return "EXCLUDE: Geometry/Vectors"
    if re.search(r"회전체|부피", content):
        return "EXCLUDE: Legacy Calculus (Volume of revolution)"
    
    # Differentiation/Integration in B-type is mostly Calc II
    if "B_" in filename:
        # If it contains trig or log/exp in the context of calculus
        if re.search(r"sin|cos|tan|초월함수|ln|exp|e\^|\\log", content, re.I):
            if re.search(r"미분|적분|함수의 극한|접선", content):
                return "EXCLUDE: Calculus II (Transcendentals)"
        # If it's a diff/int problem and NOT explicitly polynomial
        if re.search(r"미분|적분|함수의 극한|접선", content):
            if not re.search(r"다항함수|삼차함수|사차함수|이차함수|일차함수", content):
                return "EXCLUDE: Calculus II (Transcendentals or unknown non-polynomial)"

    return "KEEP"

keep_files = []
exclude_files = []

for f in sorted(list(all_files)):
    if not f.endswith(".md"): continue
    
    ref_path = os.path.join(ref_dir, f)
    if not os.path.exists(ref_path): continue
    
    with open(ref_path, "r", encoding="utf-8") as file:
        ref_content = file.read()
    
    status = get_status(f, ref_content)
    
    if "EXCLUDE" in status:
        exclude_files.append(f)
        # Move to Excluded and write caution
        reason = status.split(": ")[1] if ": " in status else "2028 수능 출제 범위 제외"
        caution_content = f"# {f} 해설\n\n> [!CAUTION]\n> 2028 수능 출제 범위 제외({reason})\n\n> 원본 문항 링크: [{f}](../../MD_Ref/2014/{f})\n"
        
        target_path = os.path.join(excluded_dir, f)
        with open(target_path, "w", encoding="utf-8") as file:
            file.write(caution_content)
        
        # Remove from Sol if exists
        sol_f_path = os.path.join(sol_dir, f)
        if os.path.exists(sol_f_path):
            os.remove(sol_f_path)
    else:
        keep_files.append(f)
        # Ensure it is in Sol/2014 (move from Excluded if needed)
        excl_f_path = os.path.join(excluded_dir, f)
        sol_f_path = os.path.join(sol_dir, f)
        if os.path.exists(excl_f_path) and not os.path.exists(sol_f_path):
            shutil.move(excl_f_path, sol_f_path)
            print(f"[RECOVERED] {f}")

print(f"Done. KEEP: {len(keep_files)}, EXCLUDE: {len(exclude_files)}")
