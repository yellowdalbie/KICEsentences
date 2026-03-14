"""
build_vectors.py
================
Step 타이틀 텍스트를 BGE-m3-ko 모델로 임베딩하여 kice_step_vectors.npz 에 저장합니다.
build_db.py 실행 후 이 스크립트를 실행하세요.

임베딩 텍스트 구성 (3-tier 풍성화):
  Tier 1: step_title  (핵심 기법 표현)
  Tier 2: trigger_text (수학적 맥락 카테고리)
  Tier 3: concept standard_name + keywords (교육과정 성취기준 설명)

사용법:
    python3 build_vectors.py
"""

import json
import sqlite3
import re
import numpy as np
from sentence_transformers import SentenceTransformer

DB_FILE = 'kice_database.sqlite'
OUTPUT_FILE = 'kice_step_vectors.npz'
MODEL_NAME = 'dragonkue/BGE-m3-ko'

# ─────────────────────────────────────────
# LaTeX 전처리: 수식 → 읽기 쉬운 텍스트
# 모델이 수학 변수명을 의미 있는 토큰으로 처리할 수 있도록 정규화
# ─────────────────────────────────────────
LATEX_MAP = {
    r'\\sin': 'sin',
    r'\\cos': 'cos',
    r'\\tan': 'tan',
    r'\\cot': 'cot',
    r'\\sec': 'sec',
    r'\\csc': 'csc',
    r'\\log': 'log',
    r'\\ln': 'ln',
    r'\\lim': 'lim',
    r'\\sum': '합',
    r'\\int': '적분',
    r'\\infty': '무한대',
    r'\\sqrt': '제곱근',
    r'\\frac': '분수',
    r'\\theta': 'theta',
    r'\\alpha': 'alpha',
    r'\\beta': 'beta',
    r'\\gamma': 'gamma',
    r'\\delta': 'delta',
    r'\\pi': 'pi',
    r'\\leq': '이하',
    r'\\geq': '이상',
    r'\\neq': '같지않음',
    r'\\cdot': '곱',
    r'\\times': '곱',
    r'\\div': '나누기',
    r'\\pm': '더하기빼기',
    r'\\left': '',
    r'\\right': '',
    r'\\mid': '조건',
    r'\\in': '원소',
    r'\\cup': '합집합',
    r'\\cap': '교집합',
    r'\\prime': '프라임',
    r'\\quad': ' ',
    r'\\,': ' ',
}

def preprocess_latex(text: str) -> str:
    """LaTeX 명령어를 의미 있는 텍스트로 변환 후 수식 기호 정리"""
    if not text:
        return ''
    for pattern, replacement in LATEX_MAP.items():
        text = re.sub(pattern, replacement, text)
    # 중괄호, 수식 달러 기호 등 잔여 LaTeX 기호 제거
    text = re.sub(r'[\$\{\}\_\^\\]', ' ', text)
    # 연속 공백 정리
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def load_steps(conn: sqlite3.Connection):
    """스텝 데이터를 트리거, 개념 정보와 함께 조회 (3-tier 풍성화용)"""
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT
            s.step_id,
            s.step_title,
            s.action_concept_id,
            s.problem_id,
            s.step_number,
            GROUP_CONCAT(t.trigger_text, ' / ') AS trigger_texts,
            c.standard_name,
            c.keywords
        FROM steps s
        LEFT JOIN step_triggers st ON s.step_id = st.step_id
        LEFT JOIN triggers t ON st.trigger_id = t.trigger_id
        LEFT JOIN concepts c ON s.action_concept_id = c.id
        WHERE s.step_title IS NOT NULL AND s.step_title != ""
        GROUP BY s.step_id
    ''')
    rows = cursor.fetchall()
    return rows


def build_embedding_text(row) -> str:
    """step_title + trigger + concept 정보를 결합한 풍성화 임베딩 텍스트 생성"""
    parts = [row['step_title']]

    # Tier 2: 트리거 카테고리 (괄호 제거하여 자연어화)
    if row['trigger_texts']:
        trigger_clean = re.sub(r'[\[\]]', '', row['trigger_texts'])
        parts.append(trigger_clean)

    # Tier 3: 교육과정 성취기준 설명 + 키워드
    if row['standard_name']:
        parts.append(row['standard_name'])
    if row['keywords']:
        try:
            kws = json.loads(row['keywords'])
            parts.append(' '.join(kws))
        except (json.JSONDecodeError, TypeError):
            pass

    return preprocess_latex(' | '.join(parts))


def main():
    print(f"[1/4] DB 연결 중: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    rows = load_steps(conn)
    conn.close()

    if not rows:
        print("ERROR: steps 테이블에 데이터가 없습니다. build_db.py를 먼저 실행하세요.")
        return

    print(f"[2/4] {len(rows)}개 스텝 로드 완료. 임베딩 텍스트 구성 중...")
    step_ids = []
    step_texts = []
    concept_ids = []
    problem_ids = []
    step_numbers = []

    for row in rows:
        step_ids.append(row['step_id'])
        step_texts.append(build_embedding_text(row))
        concept_ids.append(row['action_concept_id'] or '')
        problem_ids.append(row['problem_id'] or '')
        step_numbers.append(row['step_number'] or 0)

    # 풍성화 샘플 출력 (첫 3개)
    print("\n  [임베딩 텍스트 샘플]")
    for i in range(min(3, len(step_texts))):
        print(f"  Step {step_ids[i]}: {step_texts[i][:100]}...")
    print()

    print(f"[3/4] 임베딩 생성 중 (모델: {MODEL_NAME}) ...")
    print("      첫 실행 시 모델 다운로드(~500MB)가 필요합니다.")
    model = SentenceTransformer(MODEL_NAME)
    vectors = model.encode(
        step_texts,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True  # 코사인 유사도를 위해 L2 정규화
    )

    print(f"[4/4] 벡터 저장 중: {OUTPUT_FILE}")
    np.savez(
        OUTPUT_FILE,
        step_ids=np.array(step_ids, dtype=np.int32),
        vectors=vectors.astype(np.float32),
        concept_ids=np.array(concept_ids, dtype=object),
        problem_ids=np.array(problem_ids, dtype=object),
        step_numbers=np.array(step_numbers, dtype=np.int32),
        step_texts=np.array(step_texts, dtype=object),
    )

    print(f"\n완료! 저장된 벡터 수: {len(step_ids)}, 차원: {vectors.shape[1]}")
    print(f"파일 경로: {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
