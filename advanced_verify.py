import json
import glob
import re
import os

def load_concept_db():
    try:
        with open('concepts.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(item['id'] for item in data if 'id' in item)
    except Exception as e:
        print(f"Error loading concepts.json: {e}")
        return set()

def verify_file(filepath, valid_codes):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    issues = []
    
    for i in range(len(lines) - 1):
        if lines[i].strip() == '>' and lines[i+1].strip() == '>':
             issues.append(f"Rule 6 (포맷팅 - 빈 인용구 연속): Line {i+1}")
             
    for i, line in enumerate(lines):
        if line.startswith('## [Step'):
            step_text = line.split(']', 1)[-1] if ']' in line else line
            if '$' in step_text or '\\' in step_text or bool(re.search(r'\d+', step_text)):
                issues.append(f"Rule 3 (추상화 위반 - 수식/숫자 배제): Line {i+1} : {line.strip()}")

        if '- **Action**:' in line:
            matches = re.findall(r'\[([A-Z0-9\-]+)\]', line)
            matches = [m for m in matches if m.startswith('CPT-')]
            if not matches:
                issues.append(f"Rule 4 (개념 코드 누락): Line {i+1} : No CPT code found")
            else:
                for match in matches:
                    if match not in valid_codes:
                        issues.append(f"Rule 4 (개념 코드 오류): Line {i+1} : Invalid code '{match}'")

    if issues:
        return issues
    return None

def main():
    valid_codes = load_concept_db()
    if not valid_codes: return
        
    files = glob.glob('Sol/**/*.md', recursive=True)
    
    issues_by_file = {}
    for f in files:
        if os.path.isfile(f):
            res = verify_file(f, valid_codes)
            if res:
                issues_by_file[f] = res
                
    count = 0
    for f, issues in issues_by_file.items():
        print(f"\n[{f}]")
        for iss in issues:
            print(f"  - {iss}")
        count += 1
        if count >= 30: 
            break

if __name__ == '__main__':
    main()
