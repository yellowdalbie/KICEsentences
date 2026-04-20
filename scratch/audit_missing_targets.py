import os
import unicodedata

sol_base = "/Users/home/vaults/projects/KICEsentences/Sol"
excluded_file = "/Users/home/vaults/projects/KICEsentences/a_type_excluded.txt"
target_na_file = "/Users/home/vaults/projects/KICEsentences/target_na_type_list.txt"

def normalize(s):
    return unicodedata.normalize('NFC', s)

# Load excluded A-type (2016)
excluded_a = set()
with open(excluded_file, "r", encoding="utf-8") as f:
    for line in f:
        if ".md" in line and "→" not in line:
            path = line.split()[0]
            excluded_a.add(normalize(path))

# Load target Na-type (2017-2018)
target_na = set()
with open(target_na_file, "r", encoding="utf-8") as f:
    for line in f:
        path = line.strip()
        if path:
            target_na.add(normalize(path))

years = ["2016", "2017", "2018"]

for year in years:
    print(f"\n--- Audit for {year} ---")
    sol_dir = os.path.join(sol_base, year)
    if not os.path.exists(sol_dir):
        continue
        
    # Get all potential Na/A files from reference (or just numbers 1-30)
    # Actually, let's use the logic: if it's Na/A type, it should be in target or excluded.
    
    existing_files = {normalize(f) for f in os.listdir(sol_dir)}
    
    # 2016 (A-type)
    if year == "2016":
        prefix = "2016.6모A", "2016.9모A", "2016수능A"
        for p in prefix:
            for i in range(1, 31):
                filename = f"{p}_{i:02d}.md"
                rel_path = f"2016/{filename}"
                norm_path = normalize(rel_path)
                norm_filename = normalize(filename)
                
                if norm_path in excluded_a:
                    if norm_filename in existing_files:
                        print(f"[EXISTING BUT EXCLUDED] {rel_path}")
                else:
                    if norm_filename not in existing_files:
                        print(f"[MISSING AND TARGET] {rel_path}")

    # 2017-2018 (Na-type)
    else:
        # Check against target_na
        for path in target_na:
            if path.startswith(year):
                filename = os.path.basename(path)
                if normalize(filename) not in existing_files:
                    print(f"[MISSING AND TARGET] {path}")
        
        # Check for files in Sol that are NOT in target_na (and not Ga-type)
        for f in existing_files:
            if "나" in f:
                rel_path = normalize(f"{year}/{f}")
                if rel_path not in target_na:
                    print(f"[EXISTING BUT NOT IN TARGET] {rel_path}")
