"""
Phase A - Cluster Label 수동 교정 스크립트
13개 오류 클러스터를 진단 결과에 따라 수정
실행: .venv/bin/python phase_A_label_fix.py
"""

import json
import requests

LABELS_FILE = '.build_cache/phase_A/cluster_labels.json'
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5-coder:14b"

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

# ============================================================
# 명백한 케이스는 수동으로 직접 교정 (LLM 없이)
# ============================================================
MANUAL_FIXES = {
    # Cluster 5: 극값이 아니라 좌·우극한 관찰 클러스터
    "5": {
        "canonical_name": "좌극한·우극한을 이용하여 극한값을 구하기",
        "concept_id": "12미적Ⅰ-01-02",
        "rationale": "샘플들이 모두 그래프에서 좌극한/우극한을 시각적으로 관찰하여 극한값을 구하는 행동. 극한의 성질과 극한값 계산(12미적Ⅰ-01-02)에 해당."
    },
    # Cluster 8: "최종 계산 결과 도출" - 여러 단원에 걸친 '마지막 산술 계산' 집합체
    # 샘플: "모든 조합의 확률을 합산하여 최종 결과를 도출" → 이 클러스터 자체가 잡다함
    # → 재분류 불가, '계산 결과 정리' 로 명시
    "8": {
        "canonical_name": "앞서 구한 값들을 대입하여 최종 답을 계산하기",
        "concept_id": "10공수1-01-01",  # 가장 낮은 단계의 '식의 계산'
        "rationale": "각 문항 마지막에 이전 스텝에서 구한 값들을 합산·대입하여 수치 결과를 확정하는 단계. 개념보다는 산술 계산 행위에 해당."
    },
    # Cluster 17: 함수 미분 – 개념은 명확하나 변수명이 그대로 노출됨
    "17": {
        "canonical_name": "도함수를 구하여 다음 계산에 활용하기",
        "concept_id": "12미적Ⅰ-02-03",
        "rationale": "여러 함수(삼차·다항·합성 등)의 도함수를 구하는 행동. 도함수 계산(12미적Ⅰ-02-03)에 해당."
    },
    # Cluster 26: 좌표/거리 계산 – 신뢰구간·경우의 수 등 이질적 샘플이 섞임
    # 실제 대표점 "좌표를 이용하여 거리를 계산하기"는 맞으나 concept_id 오류
    "26": {
        "canonical_name": "주어진 조건에서 수치(거리·길이·확률 등)를 계산하기",
        "concept_id": "10공수1-01-01",  # 잡다한 클러스터이므로 가장 범용 성취기준
        "rationale": "대표점은 거리 계산이나 신뢰구간, 최단경로 등 이질적 샘플이 포함된 잡다한 클러스터. 재클러스터링 필요 표시."
    },
    # Cluster 20: 코사인법칙 – concept_id 오류
    "20": {
        "canonical_name": "코사인법칙을 이용하여 삼각형의 변의 길이를 구하기",
        "concept_id": "12대수02-03",
        "rationale": "대부분의 샘플이 사인/코사인법칙을 이용하여 삼각형의 변 길이를 구하는 행동. 사인법칙·코사인법칙(12대수02-03)에 해당."
    },
    # Cluster 28: 방정식으로 값을 구하기 – Z값 계산 샘플이 섞임 → 통계 영역
    "28": {
        "canonical_name": "표준화(Z변환)를 이용하여 확률값을 구하기",
        "concept_id": "12확통03-04",
        "rationale": "샘플들이 정규분포의 표준화(Z변환)와 확률 계산을 다룸. 정규분포(12확통03-04)에 해당."
    },
    # Cluster 31: 두 그래프 교점 – concept_id 오류
    "31": {
        "canonical_name": "방정식을 이용하여 두 그래프의 교점을 구하기",
        "concept_id": "12미적Ⅰ-02-09",
        "rationale": "두 함수의 그래프가 만나는 교점을 방정식으로 풀어 구하는 행동. 방정식과 부등식에의 활용(12미적Ⅰ-02-09)에 해당."
    },
    # Cluster 34: 로그 성질 계산 – concept_id 오류 (평면좌표 아님)
    "34": {
        "canonical_name": "로그의 성질을 이용하여 로그 방정식을 풀기",
        "concept_id": "12대수01-04",
        "rationale": "로그 성질을 이용하여 로그값을 변환하거나 방정식을 도출하는 행동. 로그의 뜻과 성질(12대수01-04)에 해당."
    },
    # Cluster 4: 정규분포 표준화
    "4": {
        "canonical_name": "정규분포를 표준화하여 확률값을 구하기",
        "concept_id": "12확통03-04",
        "rationale": "정규분포 N(m, σ²)를 표준정규분포 Z로 변환한 뒤 확률표로 확률을 계산하는 행동. 정규분포(12확통03-04)에 해당."
    },
    # Cluster 1: 함수 미분 (변수명 노출) – Cluster 17과 유사하나 좀 더 극한/미분계수 쪽
    "1": {
        "canonical_name": "함수를 미분하여 도함수를 구하기",
        "concept_id": "12미적Ⅰ-02-04",
        "rationale": "다항함수의 도함수를 직접 계산하거나 미분계수를 활용하는 행동. 다항함수의 미분법(12미적Ⅰ-02-04)에 해당."
    },
    # Cluster 23: 이차방정식 도출 → 미분계수/극한 등 다양한 출처
    "23": {
        "canonical_name": "주어진 식을 변형하여 이차방정식을 도출하기",
        "concept_id": "10공수1-02-02",
        "rationale": "여러 조건을 정리하여 이차방정식 형태로 바꾸는 행동. 이차방정식의 판별식과 근(10공수1-02-02)에 해당."
    },
    # Cluster 27: 접선의 기울기 = 미분계수
    "27": {
        "canonical_name": "미분계수를 이용하여 접선의 기울기를 구하기",
        "concept_id": "12미적Ⅰ-02-05",
        "rationale": "특정 점에서 도함수(미분계수)를 계산하여 접선의 기울기를 구하는 행동. 접선의 방정식(12미적Ⅰ-02-05)에 해당."
    },
    # Cluster 13: 정적분으로 속도/거리 계산 – concept_id 오류
    "13": {
        "canonical_name": "정적분을 이용하여 이동 거리 또는 위치 변화를 구하기",
        "concept_id": "12미적Ⅰ-03-06",
        "rationale": "속도 함수를 적분하여 이동 거리나 위치를 구하는 행동. 적분을 속도와 거리에 활용(12미적Ⅰ-03-06)에 해당."
    },
    # Cluster 15: 부등식 조건에서 x 범위 도출
    "15": {
        "canonical_name": "부등식의 성질을 이용하여 변수의 범위를 결정하기",
        "concept_id": "10공수1-02-07",
        "rationale": "주어진 조건을 부등식으로 변환하여 변수의 범위를 구하는 행동. 여러 가지 방정식과 부등식(10공수1-02-07)에 해당."
    },
    # Cluster 32: 수열 귀납적 패턴 (홀수→역수 변환)
    "32": {
        "canonical_name": "수열의 귀납적 정의를 이용하여 항의 변환 패턴을 파악하기",
        "concept_id": "12대수03-06",
        "rationale": "귀납적으로 정의된 수열에서 홀수/짝수 항의 패턴을 파악하는 행동. 수열의 귀납적 정의(12대수03-06)에 해당."
    },
}


def main():
    print("=" * 55)
    print("🔧 Phase A - Cluster Label 교정")
    print("=" * 55)

    with open(LABELS_FILE, 'r') as f:
        labels = json.load(f)

    fixed_count = 0
    for cid, fix in MANUAL_FIXES.items():
        if cid in labels:
            old_name = labels[cid].get('canonical_name', '')
            old_concept = labels[cid].get('concept_id', '')
            labels[cid]['canonical_name'] = fix['canonical_name']
            labels[cid]['concept_id'] = fix['concept_id']
            labels[cid]['rationale'] = fix['rationale']
            labels[cid]['fix_status'] = 'manually_corrected'
            fixed_count += 1
            print(f"\n✅ Cluster {cid} ({labels[cid].get('size',0)}개) 교정:")
            print(f"   이전: [{old_concept}] {old_name[:45]}")
            print(f"   이후: [{fix['concept_id']}] {fix['canonical_name'][:45]}")

    with open(LABELS_FILE, 'w') as f:
        json.dump(labels, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*55}")
    print(f"✅ 총 {fixed_count}개 클러스터 교정 완료")
    print(f"   저장: {LABELS_FILE}")
    print(f"\n💡 다음: phase_A_cluster_labeler.py의 assign_all()을 재실행하여")
    print(f"   phaseA_canonical_v2.json을 교정된 라벨로 갱신하세요.")


if __name__ == "__main__":
    main()
