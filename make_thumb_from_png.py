#!/usr/bin/env python3
"""
PNG 소스로부터 v4 규격 썸네일 생성 유틸리티
=============================================
원본 PDF가 손상/불완전하여 PNG 캡처본으로 대체해야 할 때 사용.

사용법:
  1. 아래 설정값(PROBLEM_ID, SRC_PNG, PERIOD_RIGHT_X, PERIOD_TOP_Y) 수정
  2. python3 make_thumb_from_png.py

좌표 기준:
  - PERIOD_RIGHT_X, PERIOD_TOP_Y : 1400px 기준으로 확대된 이미지에서 마침표(.)의
    오른쪽 끝 x좌표, 상단 y좌표.
  - 값을 모를 경우 브라우저에서 결과 확인하며 조정 (처음엔 50~130 범위에서 시작).
"""

import unicodedata
from PIL import Image, ImageDraw

# ── 사용자 설정 ──────────────────────────────────────────
PROBLEM_ID     = '2018수능나_05'   # 저장될 썸네일 파일명 (확장자 제외)
SRC_PNG        = '2018수능나_05.png'  # 원본 PNG 경로 (프로젝트 루트 기준)
PERIOD_RIGHT_X = 50    # 마침표 오른쪽 끝 x (1400px 기준)
PERIOD_TOP_Y   = 88    # 마침표 상단 y (1400px 기준)
# ────────────────────────────────────────────────────────

# v4 고정 상수
CANVAS_WIDTH     = 1400
ANCHOR_X_1DIGIT  = 2
ANCHOR_X_2DIGIT  = 29
ANCHOR_Y_TARGET  = 90
MASK_LINE_HEIGHT = 8
THUMBNAIL_DIR    = 'static/thumbnails'


def main():
    import os
    nfc_id     = unicodedata.normalize('NFC', PROBLEM_ID)
    thumb_path = os.path.join(THUMBNAIL_DIR, f'{nfc_id}.png')

    # 1자리/2자리 자동 판별
    import re
    m = re.search(r'_\D*(\d+)$', PROBLEM_ID)
    num = str(int(m.group(1))) if m else '1'
    anchor_x = ANCHOR_X_2DIGIT if len(num) >= 2 else ANCHOR_X_1DIGIT

    # RGBA → RGB (흰 배경 합성)
    src = Image.open(SRC_PNG).convert('RGBA')
    bg  = Image.new('RGBA', src.size, (255, 255, 255, 255))
    bg.paste(src, mask=src.split()[3])
    raw_img = bg.convert('RGB')

    # 1400px 기준 비례 확대
    src_w, src_h = raw_img.size
    raw_img = raw_img.resize(
        (CANVAS_WIDTH, int(src_h * CANVAS_WIDTH / src_w)),
        Image.LANCZOS
    )

    # 오프셋 계산
    offset_x = anchor_x - PERIOD_RIGHT_X
    offset_y = ANCHOR_Y_TARGET - PERIOD_TOP_Y

    # 캔버스 생성 및 붙여넣기
    top_pad  = max(0, offset_y)
    canvas_h = raw_img.size[1] + top_pad
    canvas   = Image.new('RGB', (CANVAS_WIDTH, canvas_h), (255, 255, 255))
    canvas.paste(raw_img, (offset_x, offset_y))

    # 번호 차폐
    mask_right  = anchor_x + 2
    mask_bottom = ANCHOR_Y_TARGET + MASK_LINE_HEIGHT
    ImageDraw.Draw(canvas).rectangle(
        [0, 0, mask_right, mask_bottom], fill=(255, 255, 255)
    )

    canvas.save(thumb_path, 'PNG', optimize=True)
    print(f'저장 완료: {thumb_path}')
    print(f'  num={num} ({"2" if len(num)>=2 else "1"}자리)  anchor_x={anchor_x}')
    print(f'  period=({PERIOD_RIGHT_X},{PERIOD_TOP_Y})  offset=({offset_x},{offset_y})')
    print(f'  마스크=[0,0,{mask_right},{mask_bottom}]  캔버스:{canvas.size}')


if __name__ == '__main__':
    main()
