"""평가원 수학 시험지 PDF를 문항별 개별 PDF로 분할 (번호 위치 자동 탐지).

extract_2027_9mo.py는 시험마다 영역 좌표를 손으로 잡아야 했다. 이 스크립트는
PDF 텍스트 레이어에서 문항 번호("1.", "23." 등)의 위치를 찾아
  - 같은 단(左/右)의 다음 번호 직전까지를 한 문항으로,
  - 단의 마지막 문항은 본문 하단 한계(BODY_BOTTOM)까지로
잘라낸 뒤, extract_math_questions.trim_white_space_visual로 상하 여백을 트리밍한다.

사용법:
    venv/bin/python scripts/extract_exam_auto.py <시험지.pdf> <출력폴더> <파일명접두어> [본문쪽수=20]
예:
    venv/bin/python scripts/extract_exam_auto.py 2027수능.pdf scratch/2027_suneung_extracted 2027수능

- 수능 PDF처럼 홀수형/짝수형이 이어붙은 경우 앞쪽 [본문쪽수]만 사용한다(기본 20쪽).
- 1~8쪽: 공통 01~22 / 9~12쪽: 확23~30 / 13~16쪽: 미23~30 / 17~20쪽: 기23~30
"""
import os
import re
import sys

import fitz  # PyMuPDF
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_math_questions import trim_white_space_visual

# 단(column) 가로 범위 (pt, A4 842x1191 기준) — 가운데 세로줄은 x≈420
COLUMNS = {"L": (80, 418), "R": (424, 770)}
# 문항 번호 x0가 이 범위에 있으면 해당 단의 문항 시작으로 본다
NUM_X = {"L": (84, 94), "R": (432, 442)}
BODY_BOTTOM = 1045   # 본문 하단 한계 (쪽 번호 박스 위)
WHITE = 250          # 이 값 초과 픽셀은 흰색으로 간주

SECTIONS = [  # (시작쪽, 끝쪽, 접미어 접두)
    (1, 8, ""),
    (9, 12, "확"),
    (13, 16, "미"),
    (17, 20, "기"),
]


def section_prefix(page_no):
    for start, end, prefix in SECTIONS:
        if start <= page_no <= end:
            return prefix
    raise ValueError(f"구간 밖 쪽: {page_no}")


def find_numbers(page):
    """[(col, num, y0)] 반환."""
    found = []
    for x0, y0, x1, y1, w, *_ in page.get_text("words"):
        m = re.fullmatch(r"(\d{1,2})\.", w)
        if not m:
            continue
        for col, (lo, hi) in NUM_X.items():
            if lo <= x0 <= hi:
                found.append((col, int(m.group(1)), y0))
    return found


def first_line_top(page, col, num_y):
    """번호 줄의 실제 잉크 상단을 찾는다.

    번호 글자 위로 분수·극한·지수가 솟아 있을 수 있으므로(예: lim 분수, 분수 지수),
    번호 글자 중간 높이에서 위로 올라가며 단 전체 폭이 MIN_GAP_PT 이상 연속으로
    흰색인 구간(문항 사이 여백)을 찾고, 그 구간의 아래 끝에서 1pt 위를 반환한다.
    """
    MIN_GAP_PT = 4
    left, right = COLUMNS[col]
    zoom = 2
    clip = fitz.Rect(left, max(0, num_y - 80), right, num_y + 7)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
    gray = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
    w, h = gray.size
    px = gray.load()
    run = 0
    for yy in range(h - 1, -1, -1):
        if all(px[x, yy] > WHITE for x in range(w)):
            run += 1
            if run >= MIN_GAP_PT * zoom:
                return clip.y0 + (yy + run) / zoom - 1
        else:
            run = 0
    return clip.y0


def notice_top(page, col):
    """단 하단의 '* 확인 사항' 박스 상단 y (없으면 None)."""
    lo, hi = COLUMNS[col]
    words = page.get_text("words")
    for i, (x0, y0, *_rest) in enumerate(words):
        w = words[i][4]
        if w == "확인" and lo <= x0 <= hi and i + 1 < len(words) and words[i + 1][4] == "사항":
            return y0 - 12  # 박스 테두리는 글자보다 ~6pt 위
    return None


def extract(input_pdf, output_dir, base, body_pages=20):
    doc = fitz.open(input_pdf)
    os.makedirs(output_dir, exist_ok=True)
    saved = []

    for page_no in range(1, body_pages + 1):
        page = doc[page_no - 1]
        prefix = section_prefix(page_no)
        nums = find_numbers(page)
        for col in ("L", "R"):
            col_nums = sorted((y, n) for c, n, y in nums if c == col)
            tops = [first_line_top(page, col, y) for y, _ in col_nums]
            col_bottom = notice_top(page, col) or BODY_BOTTOM
            for i, (y, n) in enumerate(col_nums):
                top = tops[i]
                bottom = tops[i + 1] if i + 1 < len(col_nums) else col_bottom
                left, right = COLUMNS[col]
                rect = fitz.Rect(left, top, right, bottom)

                new_doc = fitz.open()
                new_page = new_doc.new_page(width=rect.width, height=rect.height)
                new_page.show_pdf_page(new_page.rect, doc, page_no - 1, clip=rect)
                trim_white_space_visual(new_page, padding=10)

                suffix = f"{prefix}{n}" if prefix else f"{n:02d}"
                name = f"{base}_{suffix}.pdf"
                new_doc.save(os.path.join(output_dir, name))
                new_doc.close()
                saved.append(name)
                print(f"저장됨: {name} (쪽 {page_no}, 단 {col}, y {top:.0f}~{bottom:.0f})")

    doc.close()
    expected = 22 + 8 * 3
    print(f"\n총 {len(saved)}개 추출 → {output_dir}"
          + ("" if len(saved) == expected else f"  ⚠ 기대값 {expected}개와 다름"))
    return saved


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    extract(sys.argv[1], sys.argv[2], sys.argv[3],
            int(sys.argv[4]) if len(sys.argv) > 4 else 20)
