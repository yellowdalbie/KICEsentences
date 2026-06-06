import os
import re
import fitz  # PyMuPDF
from PIL import Image, ImageChops

def trim_white_space_visual(page, padding=10):
    """
    페이지를 이미지로 렌더링하여 '눈에 보이는' 잉크 영역을 찾고,
    해당 영역으로 PDF 크롭 박스를 설정합니다.
    """
    zoom = 2
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    gray = img.convert("L")
    binary = gray.point(lambda p: 255 if p > 250 else 0)
    inverted = ImageChops.invert(binary)
    bbox = inverted.getbbox()

    if bbox:
        left, top, right, bottom = bbox
        
        # 가로 폭 고정: 좌우는 자르지 않고 원본 유지
        pdf_left = 0
        pdf_top = top / zoom
        pdf_right = page.rect.width
        pdf_bottom = bottom / zoom

        pdf_top = max(0, pdf_top - padding)
        pdf_bottom = min(page.rect.height, pdf_bottom + padding)

        if (pdf_right > pdf_left) and (pdf_bottom > pdf_top):
            new_rect = fitz.Rect(pdf_left, pdf_top, pdf_right, pdf_bottom)
            page.set_cropbox(new_rect)
            return True
            
    return False

def extract_and_trim(input_pdf, output_dir, base_filename="2027.6모"):
    # 영역 좌표 정의
    area_coordinates = {
        1: (85, 150, 415, 540),
        2: (85, 540, 415, 950),
        3: (425, 150, 755, 590),
        4: (425, 540, 755, 1010),
        5: (85, 260, 415, 540),
        6: (435, 220, 765, 540),
        7: (85, 200, 415, 540),
        8: (85, 150, 415, 800),
        9: (435, 150, 765, 880),
        10: (85, 200, 415, 700),
        11: (425, 200, 755, 500),
        12: (425, 640, 755, 1050),
        13: (425, 150, 755, 800)
    }

    # 페이지별 추출 영역 설정
    page_area_config = {
        1: [5, 2, 6, 4],
        2: [1, 2, 3], 3: [1, 2, 3], 7: [1, 2, 9],
        4: [1, 3], 5: [8, 13], 8: [1, 3], 10: [1, 3], 11: [1, 9], 14: [1, 3], 15: [1, 3], 18: [1, 3], 19: [1, 9],
        6: [1, 11, 4],
        12: [7, 3], 16: [7, 3], 20: [10, 3],
        9: [5, 6], 13: [5, 6], 17: [5, 6]
    }

    # 파일명 접미사 설정
    filename_suffixes = (
        [f"{i:02d}" for i in range(1, 23)] +
        [f"확{i}" for i in range(23, 31)] +
        [f"미{i}" for i in range(23, 31)] +
        [f"기{i}" for i in range(23, 31)]
    )

    doc = fitz.open(input_pdf)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    suffix_index = 0
    total_extracted = 0

    for page_num in sorted(page_area_config.keys()):
        if page_num > len(doc):
            print(f"경고: {page_num}페이지가 존재하지 않습니다. 건너뜁니다.")
            continue
        
        page = doc[page_num - 1]
        print(f"처리 중: 페이지 {page_num} (크기: 너비={page.rect.width}, 높이={page.rect.height})")
        
        for area_id in page_area_config[page_num]:
            if suffix_index >= len(filename_suffixes):
                print("경고: 접미사 인덱스가 초과되었습니다.")
                break

            left, top, right, bottom = area_coordinates[area_id]
            
            # 좌표가 페이지 범위 내에 있는지 확인
            left = max(0, min(left, page.rect.width))
            top = max(0, min(top, page.rect.height))
            right = max(left, min(right, page.rect.width))
            bottom = max(top, min(bottom, page.rect.height))
            
            rect = fitz.Rect(left, top, right, bottom)
            
            if rect.is_empty or rect.is_infinite:
                print(f"경고: 유효하지 않은 클리핑 영역입니다. 건너뜁니다. 영역: {rect}")
                continue
            
            # Step 1: 새 PDF 생성 및 영역 추출 (클리핑)
            new_doc = fitz.open()
            new_page = new_doc.new_page(width=rect.width, height=rect.height)
            new_page.show_pdf_page(new_page.rect, doc, page_num - 1, clip=rect)
            
            # Step 2: 픽셀 기반 여백 트리밍
            trim_white_space_visual(new_page, padding=10)
            
            suffix = filename_suffixes[suffix_index]
            output_filename = f"{base_filename}_{suffix}.pdf"
            output_path = os.path.join(output_dir, output_filename)
            
            new_doc.save(output_path)
            new_doc.close()
            
            print(f"저장됨: {output_filename} (페이지 {page_num}, 영역 {area_id})")
            
            suffix_index += 1
            total_extracted += 1
    
    doc.close()
    print(f"\n작업 완료! 총 {total_extracted}개의 파일이 추출되었습니다.")
    print(f"출력 경로: {output_dir}")

if __name__ == "__main__":
    import sys
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_pdf_path = os.path.join(project_root, "suneung27mo06_2.pdf")
    output_dir_path = os.path.join(project_root, "scratch", "2027_6mo_extracted")
    
    if not os.path.exists(input_pdf_path):
        print(f"에러: 입력 PDF 파일을 찾을 수 없습니다: {input_pdf_path}", file=sys.stderr)
        sys.exit(1)
        
    extract_and_trim(input_pdf_path, output_dir_path, base_filename="2027.6모")
