import os, re, shutil, unicodedata
years = ["2022", "2023"]
for year in years:
    sol_dir, ref_dir, excl_dir = f"Sol/{year}", f"MD_Ref/{year}", f"Sol_Excluded/{year}"
    if not os.path.exists(ref_dir): continue
    os.makedirs(excl_dir, exist_ok=True)
    os.makedirs(sol_dir, exist_ok=True)

    for f in sorted(os.listdir(ref_dir)):
        if not f.endswith(".md"): continue
        # Exclusion based on Selective subject naming
        # Usually filenames are: 2022수능_미적_23.md, 2022수능_공통_01.md, etc.
        if "미적" in f or "기하" in f:
            status = "EXCLUDE: Selective (Calc/Geometry)"
        else:
            status = "KEEP"
        
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
    print(f"Year {year} Done.")
