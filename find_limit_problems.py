import glob
import re

files = glob.glob('Sol/**/*.md', recursive=True)
target_files = []

for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check if it's a limit problem from a graph
    if '좌극한' in content or '우극한' in content:
        if '그래프' in content or 'CA1-LIM' in content or 'lim' in content:
            # Count the number of steps based on headers like ## [Step
            steps = len(re.findall(r'##\s*\[Step', content))
            
            # Check if it contains the exact preferred title
            preferred = '함수의 그래프를 이용하여 좌극한과 우극한 구하기' in content
            
            if steps > 1:
                target_files.append((file, steps, preferred))

print(f"Found {len(target_files)} multi-step graph limit problems:")
for file, steps, pref in sorted(target_files):
    print(f"- {file} ({steps} steps) - Has preferred title: {pref}")
