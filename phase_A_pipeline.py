import os
import glob
import re
import json
import requests
import time
import numpy as np
from pathlib import Path
from dotenv import load_dotenv

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ================= Configuration =================
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5-coder:14b"
EMBED_MODEL_NAME = 'dragonkue/BGE-m3-ko'
CACHE_DIR = '.build_cache/phase_A'
os.makedirs(CACHE_DIR, exist_ok=True)

CHUNK_CACHE_FILE = os.path.join(CACHE_DIR, 'raw_chunks_cache_v3_ollama.json')
PROPOSAL_OUTPUT_FILE = 'phaseA_refactor_proposals_final.json'

# 모델 로딩
print("임베딩 모델(BGE-M3) 탑재 중...")
embed_model = SentenceTransformer(EMBED_MODEL_NAME)
print("탑재 완료!")

# =================================================

def load_pilot_files(target_dir):
    return glob.glob(os.path.join(target_dir, '*.md'))

def extract_explanation_block(md_filepath):
    with open(md_filepath, 'r', encoding='utf-8') as f: content = f.read()
    pattern = re.compile(r'> \*\*📝 해설 \(Explanation\)\*\*\n+(.*?)(?=\n## \[Step|$)', re.DOTALL)
    matches = pattern.findall(content)
    pure_texts = []
    for match in matches:
        clean_text = "\n".join([line.lstrip(">").strip() for line in match.split("\n") if line.strip()])
        pure_texts.append(clean_text)
    return " ".join(pure_texts)

def call_ollama_json(prompt):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json"
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=300)
        response.raise_for_status()
        content = response.json()['message']['content']
        return json.loads(content)
    except Exception as e:
        print(f" [!] Ollama API 오류: {e}")
        return None

def soft_split_with_llm(full_explanation_text):
    prompt = f"""다음 수능 수학 문항의 해설 줄글을 '수학적 공식이나 필연적인 핵심 개념이 바뀌는 논리적 도약(Logical Leap)' 단위로 병합하여 구조화하라.
단순히 문장 단위로 자르지 마라! 방대한 계산 과정이나 식 대입은 하나의 '행동'으로 묶어야 한다.

각 논리 단위에 대하여 다음 스키마를 준수하는 JSON 객체를 작성하고, 반드시 'results'라는 키의 배열 안에 담아서 응답하라.
{{
  "results": [
    {{
      "step_number": 1,
      "logical_action": "이 단계를 관통하는 본질적인 수학 행동(예: 일차방정식을 이용한 미정계수 도출). 문항 변수명 배제.",
      "sub_calculations": ["세세한 덧셈 뺄셈이나 식 대입 문구", "계산 결과"],
      "is_core_jump": true (또는 false)
    }}
  ]
}}

[해석 가이드]
- logical_action: 해당 단계의 '목적'이 무엇인지를 명확히 기술.
- sub_calculations: 실제로 수행한 연산 식이나 대입 과정을 나열.

[해설 본문]
{full_explanation_text}"""
    
    res = call_ollama_json(prompt)
    if res and "results" in res:
        return res["results"]
    elif res and isinstance(res, list):
        return res
    return []

def load_or_build_chunks(files):
    # Checkpoint: 기존 캐시 로드
    if os.path.exists(CHUNK_CACHE_FILE):
        with open(CHUNK_CACHE_FILE, 'r', encoding='utf-8') as f:
            processed_data = json.load(f)
    else:
        processed_data = []

    processed_files = {item['file'] for item in processed_data if item.get('chunks')}
    
    newly_processed = 0
    print(f"\n[1] Chunking 단계 진입 (기 처리: {len(processed_files)}개 / 대상: {len(files)}개)")
    
    for idx, fpath in enumerate(files):
        if fpath in processed_files:
            continue  # 이미 한 건 건너뜀
            
        print(f"  - ({idx+1}/{len(files)}) {os.path.basename(fpath)} 처리 중... (Ollama)", flush=True)
        text = extract_explanation_block(fpath)
        if not text.strip(): continue
        
        chunks = soft_split_with_llm(text)
        if chunks:
            processed_data.append({"file": fpath, "chunks": chunks})
            newly_processed += 1
            
            # ⭐️ 1개 문항 끝날 때마다 즉시 저장 (Safety First)
            with open(CHUNK_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(processed_data, f, ensure_ascii=False, indent=2)
                
    if newly_processed > 0:
        print(f" ▷ 신규 Chunking {newly_processed}건 완료 및 저장됨.")
    else:
        print(" ▷ 모든 파일이 이미 캐시되어 있습니다. 다음 단계로 진행합니다.")
        
    return processed_data

def justify_and_select_concept_with_llm(logical_action, sub_calculations, candidates: list):
    cand_str = "\n".join([f"  - ID: {c['id']}, 명칭: {c['name']}" for c in candidates])
    subs_str = "\n".join([f"  * {s}" for s in sub_calculations])
    
    prompt = f"""다음은 학생에게 설명할 수능 해설의 핵심 논리 동작(Logical Action)과 부차적인 연산 내용(Sub-calculations)입니다:

[Logical Action]: "{logical_action}"
[Sub-calculations]: 
{subs_str}

지시사항:
우리의 목표는 이 해설 스텝이 성취기준 개념 풀(Pool) 중 어디에 가장 필연적으로 소속되는지 단 하나만 선택하는 것입니다.
아래는 벡터 검색으로 추천된 상위 3개의 교육과정 후보입니다:
{cand_str}

가장 논리적으로 부합하는 1개의 성취기준을 선택하세요.
반드시 아래 스키마를 가지는 단일 JSON 객체 형식으로만 응답하세요.
{{
  "id": "선택된후보ID 또는 NEW", 
  "name": "성취기준 명칭", 
  "justification": "선택한 수학교육학적 논리적 근거 (1-2문장)"
}}
"""
    res = call_ollama_json(prompt)
    if res and "id" in res: return res
    return {"id": candidates[0]['id'], "name": candidates[0]['name'], "justification": "로컬 파싱 실패 오류 캐구"} 

def build_base_dictionary():
    with open('concepts.json', 'r', encoding='utf-8') as f: data = json.load(f)
    full_dict = []
    for row in data:
        if row['id'].startswith('9수'): continue
        kws = " ".join(row.get('keywords', []))
        desc = row.get('standard_name', "")
        full_dict.append({"id": row['id'], "name": desc, "embed_text": f"{desc} {kws}"})
    return full_dict

def get_embeddings(texts):
    return embed_model.encode(texts, normalize_embeddings=True)

def main():
    print("="*55)
    print("🚀 Phase A (V3.1): Robust Local Batch Engine 🚀")
    print(f" ▶ 모델: {OLLAMA_MODEL} | 세이브포인트 지원")
    print("="*55)
    
    target_years = ["2014", "2015", "2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026", "2028"]
    all_files = []
    for year in target_years:
        all_files.extend(load_pilot_files(f"./Sol/{year}"))
    all_files.sort()
    
    files = all_files
    print(f"\n[START] 총 {len(files)}개 파일 배치를 시작합니다.")
    
    # 1. Chunking 단계 (이어 부르기 지원)
    file_chunks = load_or_build_chunks(files)
    
    # 2. 매핑 결과 로드 (Checkpoint 지원)
    if os.path.exists(PROPOSAL_OUTPUT_FILE):
        with open(PROPOSAL_OUTPUT_FILE, 'r', encoding='utf-8') as f:
            mapping_results = json.load(f)
    else:
        mapping_results = []

    # 이미 매핑 완료된 유니크 키 생성 (file + step)
    processed_mapping_keys = {f"{r['file']}_{r['step_number']}" for r in mapping_results if r.get('assigned_id')}

    # 3. 사전 및 임베딩 준비
    print("\n[사전 벡터 준비 중...]")
    full_dict = build_base_dictionary()
    dict_vecs = get_embeddings([d['embed_text'] for d in full_dict])
    
    # 4. 대상 필터링 (이미 매핑한 건 빼고)
    pending_chunks = []
    for fc in file_chunks:
        for ch in fc['chunks']:
            if not isinstance(ch, dict): continue
            if not ch.get('is_core_jump', True): continue
            
            key = f"{fc['file']}_{ch.get('step_number', 0)}"
            if key in processed_mapping_keys: continue
            
            pending_chunks.append({
                "file": fc['file'], 
                "step_number": ch.get('step_number', 0),
                "logical_action": ch.get('logical_action', ''),
                "sub_calculations": ch.get('sub_calculations', []),
                "assigned_id": None,
                "justification_log": None
            })
            
    print(f"\n[Two-Pass Mapping] 기 처리된 매핑 제외, 신규 대상: {len(pending_chunks)}개")
    if len(pending_chunks) == 0:
        print("🏁 모든 조각의 매핑이 이미 완료되었습니다!")
        return

    # 5. Mapping 시작 (순차 저장 모드)
    chunk_actions = [c['logical_action'] for c in pending_chunks]
    chunk_vecs = get_embeddings(chunk_actions)
    sim_scores = cosine_similarity(chunk_vecs, dict_vecs)
    
    for idx, chunk in enumerate(pending_chunks):
        top3_indices = np.argsort(sim_scores[idx])[-3:][::-1]
        candidates = [full_dict[i] for i in top3_indices]
        
        print(f"  > ({idx+1}/{len(pending_chunks)}) 검증 중: {os.path.basename(chunk['file'])} Step {chunk['step_number']}...", flush=True)
        res = justify_and_select_concept_with_llm(chunk['logical_action'], chunk['sub_calculations'], candidates)
        
        chunk['assigned_id'] = res.get('id', candidates[0]['id'])
        chunk['justification_log'] = res.get('justification', 'No log.')
        
        # ⭐️ 메인 결과 리스트에 추가 및 실시간 저장
        mapping_results.append(chunk)
        with open(PROPOSAL_OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(mapping_results, f, ensure_ascii=False, indent=2)
        
    print(f"\n🏁 모든 작업이 완료되었습니다! 최종 파일: {PROPOSAL_OUTPUT_FILE}")

if __name__ == "__main__":
    main()
