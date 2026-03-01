import os
import re
import unicodedata
import pypdfium2 as pdfium
from PIL import Image
import numpy as np

# --- CONFIGURATION ---
PDF_DIR = 'PDF_Ref'
THUMBNAIL_DIR = os.path.join('static', 'thumbnails')
SCALE = 4.2           # Roughly 300 DPI
CANVAS_WIDTH = 1400   # Target fixed width
ANCHOR_X_TARGET = 80 # Period (.) aligned here
WHITE_THRESHOLD = 250 # Pixels > 250 are considered "white"

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
    """Extracts the question number from filename (e.g., '2026.6모_16' -> '16')."""
    match = re.search(r'_([가나\w]+)?(\d+)$', problem_id)
    return match.group(2) if match else None

def get_anchor_point(page, problem_num):
    """Finds the x-coordinate of the period (.) after the question number."""
    if not problem_num:
        return None
    
    tp = page.get_textpage()
    page_width, page_height = page.get_size()
    target = f"{problem_num}."
    search = tp.search(target)
    
    occ = search.get_next()
    while occ:
        index, count = occ
        # We want the right side of the '.' which is the last character in the match
        charbox = tp.get_charbox(index + count - 1)
        # Filter: Only accept periods in the left 1/3 of the page
        if charbox[0] < (page_width / 3):
            return charbox[2] # 'right' coordinate
        occ = search.get_next()
                
    return None

def get_auto_crop_height(img):
    """
    Finalized Auto-Crop Algorithm:
    1. Coarse scan starting from Y=200, step 200.
    2. If Y and Y-200 are white, perform multi-tiered internal probing.
    3. If gap is confirmed, search backwards from Y-200 in 25px steps until content is hit.
    """
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
            # Multi-tiered internal probing (100, 50, 25 tiers)
            m = y_current - 100
            q = [y_current - 150, y_current - 50]
            e = [y_current - 175, y_current - 125, y_current - 75, y_current - 25]
            
            all_internal_white = True
            for cy in [m] + q + e:
                if not is_row_white(cy):
                    all_internal_white = False
                    break
            
            if all_internal_white:
                # GAP CONFIRMED. Now search backwards to find the exact start of the gap.
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

def process_thumbnail(filename):
    problem_id = filename.replace('.pdf', '')
    pdf_path = os.path.join(PDF_DIR, filename)
    nfc_id = unicodedata.normalize('NFC', problem_id)
    thumb_path = os.path.join(THUMBNAIL_DIR, f'{nfc_id}.png')
    
    try:
        pdf = pdfium.PdfDocument(pdf_path)
        page = pdf[0]
        page_width, page_height = page.get_size()
        
        # 1. Detect Anchor
        num = get_problem_number(problem_id)
        anchor_x_pdf = get_anchor_point(page, num)
        
        # 2. Render Page (Full Height baseline)
        bitmap = page.render(scale=SCALE)
        raw_img = bitmap.to_pil()
        img_w, img_h = raw_img.size
        
        # 3. Apply Overrides or Auto-Crop
        if nfc_id in CROP_OVERRIDES:
            overrides = CROP_OVERRIDES[nfc_id]
            if 'height' in overrides:
                target_h = overrides['height']
                raw_img = raw_img.crop((0, 0, img_w, min(img_h, target_h)))
        else:
            # Apply the new Auto-Crop algorithm for un-coached items
            target_h = get_auto_crop_height(raw_img)
            raw_img = raw_img.crop((0, 0, img_w, min(img_h, target_h)))
            
        img_h = raw_img.size[1]

        # 4. Canvas Padding & Alignment
        # We keep the original height from the render
        canvas = Image.new('RGB', (CANVAS_WIDTH, img_h), (255, 255, 255))
        
        if anchor_x_pdf is not None:
            anchor_x_px = int(anchor_x_pdf * SCALE)
            offset_x = ANCHOR_X_TARGET - anchor_x_px
            canvas.paste(raw_img, (offset_x, 0))
        else:
            canvas.paste(raw_img, (0, 0)) # Fallback if anchor not found
            
        canvas.save(thumb_path, 'PNG', optimize=True)
        pdf.close()
        return True
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return False

def main():
    pdf_files = sorted([f for f in os.listdir(PDF_DIR) if f.endswith('.pdf')])
    
    total = len(pdf_files)
    print(f"Starting Universal Anchor-Aligned Generation for {total} files (Anchor: {ANCHOR_X_TARGET}px)...")
    
    count = 0
    for i, f in enumerate(pdf_files):
        if process_thumbnail(f):
            count += 1
        if (i + 1) % 100 == 0:
            print(f"Progress: {i+1}/{total} completed...")

    print(f"Finished! Total thumbnails created: {count}")

if __name__ == "__main__":
    main()
