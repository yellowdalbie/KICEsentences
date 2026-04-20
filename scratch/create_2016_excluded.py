import os

excluded_base = "/Users/home/vaults/projects/KICEsentences/Sol_Excluded/2016"

files = [
    ("2016.9모A_24.md", "행렬"),
    ("2016.9모A_30.md", "지표와 가수"),
    ("2016수능A_24.md", "행렬"),
    ("2016수능A_30.md", "지표와 가수")
]

def standardize_content(filename, problem_type):
    content = f"# {filename} 해설\n\n"
    content += "> [!CAUTION]\n"
    content += f"> 2016학년도 A형 문항 ({problem_type} - 구 교육과정 범위 및 작업 우선순위 제외)\n\n"
    content += f"> 원본 문항 링크: [{filename}](../../MD_Ref/2016/{filename})\n"
    return content

if not os.path.exists(excluded_base):
    os.makedirs(excluded_base)

for f, p_type in files:
    path = os.path.join(excluded_base, f)
    with open(path, "w", encoding="utf-8") as out_f:
        out_f.write(standardize_content(f, p_type))
    print(f"Created excluded file: 2016/{f}")
