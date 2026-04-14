"""
Phase A - Cluster Labeler
목적: 35개 클러스터 대표점에만 LLM 호출하여 canonical_name을 제안받고,
      나머지 2,559개는 벡터 유사도로 자동 배정

실행: .venv/bin/python phase_A_cluster_labeler.py
"""

import json
import os
import re
import requests
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

REVIEW_TARGETS = '.build_cache/phase_A/cluster_review_targets.json'
CLUSTER_ANALYSIS = '.build_cache/phase_A/cluster_analysis.json'
CONCEPTS_FILE = 'concepts.json'
LABELED_OUTPUT = '.build_cache/phase_A/cluster_labels.json'   # 35개 label 결과
FINAL_OUTPUT = 'phaseA_canonical_v2.json'                      # 전체 배정 결과

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5-coder:14b"
EMBED_MODEL_NAME = 'dragonkue/BGE-m3-ko'

# ======= 교육과정 표준 용어 참조 건물 =======
def load_concept_keywords():
    with open(CONCEPTS_FILE, 'r') as f:
        concepts = json.load(f)
    high_school = {}
    for row in concepts:
        if row['id'].startswith('9수'): continue
        kws = [k for k in row.get('keywords', []) if isinstance(k, str) and len(k) > 1]
        high_school[row['id']] = {
            'name': row.get('standard_name', ''),
            'keywords': kws
        }
    return high_school

# ======= LLM 호출 =======
def call_ollama_json(prompt, timeout=180):
    try:
        res = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json"
        }, timeout=timeout)
        res.raise_for_status()
        return json.loads(res.json()['message']['content'])
    except Exception as e:
        print(f"  [!] LLM 오류: {e}")
        return None

# ======= 35개 클러스터 대표점 LLM 라벨링 =======
def label_clusters(review_targets, concept_vocab):
    """클러스터 대표점 35개에만 LLM 호출"""

    # 기존 label 결과 로드 (이어부르기)
    if os.path.exists(LABELED_OUTPUT):
        with open(LABELED_OUTPUT, 'r') as f:
            labeled = json.load(f)
    else:
        labeled = {}

    labeled_ids = set(labeled.keys())
    pending = [t for t in review_targets if str(t['cluster_id']) not in labeled_ids]
    print(f"라벨 필요: {len(pending)}개 / 기완료: {len(labeled_ids)}개")

    # 교육과정 핵심어 목록 (프롬프트 주입용)
    concept_terms = []
    for cid, info in concept_vocab.items():
        kws = info.get('keywords', [])
        if kws:
            concept_terms.append(f"[{cid}] {info['name']} — {', '.join(kws[:3])}")
    concept_str = '\n'.join(concept_terms[:30])  # 상위 30개만

    for t in pending:
        cid = t['cluster_id']
        rep = t['representative_action']
        samples = t.get('sample_actions', [])
        size = t['size']

        samples_str = '\n'.join([f"  - {s}" for s in samples[:4]])

        prompt = f"""너는 2022 개정 수학과 교육과정 전문가다.
다음은 한국 수능 수학 해설 스텝들 중 비슷한 것들이 모인 클러스터({size}개)의 대표 표현과 샘플들이다.

[대표 표현]: "{rep}"
[같은 클러스터의 다른 표현들]:
{samples_str}

이 클러스터가 공통적으로 수행하는 수학적 행동을 하나의 "표준 패턴명"으로 명명하라.

작명 규칙:
1. 형식: "[수학적 개념/도구]을(를) 이용하여 [결과]를 [동사]하기"
2. 핵심 개념 명칭은 아래 교육과정 공식 용어에서 최대한 선택할 것:
{concept_str}
3. 문항 고유 변수($a$, $f(x)$, $n$)나 숫자를 포함하지 말 것
4. 너무 포괄적(예: "조건을 이용하기")도, 너무 세부적(예: "x=-1에서 인수분해")도 아닌 수준으로 작성

또한 이 패턴과 가장 부합하는 성취기준 ID 하나를 선택하라.

반드시 아래 형식의 JSON만 반환하라:
{{
  "canonical_name": "표준 패턴명",
  "concept_id": "성취기준ID (예: 12미적Ⅰ-02-07)",
  "rationale": "선택 이유 한 문장"
}}"""

        print(f"  > Cluster {cid} ({size}개): {rep[:40]}...", flush=True)
        result = call_ollama_json(prompt)

        if result and 'canonical_name' in result:
            labeled[str(cid)] = {
                'cluster_id': cid,
                'size': size,
                'representative_action': rep,
                'canonical_name': result.get('canonical_name', ''),
                'concept_id': result.get('concept_id', ''),
                'rationale': result.get('rationale', ''),
                'sample_actions': samples
            }
            print(f"    ✅ → {result.get('canonical_name', '')[:50]}")
        else:
            labeled[str(cid)] = {
                'cluster_id': cid,
                'size': size,
                'representative_action': rep,
                'canonical_name': rep,  # 실패 시 raw 유지
                'concept_id': '',
                'rationale': 'LLM 실패 - raw 유지',
                'sample_actions': samples
            }
            print(f"    ⚠️  LLM 실패, raw 유지")

        # 매 라벨마다 저장
        with open(LABELED_OUTPUT, 'w') as f:
            json.dump(labeled, f, ensure_ascii=False, indent=2)

    return labeled

# ======= 전체 항목에 클러스터 label 자동 배정 =======
def assign_all(labeled_clusters, cluster_analysis_data, embed_model):
    """클러스터 label을 전체 2,594개 항목에 자동 배정"""

    items = cluster_analysis_data['items']
    print(f"\n[배정] 총 {len(items)}개 항목에 canonical_name 배정 중...")

    results = []
    for item in items:
        cid = str(item['cluster_id'])
        cluster_info = labeled_clusters.get(cid, {})
        results.append({
            'file': item['file'],
            'step_number': item['step_number'],
            'raw_logical_action': item['logical_action'],
            'canonical_name': cluster_info.get('canonical_name', item['logical_action']),
            'assigned_concept_id': cluster_info.get('concept_id', ''),
            'cluster_id': item['cluster_id'],
            'rationale': cluster_info.get('rationale', '')
        })

    with open(FINAL_OUTPUT, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"  저장 완료: {FINAL_OUTPUT} ({len(results)}개)")
    return results

# ======= 메인 =======
def main():
    print("=" * 55)
    print("🏷️  Phase A: Cluster Labeler (LLM × 35개만)")
    print("=" * 55)

    # 데이터 로드
    with open(REVIEW_TARGETS, 'r') as f:
        review_targets = json.load(f)
    with open(CLUSTER_ANALYSIS, 'r') as f:
        cluster_analysis_data = json.load(f)

    concept_vocab = load_concept_keywords()
    print(f"\n클러스터 수: {len(review_targets)}개")
    print(f"전체 항목 수: {len(cluster_analysis_data['items'])}개")

    # Step 1: 35개만 LLM 라벨링
    print(f"\n[Step 1] LLM으로 클러스터 라벨링 ({len(review_targets)}개)")
    embed_model = SentenceTransformer(EMBED_MODEL_NAME)
    labeled = label_clusters(review_targets, concept_vocab)

    # Step 2: 전체에 자동 배정
    print(f"\n[Step 2] 전체 항목 자동 배정")
    results = assign_all(labeled, cluster_analysis_data, embed_model)

    # Step 3: 요약 출력
    print(f"\n[Step 3] 라벨링 결과 요약 (클러스터 크기순 Top 15):")
    sorted_clusters = sorted(labeled.values(), key=lambda x: -x.get('size', 0))
    for cl in sorted_clusters[:15]:
        print(f"  [{cl['cluster_id']:2d}] {cl['size']:3d}개 → {cl['canonical_name'][:55]}")
        print(f"       성취기준: {cl['concept_id']}")

    print(f"\n✅ 완료! 결과: {FINAL_OUTPUT}")
    print(f"💡 다음 단계: 결과 검토 후 엣지케이스 정제")

if __name__ == '__main__':
    main()
