import os
import re
import unicodedata

source_dir = '/Users/home/vaults/projects/KICEsentences/gemini_queue/D1_단일스텝'
files = os.listdir(source_dir)
explanation_files = [f for f in files if f.endswith('_해설.md')]

analysis = []

for f in explanation_files:
    path = os.path.join(source_dir, f)
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
        
    title_match = re.search(r'## \[Step 1\] (.*)', content)
    action_match = re.search(r'- \*\*Action\*\*: (.*)', content)
    
    title = title_match.group(1).strip() if title_match else ""
    action = action_match.group(1).strip() if action_match else ""
    size = os.path.getsize(path)
    
    analysis.append({
        'filename': f,
        'title': title,
        'action': action,
        'size': size
    })

# Print top 50 smallest for quick review
analysis.sort(key=lambda x: x['size'])

print("--- Smallest Files Analysis ---")
for item in analysis[:50]:
    print(f"{item['size']:4} bytes | {item['filename']} | {item['title']} | {item['action']}")

print("\n--- Potential Trivial Candidates (Keywords) ---")
trivial_keywords = ["대입", "공식", "계산", "미분계수", "조합", "순열", "집합", "등차수열", "등비수열"]
for item in analysis:
    # Very small files are likely trivial
    if item['size'] < 800:
        print(f"CANDIDATE: {item['filename']} | {item['title']}")
