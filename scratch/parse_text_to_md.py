import os
import re

text_file = "scratch/raw_questions.txt"
output_dir = "MD_Ref/2027"

os.makedirs(output_dir, exist_ok=True)

with open(text_file, "r", encoding="utf-8") as f:
    content = f.read()

# Remove thumbnail markers
content = content.replace("# 썸네일 확인 필수", "")

# Matches optional subject line, then "num." at the start of a line
pattern = re.compile(r'(?:^(기하|미적|확통)\n)?^(\d+)\.(?=\s|[^\s])', re.MULTILINE)
matches = list(pattern.finditer(content))

current_subject = "공통"
count = 0

for i, match in enumerate(matches):
    subj_group = match.group(1)
    num_str = match.group(2)
    
    if subj_group:
        current_subject = subj_group
    elif int(num_str) <= 22:
        current_subject = "공통"
        
    start_idx = match.start()
    end_idx = matches[i+1].start() if i+1 < len(matches) else len(content)
    
    # Extract raw chunk
    q_content = content[start_idx:end_idx].strip()
    
    # Remove the '기하\n', '미적\n' prefix if matched so it doesn't appear in output
    if subj_group:
        q_content = q_content[len(subj_group):].strip()
        
    num_padded = num_str.zfill(2)
    
    if current_subject == "공통":
        q_id = f"{num_padded}"
        subj_name = "공통"
        num_meta = num_padded
    else:
        prefix = current_subject[0]
        q_id = f"{prefix}{num_padded}"
        subj_name = current_subject
        num_meta = num_padded
        
    filename = f"2027.6모_{q_id}.md"
    pdf_filename = f"2027.6모_{q_id}.pdf"
    
    md_text = f"""---
학년도: 2027
시기: 6모
유형: {subj_name}
번호: {num_meta}
---
![[{pdf_filename}]]

{q_content}


[[2027.6모_{q_id}분석]]
"""
    
    with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as out_f:
        out_f.write(md_text)
    count += 1

print(f"Extraction complete! {count} files generated.")
