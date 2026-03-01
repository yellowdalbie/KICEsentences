import os
import re
import glob

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    
    last_text_idx = -1
    for i in range(len(lines)-1, -1, -1):
        if lines[i].strip():
            last_text_idx = i
            break
            
    if last_text_idx == -1: return

    modified = False
    new_lines = list(lines)
    
    last_line = new_lines[last_text_idx]
    # 찾기: '정답은' 부분. (옵션으로 띄어쓰기 허용), **값** 또는 단어, '입니다.'
    ans_match = re.search(r'(정답은|최댓값은|최솟값은|공차는)\s+(.*?)\s*(?:입니다|이므로|이며|이 기|이 된)\.*$', last_line)
    
    if ans_match:
        ans_val = ans_match.group(2).strip()
        expected_last_line = f"> 따라서 정답은 **{ans_val}**입니다."
        
        prefix = last_line[:ans_match.start()].strip()
        if prefix.startswith('>'):
            prefix = prefix[1:].strip()
            
        if prefix and prefix not in ['따라서', '그러므로', '정답은']:
            # 꼬리말 치환
            prefix = re.sub(r'(이며|이므로|이므로,|며|,)\s*$', '입니다.', prefix)
            # 머리말 치환
            if prefix.startswith('따라서'):
                prefix = '그러므로 ' + prefix[3:].strip()
            
            new_lines[last_text_idx] = f"> {prefix}"
            new_lines.insert(last_text_idx + 1, expected_last_line)
            last_text_idx += 1
            modified = True
        else:
            if new_lines[last_text_idx].strip() != expected_last_line:
                new_lines[last_text_idx] = expected_last_line
                modified = True
    else:
        print(f"[WARN] No answer found in last line of {filepath} : {last_line}")
        
    for i in range(len(new_lines)):
        if i == last_text_idx:
            # 마지막 줄은 '따라서' 허용
            continue
            
        if '따라서' in new_lines[i]:
            new_lines[i] = new_lines[i].replace('따라서', '그러므로')
            modified = True
            
        if new_lines[i].startswith('## [Step'):
            if '$' in new_lines[i] or '\\' in new_lines[i]:
                # 3. 적정 추상화 수준 (수식 배제) 위반 의심
                pass # print(f"[WARN] {filepath} Step title abstraction warning: {new_lines[i].strip()}")

    if modified:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))

def main():
    files = glob.glob('Sol/**/*.md', recursive=True)
    count = 0
    for f in files:
        if os.path.isfile(f):
            process_file(f)
            count += 1
    print(f"Processed {count} solution files.")

if __name__ == '__main__':
    main()
