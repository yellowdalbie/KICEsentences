import os
import shutil

sol_dir = "Sol/2014"
excluded_dir = "Sol_Excluded/2014"
os.makedirs(excluded_dir, exist_ok=True)

# List of files to definitely exclude (Based on subject or previous Turn)
# B series subjects for 2014 (Ga-type): 
# Transcendentals, Geometry, Matrix, Transform, Legacy limits.
to_exclude = []

for filename in os.listdir(sol_dir):
    if not filename.endswith(".md"):
        continue
        
    path = os.path.join(sol_dir, filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Heuristics for exclusion
    is_excluded = False
    
    # Subject-based exclusion
    if "B_" in filename:
        # 12미적 (Transcendentals) or 12기하 (Geometry)
        if "[12미적" in content and "[12미적Ⅰ" not in content:
            is_excluded = True
        if "[12기하" in content:
            is_excluded = True
        if "행렬" in content or "일차변환" in content or "분수부등식" in content or "회전체의 부피" in content:
            is_excluded = True
        if "공간좌표" in content or "공간벡터" in content or "이면각" in content:
            is_excluded = True
        if "지수함수와 로그함수의 미분" in content or "삼각함수의 미분" in content:
            is_excluded = True
            
    # Legacy subjects in A-type (e.g., Matrix, Log integer parts)
    if "A_" in filename:
        if "행렬" in content or "지표와 가수" in content or "가수" in content:
            # Special check for A_30 (Log parts)
            if "30.md" in filename and ("정수 부분" in content or "소수 부분" in content):
                is_excluded = True
        if "무한등비급수" in content or "수열의 극한" in content:
            is_excluded = True

    if is_excluded:
        to_exclude.append(filename)

print(f"Identified {len(to_exclude)} files to exclude.")
for filename in sorted(to_exclude):
    print(f"Excluding: {filename}")
    # Move to excluded dir
    # shutil.move(os.path.join(sol_dir, filename), os.path.join(excluded_dir, filename))
