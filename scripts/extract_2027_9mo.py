"""2027.9모 시험지 PDF를 문항별 개별 PDF로 분할.

알고리즘(영역 클리핑 + 픽셀 기반 여백 트리밍)은 extract_math_questions.py를 재사용하고,
좌표/페이지 배치만 2027.9모 레이아웃에 맞게 정의한다.
6모와 지면 구조는 같으나 7페이지 우측(20번)이 더 길어 해당 영역만 하단을 확장했다.
"""
import os
import sys

import fitz  # PyMuPDF

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_math_questions import trim_white_space_visual

# 영역 좌표 (6모와 동일, 단 area 9는 하단을 880 → 1010으로 확장)
AREA_COORDINATES = {
    1: (85, 150, 415, 540),
    2: (85, 540, 415, 950),
    3: (425, 150, 755, 590),
    4: (425, 540, 755, 1010),
    5: (85, 260, 415, 540),
    6: (435, 220, 765, 540),
    7: (85, 200, 415, 540),
    8: (85, 150, 415, 800),
    9: (435, 150, 765, 1010),
    10: (85, 200, 415, 700),
    11: (425, 200, 755, 500),
    12: (425, 640, 755, 1050),
    13: (425, 150, 755, 800),
}

PAGE_AREA_CONFIG = {
    1: [5, 2, 6, 4],
    2: [1, 2, 3], 3: [1, 2, 3], 7: [1, 2, 9],
    4: [1, 3], 5: [8, 13], 8: [1, 3], 10: [1, 3], 11: [1, 9],
    14: [1, 3], 15: [1, 3], 18: [1, 3], 19: [1, 9],
    6: [1, 11, 4],
    12: [7, 3], 16: [7, 3], 20: [10, 3],
    9: [5, 6], 13: [5, 6], 17: [5, 6],
}

FILENAME_SUFFIXES = (
    [f"{i:02d}" for i in range(1, 23)]
    + [f"확{i}" for i in range(23, 31)]
    + [f"미{i}" for i in range(23, 31)]
    + [f"기{i}" for i in range(23, 31)]
)


def extract(input_pdf, output_dir, base_filename="2027.9모"):
    doc = fitz.open(input_pdf)
    os.makedirs(output_dir, exist_ok=True)

    suffix_index = 0
    for page_num in sorted(PAGE_AREA_CONFIG):
        page = doc[page_num - 1]
        for area_id in PAGE_AREA_CONFIG[page_num]:
            left, top, right, bottom = AREA_COORDINATES[area_id]
            rect = fitz.Rect(
                max(0, min(left, page.rect.width)),
                max(0, min(top, page.rect.height)),
                min(right, page.rect.width),
                min(bottom, page.rect.height),
            )

            new_doc = fitz.open()
            new_page = new_doc.new_page(width=rect.width, height=rect.height)
            new_page.show_pdf_page(new_page.rect, doc, page_num - 1, clip=rect)
            trim_white_space_visual(new_page, padding=10)

            suffix = FILENAME_SUFFIXES[suffix_index]
            new_doc.save(os.path.join(output_dir, f"{base_filename}_{suffix}.pdf"))
            new_doc.close()
            print(f"저장됨: {base_filename}_{suffix}.pdf (페이지 {page_num}, 영역 {area_id})")
            suffix_index += 1

    doc.close()
    print(f"\n총 {suffix_index}개 추출 완료 → {output_dir}")


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "2027.9모")
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, "scratch", "2027_9mo_extracted")
    extract(src, dst)
