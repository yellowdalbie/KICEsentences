import os
import re
import unicodedata
import pypdfium2 as pdfium
from PIL import Image, ImageDraw
import numpy as np

# --- CONFIGURATION ---
PDF_DIR = 'PDF_Ref'
THUMBNAIL_DIR = os.path.join('static', 'thumbnails')
SCALE = 4.2
CANVAS_WIDTH = 1400
ANCHOR_X_1DIGIT  = 2    # 1자리 번호(1~9)의 마침표 오른쪽 끝 x (canvas px)
ANCHOR_X_2DIGIT  = 29   # 2자리 번호(10~30)의 마침표 오른쪽 끝 x (canvas px)
ANCHOR_Y_TARGET  = 90   # 마침표 상단 y (canvas px, 공통)
MASK_LINE_HEIGHT = 8    # 마침표 세로 높이 (≈ 8px)
PERIOD_WIDTH_PX  = 11   # 마침표 가로폭 (≈ 2.59 PDF pts × 4.2 scale)
WHITE_THRESHOLD  = 250

# --- INDIVIDUAL COACHING OVERRIDES ---
# Key: problem_id (NFC normalized), Value: {'height': pixels}
CROP_OVERRIDES = {
    unicodedata.normalize('NFC', "2014.6모A_30"): {'height': 560},
    unicodedata.normalize('NFC', "2014.6모B_30"): {'height': 750},
    unicodedata.normalize('NFC', "2014.9모A_30"): {'height': 420},
    unicodedata.normalize('NFC', "2014.9모B_30"): {'height': 700},
    unicodedata.normalize('NFC', "2014수능A_30"): {'height': 360},
    unicodedata.normalize('NFC', "2014수능B_30"): {'height': 780},
    unicodedata.normalize('NFC', "2015.6모A_30"): {'height': 520},
    unicodedata.normalize('NFC', "2015.6모B_30"): {'height': 1050},
    unicodedata.normalize('NFC', "2015.9모A_30"): {'height': 720},
    unicodedata.normalize('NFC', "2015.9모B_30"): {'height': 1100},
    unicodedata.normalize('NFC', "2015수능A_30"): {'height': 700},
    unicodedata.normalize('NFC', "2015수능B_30"): {'height': 520},
    unicodedata.normalize('NFC', "2016.6모A_30"): {'height': 650},
    unicodedata.normalize('NFC', "2016.6모B_30"): {'height': 1200},
    unicodedata.normalize('NFC', "2016.9모A_30"): {'height': 580},
    unicodedata.normalize('NFC', "2016.9모B_30"): {'height': 830},
    unicodedata.normalize('NFC', "2016수능A_30"): {'height': 1040},
    unicodedata.normalize('NFC', "2016수능B_30"): {'height': 900},
    unicodedata.normalize('NFC', "2017.6모가_30"): {'height': 1100},
    unicodedata.normalize('NFC', "2017.6모나_30"): {'height': 520},
    unicodedata.normalize('NFC', "2017.9모가_30"): {'height': 560},
    unicodedata.normalize('NFC', "2017.9모나_30"): {'height': 1020},
    unicodedata.normalize('NFC', "2017수능가_30"): {'height': 1150},
    unicodedata.normalize('NFC', "2017수능나_30"): {'height': 380},
    unicodedata.normalize('NFC', "2018.6모가_30"): {'height': 1250},
    unicodedata.normalize('NFC', "2018.6모나_30"): {'height': 680},
    unicodedata.normalize('NFC', "2018.9모가_30"): {'height': 800},
    unicodedata.normalize('NFC', "2018.9모나_30"): {'height': 1500},
    unicodedata.normalize('NFC', "2018수능가_30"): {'height': 1430},
    unicodedata.normalize('NFC', "2018수능나_30"): {'height': 1500},
    unicodedata.normalize('NFC', "2019.6모가_30"): {'height': 800},
    unicodedata.normalize('NFC', "2019.6모나_30"): {'height': 820},
    unicodedata.normalize('NFC', "2019.9모가_30"): {'height': 880},
    unicodedata.normalize('NFC', "2019.9모나_30"): {'height': 600},
    unicodedata.normalize('NFC', "2019수능가_30"): {'height': 1200},
    unicodedata.normalize('NFC', "2019수능나_30"): {'height': 1400},
    unicodedata.normalize('NFC', "2020.6모가_30"): {'height': 2300},
    unicodedata.normalize('NFC', "2020.6모나_30"): {'height': 1100},
    unicodedata.normalize('NFC', "2020.9모가_30"): {'height': 450},
    unicodedata.normalize('NFC', "2020.9모나_30"): {'height': 480},
    unicodedata.normalize('NFC', "2020수능가_30"): {'height': 350},
    unicodedata.normalize('NFC', "2020수능나_30"): {'height': 600},
    unicodedata.normalize('NFC', "2021.6모가_30"): {'height': 1620},
    unicodedata.normalize('NFC', "2021.6모나_30"): {'height': 990},
    unicodedata.normalize('NFC', "2021.9모가_30"): {'height': 900},
    unicodedata.normalize('NFC', "2021.9모나_30"): {'height': 770},
    unicodedata.normalize('NFC', "2021수능가_30"): {'height': 940},
    unicodedata.normalize('NFC', "2021수능나_30"): {'height': 650},
    unicodedata.normalize('NFC', "2022.6모_기30"): {'height': 900},
    unicodedata.normalize('NFC', "2022.6모_미30"): {'height': 450},
    unicodedata.normalize('NFC', "2022.6모_확30"): {'height': 1200},
    unicodedata.normalize('NFC', "2022.9모_기30"): {'height': 950},
    unicodedata.normalize('NFC', "2022.9모_미30"): {'height': 1050},
    unicodedata.normalize('NFC', "2022.9모_확30"): {'height': 670},
}

os.makedirs(THUMBNAIL_DIR, exist_ok=True)


def get_problem_number(problem_id):
    """파일명에서 문항번호 추출. leading zero 제거.
    _ 이후 비숫자 접두어(가나/기미확/A-Z 등 모두 허용)를 건너뛰고 끝 숫자 캡처.
    """
    match = re.search(r'_\D*(\d+)$', problem_id)
    if not match:
        return None
    return str(int(match.group(1)))  # '01' → '1'


def get_anchor_point(page, problem_num):
    """마침표(.)의 right_x 반환 (PDF 좌표계).

    1차: page_width/3 기반 필터 (정상 PDF).
    2차: MediaBox 불일치 대응 — 고정 임계값 200pt로 재시도.
    """
    if not problem_num:
        return None

    tp = page.get_textpage()
    page_width, _ = page.get_size()
    target = f"{problem_num}."

    # 1차 시도: page_width 기반 (정상 PDF)
    search = tp.search(target)
    occ = search.get_next()
    while occ:
        index, count = occ
        charbox = tp.get_charbox(index + count - 1)
        if charbox[0] < (page_width / 3):
            return charbox[2]  # right_x
        occ = search.get_next()

    # 2차 시도: MediaBox가 콘텐츠 좌표보다 작은 PDF 대응
    search = tp.search(target)
    occ = search.get_next()
    while occ:
        index, count = occ
        charbox = tp.get_charbox(index + count - 1)
        if charbox[0] < 200:
            print(f"  ⚠ x앵커 2차fallback 사용: num={problem_num} charbox[0]={charbox[0]:.1f} page_width={page_width:.1f}")
            return charbox[2]  # right_x
        occ = search.get_next()

    return None


def find_period_top_y(img_array, period_right_x_px, search_limit=300):
    """마침표 본체 중앙 컬럼을 스캔하여 마침표 상단 y좌표 탐지.

    period_right_x_px: 렌더링된 이미지에서 마침표 오른쪽 끝 x (px).
    마침표 본체 중앙 = period_right_x_px - PERIOD_WIDTH_PX // 2.
    이 컬럼의 첫 번째 어두운 픽셀 = 마침표 상단.
    """
    x_scan = max(0, period_right_x_px - PERIOD_WIDTH_PX // 2)
    for y in range(min(search_limit, img_array.shape[0])):
        if np.all(img_array[y, x_scan, :3] < WHITE_THRESHOLD):
            return y
    # fallback: 전체 행 스캔 (첫 콘텐츠 행)
    for y in range(min(search_limit, img_array.shape[0])):
        row = img_array[y, :, :3]
        if np.any(np.all(row < WHITE_THRESHOLD, axis=1)):
            return y
    return 0


def get_auto_crop_height(img):
    """하단 공백 자동 탐지 알고리즘.
    200px 단위 coarse scan → 연속 공백 확인 → 역방향 25px 정밀 탐색.
    """
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

        # 1. 문항번호 추출 및 x 앵커 탐지
        num = get_problem_number(problem_id)
        anchor_x_pdf = get_anchor_point(page, num)

        # 2. 전체 페이지 렌더링
        bitmap = page.render(scale=SCALE)
        raw_img = bitmap.to_pil()
        img_w, img_h = raw_img.size
        img_array = np.array(raw_img)

        # 3. x 오프셋 계산 (1자리/2자리 분기)
        is_2digit = num is not None and len(num) >= 2
        anchor_x = ANCHOR_X_2DIGIT if is_2digit else ANCHOR_X_1DIGIT
        mask_right = anchor_x + 2

        if anchor_x_pdf is not None:
            period_x_px = int(anchor_x_pdf * SCALE)
            offset_x = anchor_x - period_x_px
        else:
            # anchor 미검출: x 정렬 포기, y 스캔용 x는 anchor_x로 대체
            period_x_px = anchor_x
            offset_x = 0
            print(f"  ⚠ x앵커 미검출: {nfc_id} (fallback)")

        # 4. y 오프셋 계산: 렌더링된 이미지에서 마침표 상단 y 직접 스캔
        period_y_px = find_period_top_y(img_array, period_x_px)
        offset_y = ANCHOR_Y_TARGET - period_y_px

        # 5. 하단 자동 크롭 (CROP_OVERRIDES 우선)
        if nfc_id in CROP_OVERRIDES:
            target_h = CROP_OVERRIDES[nfc_id].get('height', img_h)
        else:
            target_h = get_auto_crop_height(raw_img)
        raw_img = raw_img.crop((0, 0, img_w, min(img_h, target_h)))
        cropped_h = raw_img.size[1]

        # 6. 캔버스 생성
        #    offset_y > 0: 이미지 상단에 여백 필요 → canvas 높이 확장
        #    offset_y < 0: 이미지 상단 공백 제거 → PIL이 자동 클리핑
        top_pad = max(0, offset_y)
        canvas_h = cropped_h + top_pad
        canvas = Image.new('RGB', (CANVAS_WIDTH, canvas_h), (255, 255, 255))
        canvas.paste(raw_img, (offset_x, offset_y))

        # 7. 번호 차폐: 첫 번째 행만 (전체 높이 strip 금지 — 2행 이후 잘림 방지)
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
    pdf_files = sorted([f for f in os.listdir(PDF_DIR) if f.endswith('.pdf')])
    total = len(pdf_files)
    print(f"=== 썸네일 v4 전체 생성 ({total}개) ===")
    print(f"앵커: 1자리={ANCHOR_X_1DIGIT}px, 2자리={ANCHOR_X_2DIGIT}px, y={ANCHOR_Y_TARGET}px\n")

    count = 0
    for i, f in enumerate(pdf_files):
        if process_thumbnail(f):
            count += 1
        if (i + 1) % 100 == 0:
            print(f"진행: {i+1}/{total} 완료...")

    print(f"\n완료! 생성된 썸네일: {count}/{total}")


if __name__ == "__main__":
    main()
