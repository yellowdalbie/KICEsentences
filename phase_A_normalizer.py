"""
Phase A V4: Canonical Normalizer
목적: 기존 raw_chunks_cache를 input으로 받아 canonical_name으로 정제하는 스크립트
버전: v0.1 (2026-04-10) - 점진적 개선 예정
"""

import os
import json
import re
import requests
import time
from pathlib import Path

# ============ Config ============
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5-coder:14b"

RAW_CHUNKS_FILE = '.build_cache/phase_A/raw_chunks_cache_v3_ollama.json'
CONCEPTS_FILE = 'concepts.json'
VOCAB_OUTPUT_FILE = '.build_cache/phase_A/canonical_patterns.json'
VISION_FLAG_FILE = '.build_cache/phase_A/vision_required_list.json'
RESULT_FILE = 'phaseA_canonical_proposals.json'
CACHE_DIR = '.build_cache/phase_A'
os.makedirs(CACHE_DIR, exist_ok=True)

# 그래프 관찰이 필수적인 문항 감지용 키워드 (텍스트만으로 해결 불가한 유형)
VISION_REQUIRED_KEYWORDS = ['그래프에서', '그래프를 보고', '그래프에 의해', '그래프 관찰']

# ============ 교육과정 표준 용어 사전 로드 ============
def build_standard_vocab():
    """concepts.json에서 교육과정 공식 용어만 추출 (고등학교 과목만)"""
    with open(CONCEPTS_FILE, 'r') as f:
        concepts = json.load(f)
    
    vocab = {}
    for row in concepts:
        cid = row['id']
        if cid.startswith('9수'): continue
        name = row.get('standard_name', '')
        kws = [kw for kw in row.get('keywords', []) if isinstance(kw, str) and len(kw) > 1]
        vocab[cid] = {
            'name': name,
            'keywords': kws,
            'embed_text': f"{name} {' '.join(kws)}"
        }
    return vocab

# ============ Canonical Patterns 사전 (성장하는 사전) ============
def load_canonical_patterns():
    if os.path.exists(VOCAB_OUTPUT_FILE):
        with open(VOCAB_OUTPUT_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_canonical_patterns(patterns):
    with open(VOCAB_OUTPUT_FILE, 'w') as f:
        json.dump(patterns, f, ensure_ascii=False, indent=2)

# ============ Ollama 호출 ============
def call_ollama_json(prompt):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json"
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        content = response.json()['message']['content']
        return json.loads(content)
    except Exception as e:
        print(f"  [!] Ollama 오류: {e}")
        return None

# ============ 핵심 함수: Canonical Normalizer ============
def normalize_canonical(raw_action, sub_calcs, concept_vocab, existing_patterns):
    """
    raw_action → canonical_name으로 정제
    - 교육과정 표준 용어 우선 사용
    - 기존 canonical_patterns 사전 재사용
    - 문항 고유 변수/숫자 제거
    """
    # 기존 패턴 사전에서 유사한 것 Top-3 추출 (키워드 기반 단순 매칭)
    similar_patterns = []
    for pattern_key, pattern_data in existing_patterns.items():
        for kw in pattern_data.get('keywords', []):
            if kw in raw_action:
                similar_patterns.append({
                    'canonical_name': pattern_key,
                    'count': pattern_data.get('count', 1)
                })
                break
    similar_patterns = sorted(similar_patterns, key=lambda x: -x['count'])[:3]
    
    similar_str = ""
    if similar_patterns:
        similar_str = "\n기존 패턴 사전에 유사한 것이 있으면 아래 중 하나를 그대로 반환하라:\n"
        for p in similar_patterns:
            similar_str += f"  - \"{p['canonical_name']}\" (사용횟수: {p['count']})\n"
    
    sub_str = "\n".join([f"  - {s}" for s in sub_calcs[:3]])
    
    prompt = f"""너는 한국 수학 교육과정 전문가다. 다음 수능 수학 해설의 수학적 행동을 '표준 패턴명'으로 정제하라.

[원본 행동]: "{raw_action}"
[부가 연산 내역]:
{sub_str}

[필수 규칙]
1. 형식: "[수학적 개념명]을 이용하여 [결과물]을 [구하기/판정하기/도출하기]"
2. 아래 교육과정 공식 용어만 핵심 개념명으로 사용: 
   지수법칙, 로그의 성질, 합성함수, 역함수, 극한, 연속, 미분계수, 도함수, 접선의 방정식,
   극값, 부정적분, 정적분, 미적분학의 기본 정리, 등차수열, 등비수열, 점화식, 시그마(∑),
   경우의 수, 조건부확률, 이항정리, 이항분포, 정규분포, 표본평균의 분포,
   근과 계수의 관계, 인수분해, 인수 정리, 사인법칙, 코사인법칙, 충분조건/필요조건
3. 절대 포함 금지: 변수명($a$, $f(x)$, $n$), 구체적 숫자(3, 55다), 보기번호(ㄱ, ①)
4. '계산', '단순화', '파악', '도출' 같은 비전문 동사 사용 금지
{similar_str}
오직 아래 JSON 하나만 반환하라:
{{"canonical_name": "정제된 표준 패턴명 (한국어, 한 문장)"}}"""

    res = call_ollama_json(prompt)
    if res and 'canonical_name' in res:
        return res['canonical_name'].strip()
    # 실패 시 단순 수동 정제 시도
    clean = re.sub(r'\$[^$]+\$', '', raw_action)  # 수식 제거
    clean = re.sub(r'[0-9]+(번|개|회)', '', clean).strip()  # 숫자 제거
    return clean[:50] + "..." if len(clean) > 50 else clean

# ============ Vision 필요 여부 감지 ============
def detect_vision_required(file_path, chunks):
    """그래프 관찰이 필수적인 문항인지 감지"""
    for c in chunks:
        action = c.get('logical_action', '')
        subs = ' '.join(c.get('sub_calculations', []))
        full_text = action + ' ' + subs
        if any(kw in full_text for kw in VISION_REQUIRED_KEYWORDS):
            return True
    return False

# ============ 메인 ============
def main():
    print("=" * 55)
    print("🔬 Phase A V4: Canonical Normalizer (Option A - 캐시 활용)")
    print(f"   모델: {OLLAMA_MODEL}")
    print("=" * 55)
    
    # 1. 기존 raw_chunks 로드
    print(f"\n[1] 기존 raw_chunks 로드: {RAW_CHUNKS_FILE}")
    with open(RAW_CHUNKS_FILE, 'r') as f:
        raw_data = json.load(f)
    print(f"    총 {len(raw_data)}개 파일, 청크 처리 대상 확인 중...")
    
    total_chunks = sum(
        len([c for c in item.get('chunks', []) if isinstance(c, dict) and c.get('is_core_jump')])
        for item in raw_data
    )
    print(f"    is_core_jump=True 청크 합계: {total_chunks}개")
    
    # 2. 교육과정 표준 용어 로드
    print(f"\n[2] 교육과정 표준 용어 로드...")
    concept_vocab = build_standard_vocab()
    print(f"    고등학교 성취기준 {len(concept_vocab)}개 로드 완료")
    
    # 3. 기존 canonical 패턴 사전 로드 (성장하는 사전)
    canonical_patterns = load_canonical_patterns()
    print(f"\n[3] Canonical 패턴 사전: 현재 {len(canonical_patterns)}개 등록됨")
    
    # 4. 기존 결과 로드 (이어부르기)
    if os.path.exists(RESULT_FILE):
        with open(RESULT_FILE, 'r') as f:
            existing_results = json.load(f)
    else:
        existing_results = []
    
    processed_keys = {f"{r['file']}_{r['step_number']}" for r in existing_results}
    print(f"    기 처리된 스텝: {len(processed_keys)}개 (이어서 시작)")
    
    # 5. Vision 체크리스트
    vision_list = []
    if os.path.exists(VISION_FLAG_FILE):
        with open(VISION_FLAG_FILE, 'r') as f:
            vision_list = json.load(f)
    vision_files = {v['file'] for v in vision_list}
    
    # 6. 정제 루프
    print(f"\n[4] Canonical Normalization 시작 ---")
    new_count = 0
    
    for file_idx, item in enumerate(raw_data):
        fpath = item.get('file', '')
        chunks = item.get('chunks', [])
        if not chunks: continue
        
        # Vision 체크 (파일 단위)
        if fpath not in vision_files and detect_vision_required(fpath, chunks):
            vision_list.append({'file': fpath, 'reason': 'graph_observation_keyword'})
            vision_files.add(fpath)
            print(f"  📸 Vision 목록 추가: {os.path.basename(fpath)}")
        
        for chunk in chunks:
            if not isinstance(chunk, dict): continue
            if not chunk.get('is_core_jump'): continue
            
            step_key = f"{fpath}_{chunk.get('step_number', 0)}"
            if step_key in processed_keys: continue
            
            raw_action = chunk.get('logical_action', '')
            sub_calcs = chunk.get('sub_calculations', [])
            
            print(f"  > ({file_idx+1}/{len(raw_data)}) {os.path.basename(fpath)} Step {chunk.get('step_number')} 정제 중...", flush=True)
            
            # Canonical Name 생성
            canonical = normalize_canonical(raw_action, sub_calcs, concept_vocab, canonical_patterns)
            
            # 패턴 사전 업데이트 (사용 횟수 누적)
            if canonical not in canonical_patterns:
                # 패턴에서 핵심어 추출 (간단한 방법)
                kws = [w for w in canonical.split() if len(w) > 2 and w not in ['이용하여', '통해서', '구하기', '판정하기', '도출하기']]
                canonical_patterns[canonical] = {'count': 1, 'keywords': kws}
            else:
                canonical_patterns[canonical]['count'] += 1
            
            result_entry = {
                'file': fpath,
                'step_number': chunk.get('step_number', 0),
                'raw_logical_action': raw_action,
                'canonical_name': canonical,
                'sub_calculations': sub_calcs,
                'assigned_id': None,   # Two-Pass Mapping은 다음 단계에서
                'justification': None
            }
            
            existing_results.append(result_entry)
            processed_keys.add(step_key)
            new_count += 1
            
            # 실시간 저장 (세이브포인트)
            if new_count % 5 == 0:
                with open(RESULT_FILE, 'w') as f:
                    json.dump(existing_results, f, ensure_ascii=False, indent=2)
                save_canonical_patterns(canonical_patterns)
                with open(VISION_FLAG_FILE, 'w') as f:
                    json.dump(vision_list, f, ensure_ascii=False, indent=2)
    
    # 최종 저장
    with open(RESULT_FILE, 'w') as f:
        json.dump(existing_results, f, ensure_ascii=False, indent=2)
    save_canonical_patterns(canonical_patterns)
    with open(VISION_FLAG_FILE, 'w') as f:
        json.dump(vision_list, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*55}")
    print(f"✅ Canonical Normalization 1차 완료!")
    print(f"   신규 정제: {new_count}개 | 총 누적: {len(existing_results)}개")
    print(f"   패턴 사전: {len(canonical_patterns)}개 등록됨")
    print(f"   Vision 필요 목록: {len(vision_list)}개 격리됨")
    print(f"   결과 파일: {RESULT_FILE}")
    print(f"\n💡 다음 단계: Two-Pass Concept Mapping (phase_A_mapper.py)")

if __name__ == "__main__":
    main()
