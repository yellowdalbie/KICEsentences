import os
import re
import unicodedata
import pypdfium2 as pdfium
from PIL import Image

# --- CONFIGURATION ---
PDF_DIR = 'PDF_Ref'
THUMBNAIL_DIR = os.path.join('static', 'thumbnails')
SCALE = 4.2           # Roughly 300 DPI
CANVAS_WIDTH = 1400   # Target fixed width for printing
ANCHOR_X_TARGET = 40  # Period (.) will be moved to this x-coordinate

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
    target = f"{problem_num}."
    search = tp.search(target)
    
    # search.get_next() returns (index, count) tuple
    occ = search.get_next()
    
    if occ:
        index, count = occ
        page_width, page_height = page.get_size()
        
        # Check rectangles for this occurrence
        for i in range(count):
            try:
                rect = tp.get_rect(index + i)
                # Filter: Only accept periods in the left 1/3 of the page
                if rect[0] < (page_width / 3):
                    # We want the right side of the '.' which usually comes at the end of the match
                    last_rect = tp.get_rect(index + count - 1)
                    return last_rect[2] 
            except:
                pass
                
    return None

def should_crop_top(problem_id):
    """Logic to remove the 'Short-Answer' box from specific problems."""
    match = re.match(r'^(\d{4})', problem_id)
    if "2028.예시" in problem_id and "_22" in problem_id:
        return True
    if match:
        year = int(match.group(1))
        if year >= 2022:
            return "_16" in problem_id
        else:
            return "_22" in problem_id
    return False

def process_thumbnail(filename):
    problem_id = filename.replace('.pdf', '')
    pdf_path = os.path.join(PDF_DIR, filename)
    # Output path with NFC normalization
    nfc_id = unicodedata.normalize('NFC', problem_id)
    thumb_path = os.path.join(THUMBNAIL_DIR, f'{nfc_id}.png')
    
    try:
        pdf = pdfium.PdfDocument(pdf_path)
        page = pdf[0]
        page_width, page_height = page.get_size()
        
        # 1. Detect Anchor
        num = get_problem_number(problem_id)
        anchor_x_pdf = get_anchor_point(page, num)
        
        # 2. Render Page
        bitmap = page.render(scale=SCALE)
        raw_img = bitmap.to_pil()
        width, height = raw_img.size
        
        # 3. Apply Top Crop if needed (Safe version)
        if should_crop_top(problem_id):
            crop_y = int(145)
            # Only crop if the image is tall enough to avoid 'lower < upper' error
            if height > (crop_y + 10):
                raw_img = raw_img.crop((0, crop_y, width, height))
                width, height = raw_img.size

        # 4. Canvas Padding & Alignment
        canvas = Image.new('RGB', (CANVAS_WIDTH, height), (255, 255, 255))
        
        if anchor_x_pdf is not None:
            anchor_x_px = int(anchor_x_pdf * (width / page_width))
            offset_x = ANCHOR_X_TARGET - anchor_x_px
            canvas.paste(raw_img, (offset_x, 0))
        else:
            canvas.paste(raw_img, (0, 0))
            
        canvas.save(thumb_path, 'PNG', optimize=True)
        pdf.close()
        return True
    except Exception as e:
        print(f"Error processing {filename}: {e}")
        return False

def main():
    pdf_files = [f for f in os.listdir(PDF_DIR) if f.endswith('.pdf')]
    total = len(pdf_files)
    print(f"Starting production-grade generation for {total} files...")
    
    count = 0
    for i, f in enumerate(pdf_files):
        # We process all files again to be sure, or we could check if exists.
        # Given the previous errors, a full clean run is safer.
        if process_thumbnail(f):
            count += 1
        if (i + 1) % 100 == 0:
            print(f"[{i+1}/{total}] Completed...")

    print(f"Finished! Total thumbnails created: {count}")

if __name__ == "__main__":
    main()
