import os
import json

base_dir = "/Users/home/vaults/projects/KICEsentences"
sol_base = os.path.join(base_dir, "Sol")
ref_base = os.path.join(base_dir, "MD_Ref")

years = ["2016", "2017", "2018"]
results = []

for year in years:
    sol_dir = os.path.join(sol_base, year)
    if not os.path.exists(sol_dir):
        continue
    
    for filename in os.listdir(sol_dir):
        if not filename.endswith(".md"):
            continue
        
        sol_path = os.path.join(sol_dir, filename)
        ref_path = os.path.join(ref_base, year, filename)
        
        size = os.path.getsize(sol_path)
        
        # Read first few lines of solution
        first_lines = ""
        try:
            with open(sol_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
                first_lines = "\n".join(lines[:10]) # Get first 10 lines
        except Exception as e:
            first_lines = f"Error reading file: {e}"

        results.append({
            "year": year,
            "filename": filename,
            "size": size,
            "has_ref": os.path.exists(ref_path),
            "snippet": first_lines
        })

print(json.dumps(results, ensure_ascii=False, indent=2))
