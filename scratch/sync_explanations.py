import os
import re
import unicodedata

source_dir = '/Users/home/vaults/projects/KICEsentences/gemini_queue/B4_방법어없음'
target_base_dir = '/Users/home/vaults/projects/KICEsentences/Sol'

files_to_sync = [
    '2014수능A_30_해설.md', '2015수능A_20_해설.md', '2016.6모A_27_해설.md',
    '2016.9모A_29_해설.md', '2016수능A_17_해설.md', '2017.6모나_04_해설.md',
    '2017.9모나_08_해설.md', '2017.9모나_12_해설.md', '2017.9모나_29_해설.md',
    '2017수능나_08_해설.md', '2018.6모나_20_해설.md', '2018수능나_05_해설.md',
    '2028.예시_21_해설.md'
]

# Ensure we use the exact binary filenames from the directory
actual_filenames = os.listdir(source_dir)
mapped_files = []

for target in files_to_sync:
    norm_target = unicodedata.normalize('NFC', target)
    for actual in actual_filenames:
        if unicodedata.normalize('NFC', actual) == norm_target:
            mapped_files.append(actual)
            break

print(f"Mapped {len(mapped_files)} files out of {len(files_to_sync)}")

for filename in mapped_files:
    # YEAR extraction
    norm_name = unicodedata.normalize('NFC', filename)
    match = re.match(r'^(\d{4})', norm_name)
    if not match:
        print(f"Could not find year in {norm_name}")
        continue
    year = match.group(1)
    
    target_dir = os.path.join(target_base_dir, year)
    target_filename = norm_name.replace('_해설.md', '.md')
    target_path = os.path.join(target_dir, target_filename)
    
    source_path = os.path.join(source_dir, filename)
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Link adjustment
    # Source: ../../problems/YEAR/NAME.md
    # Target: ../../MD_Ref/YEAR/NAME.md (for < 2028)
    # Target: ../../MD_Ref/NAME.md (for 2028)
    
    if year == '2028':
        # Replace ../../problems/2028/FILENAME.md with ../../MD_Ref/FILENAME.md
        # The filename in the link might have normalization issues too, but we search for the pattern
        content = re.sub(r'\]\(\.\./\.\./problems/2028/(.*?)\)', r'](../../MD_Ref/\1)', content)
    else:
        # Replace ../../problems/ with ../../MD_Ref/
        content = content.replace('../../problems/', '../../MD_Ref/')
        
    # Final check on target directory
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Successfully synced: {norm_name} -> {target_path}")
