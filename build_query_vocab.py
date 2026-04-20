"""
build_query_vocab.py
====================
사용자 쿼리 어휘 사전을 구축하고, 각 어휘와 전체 Step 간의
코사인 유사도 Top-K를 미리 계산하여 kice_query_vocab.npz에 저장합니다.

[실행 조건]
- BGE-m3-ko 모델 및 sentence-transformers 필요 (빌드 PC에서만 실행)
- kice_database.sqlite, kice_step_vectors.npz, concepts.json 필요

[출력]
- kice_query_vocab.npz : 배포 패키지에 포함, 런타임에 모델 불필요
"""

import re
import json
import sqlite3
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

# ── 설정 ─────────────────────────────────────────────────────────────────────
DB_PATH          = 'kice_database.sqlite'
STEP_VECTORS_NPZ = 'kice_step_vectors.npz'
CONCEPTS_JSON    = 'concepts.json'
OUTPUT_NPZ       = 'kice_query_vocab.npz'

TOP_K            = 100   # 어휘당 저장할 상위 Step 수
MIN_TERM_LEN     = 3     # 최소 글자 수 (3자 미만은 제외, 단 수학 핵심어 화이트리스트 예외)
LATEX_RATIO_MAX  = 0.15  # $ 기호 비율 상한 (이 이상이면 제외)
BATCH_SIZE       = 128   # 임베딩 배치 크기

# 2자 수학 핵심어: MIN_TERM_LEN 기준 미달이지만 반드시 vocab에 포함
MATH_WHITELIST = {
    "미분", "적분", "극한", "수열", "확률", "집합", "행렬", "벡터",
    "함수", "방정식", "부등식", "도형", "넓이", "부피", "속도", "가속도",
    "근", "항", "합", "곱", "비", "차", "역",
}


# ── 1단계: 어휘 수집 ──────────────────────────────────────────────────────────
def collect_vocab():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    terms = set()

    # (A) Step 타이틀 — 가장 중요한 소스
    cur.execute("SELECT step_title FROM steps WHERE step_title IS NOT NULL")
    for (t,) in cur.fetchall():
        terms.add(t.strip())
    print(f"[1A] Step 타이틀 수집: {len(terms)}개")

    # (B) Trigger 텍스트의 [] 카테고리 부분
    before = len(terms)
    cur.execute("SELECT trigger_text FROM triggers")
    for (t,) in cur.fetchall():
        m = re.match(r'^\[([^\]]+)\]', t or '')
        if m:
            cat = m.group(1).strip()
            terms.add(cat)
    print(f"[1B] Trigger 카테고리 추가: +{len(terms) - before}개")

    # (C) concepts.json — standard_name + 개별 키워드
    before = len(terms)
    with open(CONCEPTS_JSON, encoding='utf-8') as f:
        concepts = json.load(f)
    for c in concepts:
        terms.add(c['standard_name'].strip())
        kws_raw = c.get('keywords', [])
        if isinstance(kws_raw, list):
            kws = kws_raw
        else:
            try:
                kws = json.loads(kws_raw)
            except Exception:
                kws = [k.strip() for k in str(kws_raw).split(',') if k.strip()]
        for kw in kws:
            terms.add(str(kw).strip())

    print(f"[1C] Concepts 추가: +{len(terms) - before}개")

    # (D) 수학 핵심어 화이트리스트 — 소스 미포함 시 강제 추가
    before_wl = len(terms)
    terms.update(MATH_WHITELIST)
    print(f"[1D] 화이트리스트 강제 추가: +{len(terms) - before_wl}개")

    conn.close()
    return terms


# ── 2단계: 정제 ───────────────────────────────────────────────────────────────
def filter_vocab(raw_terms):
    cleaned = []
    for t in raw_terms:
        # 화이트리스트 단어는 길이 기준 예외
        if t not in MATH_WHITELIST and len(t) < MIN_TERM_LEN:
            continue
        latex_ratio = t.count('$') / len(t)
        if latex_ratio > LATEX_RATIO_MAX:
            continue
        cleaned.append(t)

    # 중복 제거 후 정렬 (재현성)
    cleaned = sorted(set(cleaned))
    wl_hits = sum(1 for t in cleaned if t in MATH_WHITELIST)
    print(f"[2] 정제 후 어휘: {len(cleaned)}개 (원본 {len(raw_terms)}개, 화이트리스트 {wl_hits}개 포함)")
    return cleaned


# ── 3단계: 임베딩 ─────────────────────────────────────────────────────────────
def embed_vocab(terms):
    print("[3] BGE-m3-ko 모델 로드 중...")
    model = SentenceTransformer('dragonkue/BGE-m3-ko')

    print(f"[3] 어휘 {len(terms)}개 임베딩 중 (batch={BATCH_SIZE})...")
    vectors = model.encode(
        terms,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,   # 코사인 유사도 = 내적으로 단순화
        convert_to_numpy=True,
    )
    print(f"[3] 완료: shape={vectors.shape}")
    return vectors  # (n_vocab, 1024)


# ── 4단계: 유사도 Top-K 계산 ──────────────────────────────────────────────────
def compute_top_k(vocab_vectors, step_data):
    step_ids    = step_data['step_ids']      # (2208,)
    step_vecs   = step_data['vectors']       # (2208, 1024)
    n_vocab     = vocab_vectors.shape[0]
    n_steps     = step_vecs.shape[0]
    k           = min(TOP_K, n_steps)

    print(f"[4] 유사도 행렬 계산: {n_vocab} × {n_steps} → Top-{k} 저장")

    top_k_indices = np.zeros((n_vocab, k), dtype=np.int32)
    top_k_scores  = np.zeros((n_vocab, k), dtype=np.float32)

    # normalize_embeddings=True이면 내적 = 코사인 유사도
    # 배치 처리로 메모리 절약
    CHUNK = 500
    for start in range(0, n_vocab, CHUNK):
        end   = min(start + CHUNK, n_vocab)
        chunk = vocab_vectors[start:end]          # (chunk, 1024)
        sims  = chunk @ step_vecs.T               # (chunk, 2208)

        for i, sim_row in enumerate(sims):
            top_k = np.argpartition(sim_row, -k)[-k:]
            top_k = top_k[np.argsort(sim_row[top_k])[::-1]]
            top_k_indices[start + i] = top_k
            top_k_scores[start + i]  = sim_row[top_k]

        if (start // CHUNK) % 5 == 0:
            print(f"  {end}/{n_vocab} 처리 완료")

    print("[4] 완료")
    return top_k_indices, top_k_scores


# ── 5단계: 저장 ───────────────────────────────────────────────────────────────
def save(terms, vocab_vectors, top_k_indices, top_k_scores, step_data):
    np.savez_compressed(
        OUTPUT_NPZ,
        terms         = np.array(terms, dtype=object),
        vocab_vectors = vocab_vectors.astype(np.float32),
        top_k_indices = top_k_indices,
        top_k_scores  = top_k_scores,
        step_ids      = step_data['step_ids'],
        problem_ids   = step_data['problem_ids'],
        step_numbers  = step_data['step_numbers'],
    )
    import os
    size_mb = os.path.getsize(OUTPUT_NPZ) / 1024 / 1024
    print(f"[5] 저장 완료: {OUTPUT_NPZ} ({size_mb:.1f} MB)")
    print(f"    어휘: {len(terms)}개 / Step: {len(step_data['step_ids'])}개 / Top-K: {top_k_indices.shape[1]}")


# ── 메인 ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Step 벡터 로드
    print("[0] Step 벡터 로드...")
    step_data = np.load(STEP_VECTORS_NPZ, allow_pickle=True)

    # step_vectors도 정규화 (내적 = 코사인 유사도로 사용)
    step_vecs_raw = step_data['vectors'].astype(np.float32)
    norms = np.linalg.norm(step_vecs_raw, axis=1, keepdims=True)
    norms[norms == 0] = 1
    step_vecs_norm = step_vecs_raw / norms

    # step_data를 정규화 버전으로 교체 (계산용)
    class StepDataWrapper:
        def __init__(self, data, norm_vecs):
            self._data = data
            self.vectors = norm_vecs
        def __getitem__(self, key):
            if key == 'vectors':
                return self.vectors
            return self._data[key]

    step_data_w = StepDataWrapper(step_data, step_vecs_norm)
    print(f"[0] Step {len(step_data['step_ids'])}개 로드 완료")

    # 파이프라인 실행
    raw_terms    = collect_vocab()
    terms        = filter_vocab(raw_terms)
    vocab_vecs   = embed_vocab(terms)
    top_k_idx, top_k_sc = compute_top_k(vocab_vecs, step_data_w)
    save(terms, vocab_vecs, top_k_idx, top_k_sc, step_data_w)
