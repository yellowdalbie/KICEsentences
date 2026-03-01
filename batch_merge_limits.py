import glob
import re
import os

files = glob.glob('Sol/**/*.md', recursive=True)
target_files = []

for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if '좌극한' in content or '우극한' in content:
        if '그래프' in content or 'CA1-LIM' in content or 'lim' in content:
            steps = len(re.findall(r'##\s*\[Step', content))
            if steps > 1:
                target_files.append(file)

print(f"Starting batch process on {len(target_files)} files...")

for file in target_files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract header: everything before the first "## [Step"
    header_match = re.search(r'^(.*?)(?=## \[Step)', content, re.DOTALL)
    header = header_match.group(1).strip() if header_match else ""
    
    # Extract all results to find the final result
    results = re.findall(r'- \*\*Result\*\*: (.*)', content)
    final_result = results[-1].strip() if results else ""
    
    # Extract explanations: all blocks between "> **📝 해설..." and the next step or EOF
    explanations = re.findall(r'> \*\*📝 해설 \(Explanation\)\*\*\n(.*?)(?=\n## \[Step|\Z)', content, re.DOTALL)
    
    # Merge explanations
    merged_exp_lines = []
    for exp in explanations:
        # Strip consecutive blank quote lines and ensure seamless joining
        lines = exp.strip().split('\n')
        for line in lines:
            if line.strip() == '>':
                # Avoid too many empty quote lines
                if not merged_exp_lines or merged_exp_lines[-1] != '>':
                    merged_exp_lines.append('>')
            else:
                merged_exp_lines.append(line)
        merged_exp_lines.append('>') # Add a blank quote line between step explanations
    
    # Remove the very last blank quote line if exists
    if merged_exp_lines and merged_exp_lines[-1] == '>':
        merged_exp_lines.pop()
        
    merged_exp = '\n'.join(merged_exp_lines)
    
    # Build the new content
    new_content = f"""{header}

## [Step 1] 함수의 그래프를 이용하여 좌극한과 우극한 구하기

- **Trigger**: [그래프를 이용한 극한값 판독] 함수의 그래프가 주어지고 좌극한과 혹은 우극한을 구하는 극한식 제시
- **Action**: [CPT-CA1-LIM-002] 주어진 $y=f(x)$ 의 그래프에서 $x$ 가 특정한 값으로 다가갈 때, 곡선이 향하는 목표점의 $y$ 좌표를 각각 판독하여 연산 수행
- **Result**: {final_result}

> **📝 해설 (Explanation)**
{merged_exp}
"""
    
    # Write back to file
    with open(file, 'w', encoding='utf-8') as f:
        f.write(new_content)

print("Batch processing complete!")
