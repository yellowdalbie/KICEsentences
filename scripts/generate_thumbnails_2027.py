import os
import re
import unicodedata
import pypdfium2 as pdfium
from PIL import Image, ImageDraw
import numpy as np

# --- CONFIGURATION ---
PDF_DIR = 'PDF_Ref'
# 임시 썸네일 출력 폴더
THUMBNAIL_DIR = os.path.join('scratch', '2027_6mo_thumbnails')
SCALE = 4.2
CANVAS_WIDTH = 1400
ANCHOR_X_1DIGIT  = 2    # 1자리 번호(1~9)의 마침표 오른쪽 끝 x (canvas px)
ANCHOR_X_2DIGIT  = 29   # 2자리 번호(10~30)의 마침표 오른쪽 끝 x (canvas px)
ANCHOR_Y_TARGET  = 90   # 마침표 상단 y (canvas px, 공통)
MASK_LINE_HEIGHT = 8    # 마침표 세로 높이 (≈ 8px)
PERIOD_WIDTH_PX  = 11   # 마침표 가로폭 (≈ 2.59 PDF pts × 4.2 scale)
WHITE_THRESHOLD  = 250

# --- INDIVIDUAL COACHING OVERRIDES ---
CROP_OVERRIDES = {}

os.makedirs(THUMBNAIL_DIR, exist_ok=True)


def get_problem_number(problem_id):
    match = re.search(r'_\D*(\d+)$', problem_id)
    if not match:
        return None
    return str(int(match.group(1)))


def get_anchor_point(page, problem_num):
    if not problem_num:
        return None

    tp = page.get_textpage()
    page_width, _ = page.get_size()
    target = f"{problem_num}."

    search = tp.search(target)
    occ = search.get_next()
    while occ:
        index, count = occ
        charbox = tp.get_charbox(index + count - 1)
        if charbox[0] < (page_width / 3):
            return charbox[2]
        occ = search.get_next()

    search = tp.search(target)
    occ = search.get_next()
    while occ:
        index, count = occ
        charbox = tp.get_charbox(index + count - 1)
        if charbox[0] < 200:
            print(f"  ⚠ x앵커 2차fallback 사용: num={problem_num} charbox[0]={charbox[0]:.1f} page_width={page_width:.1f}")
            return charbox[2]
        occ = search.get_next()

    return None


def find_period_top_y(img_array, period_right_x_px, search_limit=300):
    x_scan = max(0, period_right_x_px - PERIOD_WIDTH_PX // 2)
    for y in range(min(search_limit, img_array.shape[0])):
        if np.all(img_array[y, x_scan, :3] < WHITE_THRESHOLD):
            return y
    for y in range(min(search_limit, img_array.shape[0])):
        row = img_array[y, :, :3]
        if np.any(np.all(row < WHITE_THRESHOLD, axis=1)):
            return y
    return 0


def get_auto_crop_height(img):
    img_array = np.array(img)
    img_h, img_w, _ = img_array.shape

    def is_row_white(y):
        if y >= img_h or y < 0:
            return True
        row = img_array[int(y), :, :3]
        return not np.any(np.all(row < WHITE_THRESHOLD, axis=1))

    y_current = 200
    prev_y = 0
    final_cut_y = img_h

    while y_current < img_h:
        res_current = is_row_white(y_current)
        res_prev = is_row_white(prev_y)

        if res_current and res_prev:
            m = y_current - 100
            q = [y_current - 150, y_current - 50]
            e = [y_current - 175, y_current - 125, y_current - 75, y_current - 25]

            all_internal_white = True
            for cy in [m] + q + e:
                if not is_row_white(cy):
                    all_internal_white = False
                    break

            if all_internal_white:
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


def process_thumbnail(filename, verbose=False):
    problem_id = filename.replace('.pdf', '')
    pdf_path = os.path.join(PDF_DIR, filename)
    nfc_id = unicodedata.normalize('NFC', problem_id)
    thumb_path = os.path.join(THUMBNAIL_DIR, f'{nfc_id}.png')

    try:
        pdf = pdfium.PdfDocument(pdf_path)
        page = pdf[0]

        num = get_problem_number(problem_id)
        anchor_x_pdf = get_anchor_point(page, num)

        bitmap = page.render(scale=SCALE)
        raw_img = bitmap.to_pil()
        img_w, img_h = raw_img.size
        img_array = np.array(raw_img)

        is_2digit = num is not None and len(num) >= 2
        anchor_x = ANCHOR_X_2DIGIT if is_2digit else ANCHOR_X_1DIGIT
        mask_right = anchor_x + 2

        if anchor_x_pdf is not None:
            period_x_px = int(anchor_x_pdf * SCALE)
            offset_x = anchor_x - period_x_px
        else:
            period_x_px = anchor_x
            offset_x = 0
            print(f"  ⚠ x앵커 미검출: {nfc_id} (fallback)")

        period_y_px = find_period_top_y(img_array, period_x_px)
        offset_y = ANCHOR_Y_TARGET - period_y_px

        if nfc_id in CROP_OVERRIDES:
            target_h = CROP_OVERRIDES[nfc_id].get('height', img_h)
        else:
            target_h = get_auto_crop_height(raw_img)
        raw_img = raw_img.crop((0, 0, img_w, min(img_h, target_h)))
        cropped_h = raw_img.size[1]

        top_pad = max(0, offset_y)
        canvas_h = cropped_h + top_pad
        canvas = Image.new('RGB', (CANVAS_WIDTH, canvas_h), (255, 255, 255))
        canvas.paste(raw_img, (offset_x, offset_y))

        mask_bottom = ANCHOR_Y_TARGET + MASK_LINE_HEIGHT
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, 0, mask_right, mask_bottom], fill=(255, 255, 255))

        canvas.save(thumb_path, 'PNG', optimize=True)
        pdf.close()

        if verbose:
            print(f"  ✓ {nfc_id:28s}  num={num or '?':>2s}({'2' if is_2digit else '1'}자리)  "
                  f"period_x={period_x_px:4d}px  period_y={period_y_px:4d}px  "
                  f"offset=({offset_x:+d},{offset_y:+d})  mask_right={mask_right}")
        return True

    except Exception as e:
        print(f"  ✗ 오류: {filename}: {e}")
        return False


def main():
    # 2027.6모 관련 파일만 필터링
    pdf_files = sorted([f for f in os.listdir(PDF_DIR) if f.startswith('2027.6모') and f.endswith('.pdf')])
    total = len(pdf_files)
    print(f"=== 2027학년도 6월 모의평가 썸네일 생성 ({total}개) ===")

    count = 0
    for i, f in enumerate(pdf_files):
        if process_thumbnail(f, verbose=True):
            count += 1
        if (i + 1) % 10 == 0:
            print(f"진행: {i+1}/{total} 완료...")

    print(f"\n완료! 생성된 썸네일: {count}/{total}")
    print(f"출력 경로: {THUMBNAIL_DIR}")


if __name__ == "__main__":
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    main()
