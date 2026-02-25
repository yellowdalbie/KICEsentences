import json
import re

MAPPING_FILE = 'trigger_mapping.json'

def normalize_triggers():
    with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    for item in data:
        text = item['trigger_text']
        normalized = ""

        # 0. 새 형식: 트리거 텍스트가 [카테고리명]으로 시작하면 그대로 추출
        # 콜론(:)이나 수식($)이 없는 순수 카테고리명만 추출 (구식 [문제 조건: ...] 형태 제외)
        bracket_match = re.match(r'^\[([^\]$:]+)\]', text.strip())
        if bracket_match:
            normalized = f"[{bracket_match.group(1)}]"

        # 1. 극한 기호 관련
        elif '미분계수의 정의' in text or r'\lim_{h' in text:
            normalized = "[특정 점에서의 미분계수 극한식]"
        elif r'\lim_{x \to' in text:
            normalized = "[특정 점에서의 극한값 기호]"
            
        # 2. 다항함수 식 제시
        elif '다항함수 $f(x)=' in text:
            normalized = "[다항함수 식 제시]"
        elif '두 다항식' in text and '함수' in text:
            normalized = "[두 다항식 곱 형태의 함수 제시]"
        elif '도함수의 식' in text:
            normalized = "[도함수의 식 제시]"
            
        # 3. 삼각함수 관련
        elif r'\cos(\theta' in text or r'\sin(\pi' in text or '각변환' in text or '각의 변환' in text:
            normalized = "[삼각함수의 각변환 조건]"
        elif r'\tan \theta < 0' in text or r'\sin \theta > 0' in text or '사분면' in text:
            normalized = "[삼각함수 부호 조건]"
        elif r'y=a \cos bx' in text:
            if '최댓값' in text:
                normalized = "[삼각함수 최댓값 조건]"
            elif '주기' in text:
                normalized = "[삼각함수 주기 조건]"
        elif '코사인 값' in text or '사인 값' in text or r'\cos(\angle' in text:
            normalized = "[특정 각의 삼각함수 값 제시]"
            
        # 4. 지수/로그 정리
        elif '거듭제곱근' in text:
            normalized = "[거듭제곱근 연산 제시]"
        elif '밑이 소수가 아닌' in text or '밑이 역수' in text:
            normalized = "[합성수/분수 밑의 거듭제곱 제시]"
        elif '밑이 같은 두' in text and '곱' in text:
            normalized = "[밑이 동일한 지수식의 곱]"
        elif r'\log_' in text and '=' in text and '과' in text:
            normalized = "[두 로그 방정식 제시]"
        elif '밑이 다른' in text and '로그 방' in text:
            normalized = "[밑이 다른 로그 방정식]"
        elif ('로그' in text) and ('합' in text or '곱' in text or '덧셈' in text):
            normalized = "[로그 식의 연산 조건]"
            
        # 5. 수열 관련
        elif r'\sum' in text and '다항식' in text:
            normalized = "[내부에 다항식이 포함된 시그마 기호식]"
        elif (r'\sum' in text or '시그마' in text) and ('안의 식이' in text or '연산이 포함된' in text or '시그마 식' in text):
            normalized = "[시그마 기호식 조건]"
        elif '귀납적 정의 식' in text or '점화식' in text:
            normalized = "[귀납적으로 정의된 수열의 점화식]"
        elif '등비수열' in text:
            normalized = "[등비수열의 조건식 제시]"
        elif '등차수열' in text:
            normalized = "[등차수열의 조건식 제시]"
            
        # 6. 미적분 기본
        elif '연속' in text and ('나뉘어 정의' in text or '다르게 정의' in text):
            normalized = "[구간별 분기된 연속 함수]"
        elif '접한다' in text or '접선의 방정식' in text:
            normalized = "[곡선과 직선의 접함 통과 조건]"
        elif '위의 한 점' in text:
            normalized = "[곡선 위의 한 점 제시]"
        elif '넓이 구하기' in text:
            normalized = "[두 곡선 사이 넓이 조건]"
        elif '적분 구간이' in text and ('동일한' in text or '같은' in text):
            normalized = "[적분 구간이 동일한 두 정적분식]"
        elif '정적분으로 정의된 함수' in text:
            normalized = "[정적분으로 정의된 함수 제시]"
        elif '부정적분' in text:
            normalized = "[함수의 부정적분 조건]"
        elif '정적분' in text and '구간' in text:
            normalized = "[다항함수의 정적분 조건]"
        elif '극대' in text or '극소' in text or '극값' in text or '극댓값' in text or '극솟값' in text:
            normalized = "[다항함수의 극값 조건]"
        elif '실근의 개수' in text:
            normalized = "[방정식의 실근 개수 조건]"
        elif '곱해진 형태의 함수' in text and '미분' in text:
            normalized = "[두 함수 곱 형태의 미분]"
        elif '부등식이 항상 성립' in text:
            normalized = "[특정 구간에서 부등식이 항상 성립할 조건]"
        elif '두 곡선' in text:
            normalized = "[두 곡선 위치 관계 조건]"
            
        # 7. Step Result 연계 (재귀적 조건)
        elif 'Step' in text and 'Result:' in text:
            if 'f\'(' in text and '식' not in text:
                normalized = "[미분계수 값 도출]"
            elif "f'(x)" in text or "g'(x)" in text:
                normalized = "[도함수 식 도출]"
            elif r'\cos' in text or r'\sin' in text:
                normalized = "[삼각함수 값 도출]"
            elif '적분 구간' in text:
                normalized = "[적분 구간 도출]"
            elif 'a, b 값' in text or '미지수' in text:
                normalized = "[미지수 쌍 도출]"
            else:
                normalized = "[이전 단계 연산 결과]"
                
        # 8. 기타 문제 조건
        elif '구하고자 하는 값' in text or '구하는 값' in text or '구해야 하는 값' in text or '구하고자 하는 식' in text or '구하고자 하는 함숫값' in text:
            normalized = "[최종 구하는 값]"
        elif '구간 양 끝점' in text or '양 끝점' in text:
            normalized = "[구간 경계점 조사]"
        elif '원점 출발' in text or '출발' in text:
            normalized = "[운동 방향 전환 조건]"
        elif '위치' in text and ('$x(' in text or 'x(t' in text):
            normalized = "[추가 관계식 조건]"
        elif '함수 $f(x)$ 식' in text or '함수의 식' in text:
            normalized = "[다항함수 식 제시]"
        elif '아래끝이 같은' in text or '아래끝이 동일한' in text:
            normalized = "[적분 구간이 동일한 두 정적분식]"
        elif '극댓값' in text and '조건' in text:
            normalized = "[다항함수의 극값 조건]"
        elif '문제 조건:' in text or '조건:' in text or '제약 조건:' in text or '제약' in text:
            if '대입' in text or '함숫값' in text or 'f(' in text:
                normalized = "[특정 x값 대입 조건]"
            elif '구하고자 하는 값' in text or '구하는 값' in text:
                normalized = "[최종 구하는 값]"
            else:
                normalized = "[추가 관계식 조건]"

        if not normalized:
            normalized = "[미분류 기타 조건]" # Fallback
            
        item['normalized_text'] = normalized

    with open(MAPPING_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    print(f"Update complete. Check {MAPPING_FILE}")

if __name__ == '__main__':
    normalize_triggers()
