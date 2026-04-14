import os
import shutil
import re

sol_dir = "Sol/2014"
excluded_dir = "Sol_Excluded/2014"
os.makedirs(excluded_dir, exist_ok=True)

# Move everything back from Sol_Excluded to Sol temporarily to re-evaluate
for filename in os.listdir(excluded_dir):
    if filename.endswith(".md"):
        shutil.move(os.path.join(excluded_dir, filename), os.path.join(sol_dir, filename))

def get_exclusion_reason(filename, content):
    # Rule 1: Always exclude legacy curriculum
    if "행렬" in content:
        return "2028 수능 출제 범위 제외(행렬)"
    if "일차변환" in content:
        return "2028 수능 출제 범위 제외(일차변환)"
    if "분수부등식" in content or "분수방정식" in content:
        return "2028 수능 출제 범위 제외(분수부등식/방정식)"
    if "무리부등식" in content or "무리방정식" in content:
        return "2028 수능 출제 범위 제외(무리부등식/방정식)"
    if "지표" in content and "가수" in content:
        return "2028 수능 출제 범위 제외(로그의 정수/소수 부분)"
    if "정수 부분" in content and "소수 부분" in content and "로그" in content:
        return "2028 수능 출제 범위 제외(로그의 정수/소수 부분)"
    if "회전체" in content and "부피" in content:
        return "2028 수능 출제 범위 제외(회전체의 부피)"
    if "계차수열" in content:
        return "2028 수능 출제 범위 제외(계차수열)"
    if "무한등비급수" in content and ("도형" in content or "넓이" in content):
        return "2028 수능 출제 범위 제외(급수 활용)"
    if "수열의 극한" in content:
        return "2028 수능 출제 범위 제외(수열의 극한)"
    if "급수" in content and "B_" in filename and "12대수" not in content:
        # Most series in B-type are excluded (unless they are geometric series in Algebra? No, wait)
        # Actually follow user's instruction: Transcendentals and Geometry
        pass

    # Rule 2: Exclude 미적분II (Transcendentals) and 기하 (Geometry)
    # Transcendental keywords: sin, cos, tan, ln, exp, log derivatives/integrals
    if re.search(r"sin|cos|tan|ln|exp|로그함수의 미분|지수함수의 미분|초월함수", content, re.I):
        return "2028 수능 출제 범위 제외(미적분II/기하)"
        
    # Geometry keywords
    if re.search(r"벡터|포물선|타원|쌍곡선|내적|정사영|이면각|공간|기하", content):
        if "직선" in content and "공간" not in content and "이면각" not in content:
            # Planar geometry is sometimes in Common Math
            pass
        else:
            return "2028 수능 출제 범위 제외(미적분II/기하)"
            
    # B-type specific: Most derivatives/integrals in B-type are Calculus II
    if "B_" in filename:
        if "미분" in content or "적분" in content:
            # Check if it's polynomial or transcendental
            if re.search(r"sin|cos|tan|ln|exp|e\^|log", content, re.I):
                return "2028 수능 출제 범위 제외(미적분II/기하)"
            if "[12미적-" in content or "[12미적Ⅱ" in content:
                return "2028 수능 출제 범위 제외(미적분II/기하)"

    return None

files = os.listdir(sol_dir)
for filename in files:
    if not filename.endswith(".md"):
        continue
        
    path = os.path.join(sol_dir, filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    reason = get_exclusion_reason(filename, content)
    
    if reason:
        print(f"Excluding {filename}: {reason}")
        new_content = f"""# {filename} 해설

> [!CAUTION]
> {reason}

> 원본 문항 링크: [{filename}](../../MD_Ref/2014/{filename})
"""
        with open(os.path.join(excluded_dir, filename), "w", encoding="utf-8") as f:
            f.write(new_content)
        os.remove(path)
    else:
        # Standardize remaining files
        print(f"Standardizing {filename}")
        new_content = content.replace("[12미적-", "[12미적Ⅰ-").replace("[12미적0", "[12미적Ⅰ-0")
        new_content = re.sub(r"\[12미적Ⅰ-(\d+)-(\d+)\]", r"[12미적Ⅰ-\1-\2]", new_content)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

print("Processing complete.")
