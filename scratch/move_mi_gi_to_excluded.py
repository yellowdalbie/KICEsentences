import os
import shutil
import unicodedata

sol_base = "/Users/home/vaults/projects/KICEsentences/Sol"
excluded_base = "/Users/home/vaults/projects/KICEsentences/Sol_Excluded"

years = ["2022", "2023", "2024"]

def standardize_content(filename, year, problem_type):
    content = f"# {filename} 해설\n\n"
    content += "> [!CAUTION]\n"
    content += f"> {year}학년도 {problem_type} 선택과목 문항 (교육과정 범위 및 작업 우선순위 제외)\n\n"
    content += f"> 원본 문항 링크: [{filename}](../../MD_Ref/{year}/{filename})\n"
    return content

for year in years:
    sol_dir = os.path.join(sol_base, year)
    excluded_dir = os.path.join(excluded_base, year)
    
    if not os.path.exists(sol_dir):
        continue
        
    if not os.path.exists(excluded_dir):
        os.makedirs(excluded_dir)
        
    files = os.listdir(sol_dir)
    for f in files:
        if not f.endswith(".md"):
            continue
            
        f_norm = unicodedata.normalize('NFC', f)
        
        is_excluded = False
        problem_type = ""
        
        # Check for '미' (Calculus) or '기' (Geometry)
        # 2022.6모_미23.md, 2022.6모_기23.md
        if "_미" in f_norm:
            is_excluded = True
            problem_type = "미적분"
        elif "_기" in f_norm:
            is_excluded = True
            problem_type = "기하"
            
        if is_excluded:
            src_path = os.path.join(sol_dir, f)
            dest_path = os.path.join(excluded_dir, f)
            
            new_content = standardize_content(f, year, problem_type)
            
            with open(dest_path, "w", encoding="utf-8") as out_f:
                out_f.write(new_content)
                
            os.remove(src_path)
            print(f"Moved and standardized: {year}/{f}")
