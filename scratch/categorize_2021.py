import os, re, shutil, unicodedata
year = "2021"
sol_dir, ref_dir, excl_dir = f"Sol/{year}", f"MD_Ref/{year}", f"Sol_Excluded/{year}"
os.makedirs(excl_dir, exist_ok=True)
os.makedirs(sol_dir, exist_ok=True)

def categorize(filename, content):
    c = content
    if re.search(r"벡터|이면각|포물선|타원|쌍곡선|정사영|공간", c): return "EXCLUDE: Geometry"
    if re.search(r"\\infty|수열의 극한|무한등비급수|급수의 합", c): return "EXCLUDE: Sequence/Series Limit"
    if "가_" in filename:
        if re.search(r"미분|적분|함수의 극한|접선|연속", c):
            if re.search(r"sin|cos|tan|ln|exp|e\^|\\log|초월함수", c, re.I): return "EXCLUDE: Calc II"
            if not re.search(r"다항|삼차|사차", c): return "EXCLUDE: Calc II"
    return "KEEP"

for f in sorted(os.listdir(ref_dir)):
    if not f.endswith(".md"): continue
    with open(os.path.join(ref_dir, f), "r", encoding="utf-8") as file:
        text = unicodedata.normalize('NFC', file.read())
    status = categorize(f, text)
    sol_p, excl_p = os.path.join(sol_dir, f), os.path.join(excl_dir, f)
    if "EXCLUDE" in status:
        reason = status.split(": ")[1]
        caution = f"# {f} 해설\n\n> [!CAUTION]\n> 2028 수능 출제 범위 제외({reason})\n\n> 원본 문항 링크: [{f}](../../MD_Ref/{year}/{f})\n"
        with open(excl_p, "w", encoding="utf-8") as out: out.write(caution)
        if os.path.exists(sol_p): os.remove(sol_p)
    else:
        if os.path.exists(excl_p): shutil.move(excl_p, sol_p)
        if not os.path.exists(sol_p):
            with open(sol_p, "w", encoding="utf-8") as out: out.write(f"# {f} 해설\n\n> 원본 문항 링크: [{f}](../../MD_Ref/{year}/{f})\n")
print("Year 2021 Done.")
