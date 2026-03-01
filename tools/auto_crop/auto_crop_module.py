import numpy as np

def get_auto_crop_height(img_array, white_threshold=250, buffer=50):
    """
    High-precision content-aware auto-crop algorithm.
    
    Logic:
    1. Coarse scan @ 200px intervals top-down.
    2. Identify potential gaps where two consecutive intervals are white.
    3. Multi-tiered internal probing (100px, 50px, 25px resolution).
    4. Backward recursive search from the gap start to find the exact content boundary.
    
    Args:
        img_array (np.ndarray): Image data as a numpy array (H, W, C).
        white_threshold (int): Pixel values >= this are considered white.
        buffer (int): Padding to add after the last detected content.
        
    Returns:
        int: The recommended crop height (Y coordinate).
    """
    img_h, img_w, _ = img_array.shape
    
    def is_row_white(y):
        if y >= img_h: return True
        if y < 0: return True
        row = img_array[int(y), :, :3]
        # Strict content detection: Any pixel below threshold is content.
        return not np.any(np.all(row < white_threshold, axis=1))

    y_current = 200
    prev_y = 0
    final_cut_y = img_h
    found_gap = False

    while y_current < img_h:
        res_current = is_row_white(y_current)
        res_prev = is_row_white(prev_y)
        
        if res_current and res_prev:
            # Multi-tiered internal probing
            m = y_current - 100
            q = [y_current - 150, y_current - 50]
            e = [y_current - 175, y_current - 125, y_current - 75, y_current - 25]
            
            all_internal_white = True
            for cy in [m] + q + e:
                if not is_row_white(cy):
                    all_internal_white = False
                    break
            
            if all_internal_white:
                # GAP CONFIRMED. Now search backwards for the exact boundary.
                search_y = prev_y - 25
                last_content_found = 0
                while search_y >= 0:
                    if not is_row_white(search_y):
                        last_content_found = search_y
                        break
                    search_y -= 25
                
                final_cut_y = last_content_found + buffer
                found_gap = True
                break
        
        prev_y = y_current
        y_current += 200

    return final_cut_y
