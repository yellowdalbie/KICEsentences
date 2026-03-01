# Auto-Crop Tool (Content-Aware)

이 도구는 수학 문제나 텍스트 위주의 이미지에서 본문이 끝나는 지점을 정밀하게 찾아내어 하단 여백을 자동으로 잘라주는 알고리즘을 담고 있습니다.

## 알고리즘 특징 (Backward-Recursive Search)

1. **성긴 탐색 (Coarse Scan)**: 200px 단위로 빠르게 점프하며 대략적인 여백 구간을 찾습니다.
2. **다단계 내부 검증 (Multi-Tiered Probing)**: 발견된 200px 구간 사이사이를 100px, 50px, 25px 단위로 촘촘하게 검사하여 "진짜 여백"인지 확인합니다.
3. **역방향 재귀 검색 (Backward Recursive Search)**: 여백이 확정되면, 해당 구간 시작점부터 거슬러 올라가며 25px 단위로 "마지막 콘텐츠"가 있는 정확한 경계선을 찾습니다.
4. **엄격한 픽셀 감지**: 단순히 평균 밝기를 보지 않고, 단 하나의 픽셀이라도 임계값(Threshold) 미만이면 콘텐츠로 간주하여 데이터 손실을 방지합니다.

## 사용 방법

```python
from PIL import Image
import numpy as np
from auto_crop_module import get_auto_crop_height

# 이미지 로드
img = Image.open("your_image.png")
img_array = np.array(img)

# 최적의 크롭 높이 계산
target_h = get_auto_crop_height(img_array, white_threshold=250, buffer=50)

# 크롭 적용
cropped_img = img.crop((0, 0, img.width, target_h))
cropped_img.save("result.png")
```

## 주요 설정

- `white_threshold`: 흰색으로 간주할 최소 밝기 (기본값: 250)
- `buffer`: 본문 끝지점 다음에 남겨둘 여유 공간 (기본값: 50px)
