import os
import re
import google.generativeai as genai
import time
from glob import glob

api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    # Try reading from a local file if not in env
    try:
        with open(os.path.expanduser('~/.gemini/api_key'), 'r') as f:
            api_key = f.read().strip()
    except Exception:
        pass

if not api_key:
    print("Could not find GEMINI_API_KEY")
    exit(1)

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-pro')

PROMPT = """You are a professional mathematics educator writing solutions for the Korean CSAT (수능).
The following explanation currently contains overly descriptive, emotional, colloquial, or non-mathematical metaphors (e.g., "덩어리", "비대한", "강제로", "뭉쳐진", "폭파", "외톨이", "도려내", "수확", "정복", "밀어 넣다", "우주", "가차 없이", "녀석", "안전하지만", "살아남은", "부품", "바구니", "해부", "치수", "명단", "신분", "땀 흘려" etc.).

Your task is to rewrite the explanation to be STRICTLY formal, objective, academic, and dry.
1. Remove all childish, conversational, or dramatic vocabulary completely.
2. Maintain all specific mathematical formulas and logical flows.
3. Use extremely precise mathematical terminology (e.g., '공통인수로 묶는다', '대입한다', '소거된다', '정리하면').
4. The output must start exactly with `> **📝 해설 (Explanation)**` and all explanation lines must begin with `> `. Retain the exact markdown formatting.
5. Provide ONLY the rewritten explanation text, do not include any other markdown formatting like ```markdown ... ``` around it.

Here is the explanation to rewrite:
{explanation}
"""

BAD_WORDS = ["덩어리", "비대", "뭉쳐진", "강제로", "폭파", "외톨이", "도려내", "수확", "정복", "밀어", 
             "데칼코마니", "거물급", "찰나", "바구니", "해부", "우리가 가진", "안겨진", "꿰찰", 
             "끌어모으", "떨어집니다", "조준", "찌꺼기", "치수", "부품", "혼동", "초딩", 
             "관문", "합격", "신분", "명단", "주인공", "다행히", "눈치", "땀 흘려", "친절", 
             "가볍게", "진짜로", "무서운", "통짜", "가차 없", "날려버리", "이 녀석", "안전하", 
             "살아남은", "쓱", "우주", "거대한", "사체", "과감히", "무조건", "완벽히 일치", "장착",
             "정체", "뼈대", "환골탈태", "침투", "기둥", "방대함", "은신", "지렛대", "사냥", "포획",
             "단숨에", "골조", "거슬러", "좇아"]

def rewrite_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Split content by steps
    steps = re.split(r'(?=## \[Step)', content)
    new_content = ""
    changed = False
    
    for step in steps:
        match = re.search(r'(> \*\*📝 해설 \(Explanation\)\*\*\n.*)', step, re.DOTALL)
        if match:
            old_exp = match.group(1)
            found_bad = [w for w in BAD_WORDS if w in step]  # Search in the whole step including Trigger/Action
            if found_bad:
                print(f"File: {filepath} | Found: {found_bad}")
                
                # Rewrite the whole explanation and action triggers if needed? No, let's just use the prompt 
                # to rewrite the Explanation, and we can also ask to fix the Trigger/Action in another script.
                # Actually, let's just pass the whole step to the LLM and ask it to rewrite the whole step.
                
                STEP_PROMPT = """You are a professional mathematics educator writing solutions for the Korean CSAT (수능).
The following markdown step contains overly descriptive, emotional, colloquial, or non-mathematical metaphors (e.g., "덩어리", "강제로", "우주", "부품", "밀어", "과감히" etc.).

Your task is to rewrite the ENTIRE step to be STRICTLY formal, objective, academic, and mathematically precise.
1. Remove all childish/dramatic vocabulary anywhere in the text (including Trigger, Action, Result, and Explanation).
2. Keep the exact markdown structure: 
## [Step X] Title
- **Trigger**: ...
- **Action**: ...
- **Result**: ...
> **📝 해설 (Explanation)**
> ...
3. Use extremely precise mathematical terminology.
4. Provide ONLY the rewritten step text, starting from `## [Step` down to the end of the explanation. Do not use ```markdown ... ``` wrapper.
5. In Action, keep the concept code `[CPT-XXX-YYY-000]` exactly as it is.

Here is the step to rewrite:
""" + step
                
                try:
                    response = model.generate_content(STEP_PROMPT)
                    new_step = response.text.strip()
                    if new_step.startswith("```markdown"):
                        new_step = new_step[11:]
                    if new_step.endswith("```"):
                        new_step = new_step[:-3]
                    new_step = new_step.strip()
                    
                    if new_step.startswith("## [Step"):
                        step = new_step + "\n\n"
                        changed = True
                    else:
                        print("Failed to parse response for", filepath)
                except Exception as e:
                    print(f"  - Failed API call: {e}")
                    time.sleep(5)
            else:
                pass
        
        new_content += step
        
    if changed:
        with open(filepath, 'w') as f:
            f.write(new_content)
        print(f"Saved {filepath}")

if __name__ == "__main__":
    files = glob("Sol/2018/*.md") + glob("Sol/2019/*.md")
    print(f"Checking {len(files)} files...")
    for f in files:
        rewrite_file(f)
