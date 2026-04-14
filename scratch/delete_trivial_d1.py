import os
import re
import unicodedata

source_dir = '/Users/home/vaults/projects/KICEsentences/gemini_queue/D1_단일스텝'
files = os.listdir(source_dir)
explanation_files = [f for f in files if f.endswith('_해설.md')]

to_delete = []

# Specific confirmed list from plan examples
targets = [
    '2014.6모A_23', '2016.9모A_23', '2016.6모A_22', '2018.6모나_22',
    '2020.6모나_22', '2019.9모나_22', '2017.9모나_22', '2017.6모나_22',
    '2018.9모나_22', '2019.6모나_22', '2015.6모A_15', '2021.9모나_24',
    '2022.6모_16', '2014.6모A_22', '2014수능A_22', '2016.6모A_23',
    '2024수능_16', '2021.6모나_22', '2015.6모A_23', '2015.9모A_22',
    '2015수능A_22', '2017.9모나_22', '2017.9모나_24'
]

# Normalize targets
norm_targets = [unicodedata.normalize('NFC', t) for t in targets]

for f in explanation_files:
    path = os.path.join(source_dir, f)
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
        
    title_match = re.search(r'## \[Step 1\] (.*)', content)
    action_match = re.search(r'- \*\*Action\*\*: (.*)', content)
    
    title = title_match.group(1).strip() if title_match else ""
    action = action_match.group(1).strip() if action_match else ""
    
    base_name = f.replace('_해설.md', '')
    norm_base = unicodedata.normalize('NFC', base_name)
    
    # HEURISTICS for triviality
    is_trivial = False
    
    # 1. Manually picked targets
    if norm_base in norm_targets:
        is_trivial = True
    
    # 2. Heuristic: Simple Combinations/Permutations (definition based)
    if ("순열" in title or "조합" in title) and "정의" in title and "계산" in action:
        is_trivial = True
        
    # 3. Heuristic: Simple Calculus (Plug and play)
    if "미분계수 구하기" in title and "대입" in action and "함수" in action:
        # Check if it's longer/complex
        if len(content) < 1200:
            is_trivial = True
            
    # 4. Heuristic: Simple Limit (Direct substitution)
    if "극한값" in title and "대입" in action and "부정형이 아닌" in action:
        is_trivial = True

    if is_trivial:
        to_delete.append(base_name)

# Dedup and perform deletion
to_delete = sorted(list(set(to_delete)))

print(f"Planning to delete {len(to_delete)} problem sets...")

for base in to_delete:
    # Find exact matching files in directory (to handle normalization)
    norm_base = unicodedata.normalize('NFC', base)
    for f in os.listdir(source_dir):
        if unicodedata.normalize('NFC', f).startswith(norm_base):
            file_path = os.path.join(source_dir, f)
            os.remove(file_path)
            print(f"Deleted: {f}")

print("Deletion complete.")
