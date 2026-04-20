import os
import shutil
import unicodedata

sol_base = "/Users/home/vaults/projects/KICEsentences/Sol"
excluded_base = "/Users/home/vaults/projects/KICEsentences/Sol_Excluded"

years = ["2016", "2017", "2018"]

def standardize_content(filename, year):
    # Standard format for excluded files
    content = f"# {filename} 해설\n\n"
    content += "> [!CAUTION]\n"
    if year == "2016":
        content += "> 2016학년도 B형 문항 (교육과정 범위 및 작업 우선순위 제외)\n\n"
    else:
        content += f"> {year}학년도 가형 문항 (교육과정 범위 및 작업 우선순위 제외)\n\n"
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
            
        # Normalize filename for matching
        f_norm = unicodedata.normalize('NFC', f)
        
        # Identify Ga-type or B-type
        is_ga_b = False
        if year == "2016" and ("모B" in f_norm or "수능B" in f_norm):
            is_ga_b = True
        elif (year == "2017" or year == "2018") and ("모가" in f_norm or "수능가" in f_norm):
            is_ga_b = True
            
        if is_ga_b:
            src_path = os.path.join(sol_dir, f)
            dest_path = os.path.join(excluded_dir, f)
            
            # Create standardized content
            new_content = standardize_content(f, year)
            
            # Write to excluded directory
            with open(dest_path, "w", encoding="utf-8") as out_f:
                out_f.write(new_content)
                
            # Remove from original directory
            os.remove(src_path)
            print(f"Moved and standardized: {year}/{f}")
