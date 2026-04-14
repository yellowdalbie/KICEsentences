import os
import re

sol_dir = 'Sol'
audit_results = []
achievement_codes = set() # To detect non-standard codes if needed

# Define patterns
latex_in_title_pattern = re.compile(r'^## \[Step \d+\].*?\$')
trigger_pattern = re.compile(r'- \*\*Trigger\*\*:\s*\[(.*?)\]')
action_pattern = re.compile(r'- \*\*Action\*\*:\s*\[(.*?)\]')
result_pattern = re.compile(r'- \*\*Result\*\*:')
explanation_header_pattern = re.compile(r'> \*\*📝 해설 \(Explanation\)\*\*')

forbidden_words = ["땀 흘려", "친절하게", "관문", "덩어리", "깎아나가며", "외톨이", "진짜로"]

def audit_file(filepath):
    violations = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
        
        # 1. Header integrity
        if not lines[0].startswith('#') or '해설' not in lines[0]:
            violations.append("Header missing or incorrect")
        
        # 2. Step Title & Block structure
        steps = []
        for i, line in enumerate(lines):
            if line.startswith('## [Step'):
                if latex_in_title_pattern.match(line):
                    violations.append(f"LaTeX in Step Title (Line {i+1})")
                
                # Check for subsequent structure
                structure_block = "\n".join(lines[i+1:i+10])
                if not trigger_pattern.search(structure_block):
                    violations.append(f"Missing or malformed Trigger after Step Title (Line {i+1})")
                else:
                    cat_match = trigger_pattern.search(structure_block)
                    if cat_match:
                        cat = cat_match.group(1)
                        if not (cat.endswith('조건') or cat == '최종 구하는 값'):
                            violations.append(f"Non-standard Trigger Category: [{cat}]")
                
                if not action_pattern.search(structure_block):
                    violations.append(f"Missing or malformed Action after Step Title (Line {i+1})")
                
                if not result_pattern.search(structure_block):
                    violations.append(f"Missing or malformed Result after Step Title (Line {i+1})")
                
                if not explanation_header_pattern.search(structure_block):
                    violations.append(f"Missing Explanation header after Step Title (Line {i+1})")

        # 3. Tone check
        for word in forbidden_words:
            if word in content:
                violations.append(f"Forbidden word used: {word}")

    return violations

total_checked = 0
violators = []

for root, dirs, files in os.walk(sol_dir):
    for file in files:
        if file.endswith('.md'):
            total_checked += 1
            filepath = os.path.join(root, file)
            v = audit_file(filepath)
            if v:
                violators.append((filepath, v))

print(f"Total checked: {total_checked}")
print(f"Total violators found: {len(violators)}")

# Output top 10 violators for sampling
for v_path, v_list in violators[:10]:
    print(f"File: {v_path}")
    for item in v_list:
        print(f" - {item}")
