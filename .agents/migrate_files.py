import os
import shutil
import glob
import re

source_dir = 'gemini_queue/D1_단일스텝'
base_sol_dir = 'Sol'

files = glob.glob(os.path.join(source_dir, '*_해설.md'))

moved_count = 0
for src_path in files:
    filename = os.path.basename(src_path)
    # Remove '_해설' from filename
    new_filename = filename.replace('_해설.md', '.md')
    
    # Extract year (first 4 digits)
    year_match = re.search(r'(\d{4})', new_filename)
    if not year_match:
        print(f"Skipping {filename}: Year not found")
        continue
    
    year = year_match.group(1)
    target_dir = os.path.join(base_sol_dir, year)
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
        
    dest_path = os.path.join(target_dir, new_filename)
    
    shutil.copy2(src_path, dest_path)
    moved_count += 1

print(f"Successfully copied {moved_count} explanations to {base_sol_dir}/")
