"""
Phase A V3 - Two-Pass Justification 독립 테스트 스크립트
V2 캐시(raw_chunks_cache_v2.json)에서 2018.6모나_06.md 청크를 읽어,
V3의 핵심 기능 2가지를 모의(Mock) 테스트함:
  [1] 파편화된 V2 청크를 logical_action 단위로 재묶기 (Manual Merge 시뮬레이션)
  [2] justify_and_select_concept_with_llm 함수 실제 LLM 호출 검증
"""

import os
import json
import time
import numpy as np
from dotenv import load_dotenv

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("google-genai 라이브러리 없음."); exit(1)

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)
FLASH_MODEL = 'gemini-2.5-flash'
embed_model = SentenceTransformer('dragonkue/BGE-m3-ko')

# ─────────────────────────────────────────────
# [1단계] V2 캐시를 읽어 Manual Merge 수행
#   V2는 잘게 쪼개진 문장 파편. V3 로직에서는
#   "논리적으로 연관된 스텝을 묶을 것"을 LLM에 지시했음.
#   여기서는 수동으로 V2 청크를 그룹핑하여 V3 논리 구조를 시뮬레이션함.
# ─────────────────────────────────────────────

print("=" * 55)
print("Phase A V3 - Two-Pass Justification 독립 테스트")
print("=" * 55)

with open('.build_cache/phase_A/raw_chunks_cache_v2.json', 'r', encoding='utf-8') as f:
    cache = json.load(f)

# 2018.6모나_06.md 청크만 추출 (is_trivial=False인 것만)
raw_chunks = [
    ch for fc in cache if '2018.6모나_06' in fc['file']
    for ch in fc['chunks'] if not ch.get('is_trivial', False)
]

print(f"\n[V2 원본 파편 {len(raw_chunks)}개]")
for i, c in enumerate(raw_chunks):
    print(f"  {i+1}. {c['core_action']}")

# ─────────────────────────────────────────────────────────
# V3 논리 병합 시뮬레이션 (Manual Merge):
# 실제 V3 파이프라인에서는 LLM이 이 병합을 직접 수행.
# 여기서는 교육학적 판단으로 수동으로 묶어,
# Two-Pass LLM이 무엇을 검증하는지 검증 가능하게 만듦.
#
# 묶음 기준:
#  - [명제 포함관계 그룹] 필요조건 정의+의미해석 → 1 Logical Leap
#  - [미정계수 도출 그룹] x값 찾기+대입+수식작성+a값계산 → 1 Logical Leap
# ─────────────────────────────────────────────────────────

merged_steps = [
    {
        "step_number": 1,
        "logical_action": "명제의 포함관계를 이용한 필요충분조건 판별",
        "sub_calculations": [
            "조건 p가 q이기 위한 필요조건 ← 명제 q→p가 참",
            "조건 q를 만족하는 모든 x가 조건 p도 만족해야 함"
        ]
    },
    {
        "step_number": 2,
        "logical_action": "방정식의 해를 대입하여 미정계수 도출",
        "sub_calculations": [
            "조건 q: x - 3 = 0 이므로 x = 3",
            "x = 3을 x^2 + 2x - a = 0 에 대입",
            "9 + 6 - a = 0 → a = 15"
        ]
    }
]

print(f"\n[V3 Logical Leap 병합 결과: {len(merged_steps)}개]")
for s in merged_steps:
    print(f"  Step {s['step_number']}: {s['logical_action']}")
    for sub in s['sub_calculations']:
        print(f"    └ {sub}")

# ─────────────────────────────────────────────
# [2단계] 개념 사전 로드 및 벡터 Top-3 추출
# ─────────────────────────────────────────────

with open('concepts.json', 'r', encoding='utf-8') as f:
    concepts_raw = json.load(f)

full_dict = [
    {
        "id": r['id'],
        "name": r.get('standard_name', ''),
        "embed_text": r.get('standard_name', '') + " " + " ".join(r.get('keywords', []))
    }
    for r in concepts_raw if not r['id'].startswith('9수')
]

dict_vecs = embed_model.encode([d['embed_text'] for d in full_dict], normalize_embeddings=True)

# ─────────────────────────────────────────────
# [3단계] Two-Pass LLM Justification 실행
# ─────────────────────────────────────────────

def justify_and_select(logical_action, sub_calculations, candidates):
    cand_str = "\n".join([f"  - ID: {c['id']}, 명칭: {c['name']}" for c in candidates])
    subs_str = "\n".join([f"  * {s}" for s in sub_calculations])
    prompt = f"""다음은 수능 수학 해설에서 추출한 핵심 논리 동작과 부차 연산 내용입니다.

[Logical Action]: "{logical_action}"
[Sub-calculations]:
{subs_str}

아래는 벡터 검색으로 추천된 상위 3개의 고등학교 수학 교육과정 성취기준 후보입니다:
{cand_str}

지시사항:
1. 위 후보 중 Logical Action과 수학교육학적으로 가장 완벽하게 부합하는 1개를 선택하세요.
2. 가급적 '12대수', '12미적', '12확통' 핵심 과목을 최우선으로 선택하고, 어쩔 수 없을 때만 '10공수'에 매핑하세요.
3. 3개 모두 맞지 않으면 id에 "NEW"를 적고 name에 새로운 명칭을 작성하세요.
4. 선택 이유(justification)를 1~2문장으로 서술하세요.

반드시 아래 JSON 포맷만 반환하세요:
{{"id": "ID", "name": "명칭", "justification": "선택 근거"}}"""
    try:
        resp = client.models.generate_content(
            model=FLASH_MODEL, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(resp.text)
    except Exception as e:
        print(f"  LLM 오류: {e}")
        return {"id": candidates[0]['id'], "name": candidates[0]['name'], "justification": "API 오류"}

print("\n[Two-Pass LLM Justification 실행] -------------------")
results = []
for step in merged_steps:
    action_vec = embed_model.encode([step['logical_action']], normalize_embeddings=True)
    sims = cosine_similarity(action_vec, dict_vecs)[0]
    top3_idx = np.argsort(sims)[-3:][::-1]
    top3 = [full_dict[i] for i in top3_idx]

    print(f"\n  ▶ Step {step['step_number']}: '{step['logical_action']}'")
    print(f"    벡터 Top-3 후보:")
    for c in top3:
        print(f"      - {c['id']}: {c['name']}")

    res = justify_and_select(step['logical_action'], step['sub_calculations'], top3)
    print(f"    ✅ LLM 최종 선택 → {res['id']}")
    print(f"    📝 근거: {res['justification']}")

    results.append({
        "step_number": step['step_number'],
        "logical_action": step['logical_action'],
        "sub_calculations": step['sub_calculations'],
        "vector_top3": [{"id": c['id'], "name": c['name']} for c in top3],
        "assigned_id": res['id'],
        "assigned_name": res['name'],
        "justification": res['justification']
    })
    time.sleep(5)

# 결과 저장
with open('phaseA_v3_twopass_test.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n\n🏁 테스트 완료! → phaseA_v3_twopass_test.json 확인")
