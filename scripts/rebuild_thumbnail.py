import os
import sys
import re
import unicodedata
import pypdfium2 as pdfium
from PIL import Image, ImageDraw
import numpy as np

# --- CONFIGURATION ---
PDF_DIR = 'PDF_Ref'
THUMBNAIL_DIR = os.path.join('static', 'thumbnails')
TEST_DIR = os.path.join('static', 'thumbnails_test')
SCALE = 4.2
CANVAS_WIDTH = 1400
ANCHOR_X_1DIGIT  = 2
ANCHOR_X_2DIGIT  = 29
ANCHOR_Y_TARGET  = 90
MASK_LINE_HEIGHT = 8
PERIOD_WIDTH_PX  = 11
WHITE_THRESHOLD  = 250

def get_problem_number(problem_id):
    match = re.search(r'_\D*(\d+)$', problem_id)
    if not match:
        return None
    return str(int(match.group(1)))

def get_anchor_point(page, problem_num):
    if not problem_num:
        return None, None
    tp = page.get_textpage()
    page_width, page_height = page.get_size()
    # CropBox를 기준으로 실제 렌더링 영역의 상단 좌표를 구함
    left, bottom, right, top = page.get_cropbox()
    target = f"{problem_num}."
    search = tp.search(target)
    occ = search.get_next()
    while occ:
        index, count = occ
        charbox = tp.get_charbox(index + count - 1)
        if charbox[0] < (page_width / 3):
            # Return (right_x - left, top - charbox[3])
            # left와 top을 빼주는 이유는 render 결과가 CropBox 기준이기 때문
            return (charbox[2] - left), (top - charbox[3])
        occ = search.get_next()
    
    # 2차 시도 (MediaBox 대응)
    search = tp.search(target)
    occ = search.get_next()
    while occ:
        index, count = occ
        charbox = tp.get_charbox(index + count - 1)
        if charbox[0] < 200:
            return (charbox[2] - left), (top - charbox[3])
        occ = search.get_next()
    return None, None

def find_period_top_y(img_array, period_right_x_px, expected_y_px, search_range=100):
    """
    expected_y_px: PDF 텍스트 검색으로 얻은 대략적인 y좌표 (이미지 스케일 적용됨)
    search_range: 예상 위치 전후로 탐색할 범위
    """
    x_scan = max(0, period_right_x_px - PERIOD_WIDTH_PX // 2)
    
    # 1. 예상 위치 근처에서 정밀 탐색
    start_y = max(0, int(expected_y_px - search_range))
    end_y = min(img_array.shape[0], int(expected_y_px + search_range))
    
    for y in range(start_y, end_y):
        if np.all(img_array[y, x_scan, :3] < WHITE_THRESHOLD):
            return y
            
    # 2. Fallback: 전체 위에서부터 스캔 (기존 방식)
    for y in range(min(300, img_array.shape[0])):
        if np.all(img_array[y, x_scan, :3] < WHITE_THRESHOLD):
            return y
    return 0

def get_auto_crop_height(img):
    img_array = np.array(img)
    img_h, img_w, _ = img_array.shape
    def is_row_white(y):
        if y >= img_h or y < 0: return True
        row = img_array[int(y), :, :3]
        return not np.any(np.all(row < WHITE_THRESHOLD, axis=1))
    y_current = 200
    prev_y = 0
    final_cut_y = img_h
    while y_current < img_h:
        if is_row_white(y_current) and is_row_white(prev_y):
            m = y_current - 100
            if is_row_white(m):
                search_y = prev_y - 25
                last_content_found = 0
                while search_y >= 0:
                    if not is_row_white(search_y):
                        last_content_found = search_y
                        break
                    search_y -= 25
                final_cut_y = last_content_found + 50
                break
        prev_y = y_current
        y_current += 200
    return final_cut_y

def process_single(problem_id, target_height=None, use_test_dir=True):
    problem_id = problem_id.replace('.pdf', '')
    pdf_path = os.path.join(PDF_DIR, f"{problem_id}.pdf")
    nfc_id = unicodedata.normalize('NFC', problem_id)
    
    out_dir = TEST_DIR if use_test_dir else THUMBNAIL_DIR
    os.makedirs(out_dir, exist_ok=True)
    thumb_path = os.path.join(out_dir, f'{nfc_id}.png')

    if not os.path.exists(pdf_path):
        print(f"Error: PDF not found at {pdf_path}")
        return False

    try:
        pdf = pdfium.PdfDocument(pdf_path)
        page = pdf[0]
        num = get_problem_number(problem_id)
        anchor_x_pdf, anchor_y_pdf = get_anchor_point(page, num)
        
        bitmap = page.render(scale=SCALE)
        raw_img = bitmap.to_pil()
        img_w, img_h = raw_img.size
        img_array = np.array(raw_img)
        
        is_2digit = num is not None and len(num) >= 2
        anchor_x_target = ANCHOR_X_2DIGIT if is_2digit else ANCHOR_X_1DIGIT
        mask_right = anchor_x_target + 2

        if anchor_x_pdf is not None:
            period_x_px = int(anchor_x_pdf * SCALE)
            period_y_pdf_px = int(anchor_y_pdf * SCALE)
            offset_x = anchor_x_target - period_x_px
            # y 앵커 정밀 탐색
            period_y_px = find_period_top_y(img_array, period_x_px, period_y_pdf_px)
        else:
            period_x_px = anchor_x_target
            period_y_px = 0
            offset_x = 0
            print(f"Warning: Anchor not found for {nfc_id}")

        offset_y = ANCHOR_Y_TARGET - period_y_px
        
        # 1. 넉넉한 캔버스 생성 및 배치
        canvas = Image.new('RGB', (CANVAS_WIDTH, 2000), (255, 255, 255))
        canvas.paste(raw_img, (offset_x, offset_y))
        
        # 2. 번호 가리기 (Masking)
        mask_bottom = ANCHOR_Y_TARGET + MASK_LINE_HEIGHT
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, 0, mask_right, mask_bottom], fill=(255, 255, 255))
        
        # 3. 크롭 결정
        if target_height:
            final_h = int(target_height)
        else:
            # 캔버스 상에서 내용이 끝나는 지점 찾기
            canvas_array = np.array(canvas)
            h_limit = canvas_array.shape[0]
            
            def is_canvas_row_white(y):
                if y >= h_limit: return True
                row = canvas_array[y, :, :3]
                return not np.any(np.all(row < WHITE_THRESHOLD, axis=1))

            last_content_y = 0
            for y in range(h_limit - 1, 0, -1):
                if not is_canvas_row_white(y):
                    last_content_y = y
                    break
            final_h = last_content_y + 40 # 여백 추가
            
            # 최소 높이 보장
            final_h = max(final_h, ANCHOR_Y_TARGET + 100)

        # 4. 최종 크롭 및 저장
        canvas = canvas.crop((0, 0, CANVAS_WIDTH, final_h))
        canvas.save(thumb_path, 'PNG', optimize=True)
        
        pdf.close()
        print(f"Success: {thumb_path} created. (Height: {final_h})")
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python rebuild_thumbnail.py <problem_id> [height]")
        sys.exit(1)
    
    p_id = sys.argv[1]
    h = sys.argv[2] if len(sys.argv) > 2 else None
    process_single(p_id, h)
