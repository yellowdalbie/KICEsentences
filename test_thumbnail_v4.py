#!/usr/bin/env python3
"""
썸네일 v4 테스트 스크립트
- 마침표(.)를 2D 앵커로 사용: (ANCHOR_X_TARGET, ANCHOR_Y_TARGET)
- y축 정렬 추가 (기존에는 x축만 정렬)
- 번호 영역 흰색 strip으로 차폐 (0 ~ MASK_RIGHT_EDGE)
"""

import os
import re
import unicodedata
import pypdfium2 as pdfium
from PIL import Image, ImageDraw
import numpy as np

# --- CONFIGURATION ---
PDF_DIR = 'PDF_Ref'
TEST_OUTPUT_DIR = os.path.join('static', 'thumbnails_test')
SCALE = 4.2
CANVAS_WIDTH = 1400
ANCHOR_X_1DIGIT  = 2    # 1자리 번호(1~9)의 마침표 오른쪽 끝 x
ANCHOR_X_2DIGIT  = 29   # 2자리 번호(10~30)의 마침표 오른쪽 끝 x
ANCHOR_Y_TARGET  = 90   # 마침표 상단 y (공통) — 위첨자/숫자 높이 고려해 넉넉히
MASK_LINE_HEIGHT = 8    # 마침표 세로 높이 (≈ 8px)
PERIOD_WIDTH_PX  = 11   # 마침표 가로폭 (≈ 2.59 PDF pts × 4.2 scale)
WHITE_THRESHOLD = 250

# 번호 폭이 다양한 테스트 대상 (1자리/2자리, 좁은/넓은)
TEST_FILES = [
    '2024수능_01.pdf',   # 번호: 1  (1자리, 좁음)
    '2024수능_05.pdf',   # 번호: 5
    '2024수능_09.pdf',   # 번호: 9  (1자리, 넓음)
    '2024수능_11.pdf',   # 번호: 11 (2자리, 좁음 - 1이 두개)
    '2024수능_15.pdf',   # 번호: 15
    '2024수능_19.pdf',   # 번호: 19
    '2024수능_22.pdf',   # 번호: 22 (2자리, 중간)
    '2024수능_28.pdf',   # 번호: 28
    '2024수능_30.pdf',   # 번호: 30 (2자리, 넓음)
]

os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)


def get_problem_number(problem_id):
    # [가나a-zA-Z]+ 만 prefix로 허용 — \w는 숫자 포함이라 "11"→"1" 오파싱 발생
    match = re.search(r'_([가나a-zA-Z]+)?(\d+)$', problem_id)
    if not match:
        return None
    return str(int(match.group(2)))  # leading zero 제거: "01" → "1"


def get_anchor_point(page, problem_num):
    """마침표의 right_x 반환 (PDF 좌표, x축만 사용)."""
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
            return charbox[2]  # right_x only
        occ = search.get_next()

    return None


def find_period_top_y(img_array, period_right_x_px, search_limit=300):
    """
    마침표의 오른쪽 끝 x(period_right_x_px)에서 마침표 본체 중앙 컬럼을 스캔하여
    마침표 상단 y좌표를 직접 탐지.

    왜 이 컬럼인가:
    - 마침표는 숫자보다 오른쪽에 위치하므로, 마침표 본체 x에는 숫자 획이 없음
    - 문항 본문은 마침표보다 오른쪽(ANCHOR_X_TARGET 이후)에서 시작하므로 간섭 없음
    - 따라서 이 컬럼의 첫 번째 어두운 픽셀 = 마침표 상단
    """
    x_scan = max(0, period_right_x_px - PERIOD_WIDTH_PX // 2)  # 마침표 본체 중앙
    for y in range(min(search_limit, img_array.shape[0])):
        if np.all(img_array[y, x_scan, :3] < WHITE_THRESHOLD):
            return y
    # fallback: 전체 행 스캔
    for y in range(min(search_limit, img_array.shape[0])):
        row = img_array[y, :, :3]
        if np.any(np.all(row < WHITE_THRESHOLD, axis=1)):
            return y
    return 0


def get_auto_crop_height(img):
    """기존 자동 크롭 알고리즘 (하단 공백 제거)."""
    img_array = np.array(img)
    img_h, img_w, _ = img_array.shape

    def is_row_white(y):
        if y >= img_h: return True
        if y < 0: return True
        row = img_array[int(y), :, :3]
        return not np.any(np.all(row < WHITE_THRESHOLD, axis=1))

    y_current = 200
    prev_y = 0
    final_cut_y = img_h
    found_gap = False

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
                found_gap = True
                break

        prev_y = y_current
        y_current += 200

    return final_cut_y


def process_thumbnail_test(filename):
    problem_id = filename.replace('.pdf', '')
    pdf_path = os.path.join(PDF_DIR, filename)
    nfc_id = unicodedata.normalize('NFC', problem_id)
    thumb_path = os.path.join(TEST_OUTPUT_DIR, f'{nfc_id}.png')

    if not os.path.exists(pdf_path):
        print(f"  ✗ 파일 없음: {filename}")
        return False

    try:
        pdf = pdfium.PdfDocument(pdf_path)
        page = pdf[0]
        page_width, page_height = page.get_size()

        # 1. x 앵커 탐지 (PDF 텍스트 좌표)
        num = get_problem_number(problem_id)
        anchor_x_pdf = get_anchor_point(page, num)

        # 2. 전체 페이지 렌더링
        bitmap = page.render(scale=SCALE)
        raw_img = bitmap.to_pil()
        img_w, img_h = raw_img.size
        img_array = np.array(raw_img)

        # 3. x 오프셋 계산 (자릿수 분기)
        is_2digit = len(num) >= 2
        anchor_x = ANCHOR_X_2DIGIT if is_2digit else ANCHOR_X_1DIGIT
        mask_right = anchor_x + 2

        if anchor_x_pdf is not None:
            period_x_px = int(anchor_x_pdf * SCALE)
            offset_x = anchor_x - period_x_px
        else:
            period_x_px = anchor_x
            offset_x = 0
            print(f"  ⚠ x앵커 미검출: {nfc_id} (fallback)")

        # 4. y 오프셋 계산: 마침표 컬럼 직접 스캔 (PDF 추출 방식 무관)
        period_y_px = find_period_top_y(img_array, period_x_px)
        offset_y = ANCHOR_Y_TARGET - period_y_px

        # 4. 하단 자동 크롭
        target_h = get_auto_crop_height(raw_img)
        raw_img = raw_img.crop((0, 0, img_w, min(img_h, target_h)))
        cropped_h = raw_img.size[1]

        # 5. 캔버스 생성 (offset_y 양수이면 위쪽 여백 필요)
        top_pad = max(0, offset_y)
        canvas_h = cropped_h + top_pad
        canvas = Image.new('RGB', (CANVAS_WIDTH, canvas_h), (255, 255, 255))
        canvas.paste(raw_img, (offset_x, offset_y))

        # 6. 번호 차폐: 1행 높이만큼의 사각형 (전체 높이 strip 금지 — 2행 이후 잘림 방지)
        mask_bottom = ANCHOR_Y_TARGET + MASK_LINE_HEIGHT
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, 0, mask_right, mask_bottom], fill=(255, 255, 255))

        canvas.save(thumb_path, 'PNG', optimize=True)
        pdf.close()

        print(f"  ✓ {nfc_id:25s}  번호={num:>2s}({'2' if is_2digit else '1'}자리)  "
              f"period_x={period_x_px:4d}px  period_y={period_y_px:4d}px  "
              f"canvas_period=({period_x_px+offset_x}, {period_y_px+offset_y})  "
              f"mask_right={mask_right}")
        return True

    except Exception as e:
        print(f"  ✗ 오류: {filename}: {e}")
        return False


def main():
    print(f"=== 썸네일 v4 테스트 ({len(TEST_FILES)}개) ===")
    print(f"앵커: (1자리={ANCHOR_X_1DIGIT}, 2자리={ANCHOR_X_2DIGIT}, y={ANCHOR_Y_TARGET})  마스크 right: 1자리={ANCHOR_X_1DIGIT+2}, 2자리={ANCHOR_X_2DIGIT+2}\n")

    for f in TEST_FILES:
        process_thumbnail_test(f)

    print(f"\n출력 디렉토리: {TEST_OUTPUT_DIR}")


if __name__ == "__main__":
    main()
