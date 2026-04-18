"""
# Copyright (c) 2026 Kim Jin-chul. All rights reserved.
# This software is the confidential and proprietary information of the author.

search_engine.py
================
하이브리드 스텝 검색 및 문항-레벨 유사도 판정 엔진.

구성:
  OfflineQueryEngine  - 사전 계산된 어휘 벡터로 모델 없이 쿼리 검색
  HybridSearchEngine  - BM25 + CPT + 벡터 임베딩 결합 스텝 검색
  ProblemSimilarity   - N×M 헝가리안 매칭으로 문항 간 유사도 산출

의존 패키지:
  rank_bm25, scipy
"""

import os
import re
import json
import numpy as np
from collections import defaultdict
from rank_bm25 import BM25Okapi
from scipy.optimize import linear_sum_assignment

# LaTeX 제거 (BM25 토크나이징에 사용)
_LATEX_STRIP = re.compile(r'\$[^$]*\$|[\[\]\\${}^_]')

# 한국어 조사/어미 목록 (길이 내림차순 — 가장 긴 것부터 매칭)
_PARTICLES = sorted([
    '으로부터', '로부터', '에서부터', '이라는', '라는', '이라고', '라고',
    '에서의', '으로의', '로의', '에게서', '한테서',
    '으로써', '로써', '으로서', '로서', '이므로', '므로',
    '이라도', '라도', '이면서', '면서',
    '에서는', '에서도', '에서만',
    '으로는', '로는', '으로도', '로도',
    '이지만', '지만', '이지만',
    '으로', '에서', '에게', '한테', '께서',
    '에는', '에도', '에만',
    '이란', '란', '이나', '나',
    '이든', '든', '까지', '부터',
    '처럼', '같이', '보다', '마다',
    '에', '의', '을', '를', '이', '가',
    '은', '는', '도', '만', '과', '와',
], key=len, reverse=True)


def _tokenize(text: str) -> list:
    """조사 제거 기반 토크나이저 (BM25용) — pure Python, 의존성 없음"""
    if not text:
        return []
    clean = _LATEX_STRIP.sub(' ', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    result = []
    for token in clean.split():
        for p in _PARTICLES:
            if token.endswith(p) and len(token) > len(p) + 1:
                token = token[:-len(p)]
                break
        if len(token) >= 2:
            result.append(token)
    return result


class HybridSearchEngine:
    """
    스텝-레벨 하이브리드 검색 엔진.

    점수 구성 (클러스터 데이터 있을 때):
      최종 = 0.40 × 클러스터 + 0.30 × BM25정규화 + 0.20 × 벡터코사인 + 0.10 × CPT점수

    점수 구성 (클러스터 데이터 없을 때, 폴백):
      최종 = 0.45 × BM25정규화 + 0.40 × 벡터코사인 + 0.15 × CPT점수
    """

    def __init__(self, vec_data: dict):
        """
        vec_data: dashboard.py의 _vec_data 딕셔너리
          (step_ids, vectors, concept_ids, problem_ids, step_numbers, step_texts)
          선택: step_cluster_ids (build_trigger_clusters.py 실행 시 추가됨)
        """
        self.vec_data = vec_data
        self._cluster_ids = vec_data.get('step_cluster_ids', None)
        self._step_trigger_vecs = vec_data.get('step_trigger_vecs', None)
        if self._step_trigger_vecs is not None:
            print(f"[HybridSearchEngine] 트리거 벡터 모드 활성화 (연속 유사도)")
        elif self._cluster_ids is not None:
            print(f"[HybridSearchEngine] 클러스터 이진 모드 활성화 "
                  f"(클러스터 수: {len(set(self._cluster_ids[self._cluster_ids >= 0]))}개)")
        else:
            print("[HybridSearchEngine] 클러스터 데이터 없음 → 기존 가중치 사용")
        self._build_bm25()

    def _build_bm25(self):
        """step_texts로 BM25 인덱스 구축"""
        print("[HybridSearchEngine] BM25 인덱스 구축 중...")
        tokenized = [_tokenize(t) for t in self.vec_data['step_texts']]
        self._bm25 = BM25Okapi(tokenized)
        self._tokenized = tokenized
        print(f"[HybridSearchEngine] BM25 인덱스 완료 ({len(tokenized)}개 스텝)")

    def _trigger_sim_score(self, q_idx: int) -> np.ndarray:
        """
        트리거 카테고리 유사도 점수 (연속값).
        - 트리거 벡터 있을 때: 쿼리 트리거 벡터와 모든 스텝 트리거 벡터의 코사인 (L2 정규화되어 있으므로 내적)
        - 없고 클러스터 ID만 있을 때: 이진값 (같은 클러스터=1.0)
        - 둘 다 없을 때: 0 배열
        """
        n = len(self.vec_data['step_ids'])
        if self._step_trigger_vecs is not None:
            q_tvec = self._step_trigger_vecs[q_idx]
            norm = np.linalg.norm(q_tvec)
            if norm < 1e-9:
                return np.zeros(n, dtype=np.float32)
            return np.dot(self._step_trigger_vecs, q_tvec / norm)
        if self._cluster_ids is not None:
            q_cluster = int(self._cluster_ids[q_idx])
            if q_cluster < 0:
                return np.zeros(n, dtype=np.float32)
            return (self._cluster_ids == q_cluster).astype(np.float32)
        return np.zeros(n, dtype=np.float32)

    def _cpt_score(self, q_concept: str) -> np.ndarray:
        """CPT 코드 유사도 점수 배열 반환 (동일=1.0, 같은계열=0.5, 무관=0.0)"""
        if not q_concept:
            return np.zeros(len(self.vec_data['concept_ids']), dtype=np.float32)
        # 계열 접두사: CPT-CA1-DIF-007 → CPT-CA1-DIF
        parts = q_concept.split('-')
        family = '-'.join(parts[:3]) if len(parts) >= 3 else q_concept
        scores = []
        for c in self.vec_data['concept_ids']:
            if c == q_concept:
                scores.append(1.0)
            elif c.startswith(family):
                scores.append(0.5)
            else:
                scores.append(0.0)
        return np.array(scores, dtype=np.float32)

    def search_steps(self, step_id: int, top_k: int = 20) -> dict:
        """
        특정 step_id에 대해 유사 스텝 top_k개 반환.

        반환값:
          {
            'query': { step_id, step_title, concept_id, problem_id },
            'results': [{ step_id, problem_id, step_number, step_title,
                          concept_id, score, bm25_score, vec_score,
                          cpt_score, same_concept }, ...]
          }
        """
        step_ids = self.vec_data['step_ids']
        matches = np.where(step_ids == step_id)[0]
        if len(matches) == 0:
            return {'error': f'step_id {step_id} 없음'}
        q_idx = matches[0]

        q_vec     = self.vec_data['vectors'][q_idx]
        q_concept = str(self.vec_data['concept_ids'][q_idx])
        q_text    = str(self.vec_data['step_texts'][q_idx])

        # Layer 3: 벡터 코사인 (벡터가 L2-정규화되어 있으므로 내적 = 코사인)
        vec_scores = np.dot(self.vec_data['vectors'], q_vec)   # (N,)

        # Layer 2: BM25
        q_tokens = _tokenize(q_text)
        bm25_raw = self._bm25.get_scores(q_tokens)
        bm25_max = bm25_raw.max()
        bm25_norm = bm25_raw / (bm25_max + 1e-9)              # [0, 1]

        # Layer 1: CPT 점수
        cpt_scores = self._cpt_score(q_concept)

        # Layer 0: 트리거 유사도 (연속값 또는 이진 클러스터, 데이터 없으면 0)
        trigger_scores = self._trigger_sim_score(q_idx)
        has_trigger = (self._step_trigger_vecs is not None or self._cluster_ids is not None)

        if has_trigger:
            # 가중치: 트리거(0.40) + BM25(0.30) + 벡터(0.20) + CPT(0.10)
            final = (0.40 * trigger_scores
                     + 0.30 * bm25_norm
                     + 0.20 * vec_scores
                     + 0.10 * cpt_scores)
        else:
            # 폴백: 기존 가중치
            final = 0.15 * cpt_scores + 0.45 * bm25_norm + 0.40 * vec_scores

        final[q_idx] = -1.0   # 자기 자신 제외

        top_indices = np.argsort(final)[::-1][:top_k]

        # 클러스터 ID (same_cluster 표시용)
        q_cluster = int(self._cluster_ids[q_idx]) if self._cluster_ids is not None else -1

        results = []
        for idx in top_indices:
            results.append({
                'step_id':       int(step_ids[idx]),
                'problem_id':    str(self.vec_data['problem_ids'][idx]),
                'step_number':   int(self.vec_data['step_numbers'][idx]),
                'concept_id':    str(self.vec_data['concept_ids'][idx]),
                'score':         round(float(final[idx]), 4),
                'bm25_score':    round(float(bm25_norm[idx]), 4),
                'vec_score':     round(float(vec_scores[idx]), 4),
                'cpt_score':     round(float(cpt_scores[idx]), 4),
                'trigger_score': round(float(trigger_scores[idx]), 4),
                'same_concept':  bool(self.vec_data['concept_ids'][idx] == q_concept and q_concept != ''),
                'same_cluster':  bool(self._cluster_ids is not None and int(self._cluster_ids[idx]) == q_cluster and q_cluster >= 0),
            })

        return {
            'query': {
                'step_id':    step_id,
                'problem_id': str(self.vec_data['problem_ids'][q_idx]),
                'concept_id': q_concept,
            },
            'results': results,
        }


class ProblemSimilarity:
    """
    문항-레벨 유사도 엔진.

    알고리즘:
      1. 쿼리 문항의 스텝 벡터(Q×D)와 모든 스텝 벡터(N×D)로 Q×N 행렬 계산
      2. 각 후보 문항별로 열을 추출 → 소규모 행렬에 헝가리안 매칭
      3. 앵커 스텝 유사도(×0.6) + 나머지 평균(×0.4) 가중 합산
      4. 등급 분류 (★★★ / ★★ / ★)
    """

    WEIGHTS = {'anchor': 0.6, 'rest': 0.4}
    THRESHOLDS = {
        'anchor_min':   0.75,   # 앵커 최소 (이하면 결과 제외)
        'level3_anchor': 0.80,  # ★★★ 앵커 기준
        'level3_rest':   0.75,  # ★★★ 나머지 기준
        'level2_anchor': 0.80,  # ★★  앵커 기준
        'level2_rest':   0.50,  # ★★  나머지 기준
        'min_score':     0.40,  # 결과 표시 최소 문항 점수
    }

    def __init__(self, vec_data: dict):
        self.vec_data = vec_data

    def _get_problem_indices(self, problem_id: str) -> np.ndarray:
        """특정 문항에 속한 스텝들의 배열 인덱스 반환 (step_number 순서)"""
        mask = self.vec_data['problem_ids'] == problem_id
        indices = np.where(mask)[0]
        # step_number 순으로 정렬
        order = np.argsort(self.vec_data['step_numbers'][indices])
        return indices[order]

    def _hungarian_match(self, sim_matrix: np.ndarray) -> tuple:
        """헝가리안 알고리즘으로 최적 스텝 매칭. (row_ind, col_ind, matched_sims) 반환"""
        # 행·열 중 작은 쪽이 기준 (스텝 수가 다른 문항 처리)
        row_ind, col_ind = linear_sum_assignment(-sim_matrix)
        matched_sims = sim_matrix[row_ind, col_ind]
        return row_ind, col_ind, matched_sims

    def _classify_level(self, anchor_sim: float, rest_avg: float) -> int:
        t = self.THRESHOLDS
        if anchor_sim >= t['level3_anchor'] and rest_avg >= t['level3_rest']:
            return 3   # ★★★ 완전 유사
        if anchor_sim >= t['level2_anchor'] and rest_avg >= t['level2_rest']:
            return 2   # ★★  부분 유사
        if anchor_sim >= t['anchor_min']:
            return 1   # ★   앵커만 유사
        return 0

    def compare(self,
                query_problem_id: str,
                anchor_step_id: int,
                top_k: int = 10) -> list:
        """
        query_problem_id 문항과 유사한 문항 top_k개 반환.

        anchor_step_id: 유사도 검색을 유발한 스텝 ID (가중치 0.6)
        """
        q_indices = self._get_problem_indices(query_problem_id)
        if len(q_indices) == 0:
            return []

        # 앵커 스텝의 쿼리 문항 내 위치 (없으면 Step 1)
        q_step_ids = self.vec_data['step_ids'][q_indices]
        anchor_pos_arr = np.where(q_step_ids == anchor_step_id)[0]
        anchor_pos = int(anchor_pos_arr[0]) if len(anchor_pos_arr) > 0 else 0

        # 쿼리 문항 스텝 벡터 (Q, D)
        q_vecs = self.vec_data['vectors'][q_indices]   # (Q, D)

        # 전체 스텝과의 유사도 행렬 (Q, N_total) - 한 번만 계산
        full_sim = np.dot(q_vecs, self.vec_data['vectors'].T)   # (Q, N_total)

        # 후보 문항 목록
        all_problem_ids = np.unique(self.vec_data['problem_ids'])
        candidate_ids = [p for p in all_problem_ids if p != query_problem_id]

        results = []
        for cand_id in candidate_ids:
            c_indices = self._get_problem_indices(cand_id)
            if len(c_indices) == 0:
                continue

            # 이 후보 문항 관련 열만 추출 → (Q, M) 소행렬
            sim_sub = full_sim[:, c_indices]   # (Q, M)

            # 헝가리안 매칭
            row_ind, col_ind, matched_sims = self._hungarian_match(sim_sub)

            # 앵커 유사도: 앵커 행의 최대값 (매칭 결과와 무관하게 best match)
            anchor_sim = float(full_sim[anchor_pos, c_indices].max())

            # 나머지 매칭 평균 (앵커 행 제외)
            other_sims = [float(s) for r, s in zip(row_ind, matched_sims) if r != anchor_pos]
            rest_avg = float(np.mean(other_sims)) if other_sims else 0.0

            # 문항 유사도 점수
            w = self.WEIGHTS
            score = w['anchor'] * anchor_sim + w['rest'] * rest_avg

            level = self._classify_level(anchor_sim, rest_avg)

            if score < self.THRESHOLDS['min_score'] or level == 0:
                continue

            # 매칭 상세 정보
            step_matches = []
            for r, c, s in zip(row_ind, col_ind, matched_sims):
                step_matches.append({
                    'q_step_id':   int(self.vec_data['step_ids'][q_indices[r]]),
                    'c_step_id':   int(self.vec_data['step_ids'][c_indices[c]]),
                    'q_step_no':   int(self.vec_data['step_numbers'][q_indices[r]]),
                    'c_step_no':   int(self.vec_data['step_numbers'][c_indices[c]]),
                    'sim':         round(float(s), 3),
                })

            results.append({
                'problem_id':   cand_id,
                'score':        round(score * 100, 1),   # 퍼센트
                'level':        level,
                'level_label':  '★' * level,
                'anchor_sim':   round(anchor_sim * 100, 1),
                'rest_avg':     round(rest_avg * 100, 1),
                'step_matches': step_matches,
            })

        results.sort(key=lambda x: -x['score'])
        return results[:top_k]


# ─────────────────────────────────────────────────────────────────────────────
class OfflineQueryEngine:
    """
    사전 계산된 어휘-Step 유사도 행렬을 이용한 오프라인 쿼리 검색 엔진.

    런타임에 ML 모델이 불필요합니다.
    build_query_vocab.py로 생성된 kice_query_vocab.npz를 사용합니다.

    동작 흐름:
      1. 쿼리 텍스트를 토크나이징
      2. 각 토큰을 어휘 사전에서 포함 관계로 매칭
      3. 매칭된 어휘들의 사전 계산 유사도 행을 가중 평균
      4. Step 인덱스 기준 최종 점수 배열 반환
    """

    VOCAB_NPZ = 'kice_query_vocab.npz'

    def __init__(self):
        if not os.path.exists(self.VOCAB_NPZ):
            raise FileNotFoundError(
                f"{self.VOCAB_NPZ} 파일이 없습니다. "
                "build_query_vocab.py를 먼저 실행하세요."
            )
        data = np.load(self.VOCAB_NPZ, allow_pickle=True)
        self.terms         = data['terms']           # (n_vocab,) str
        self.top_k_indices = data['top_k_indices']   # (n_vocab, K) int32
        self.top_k_scores  = data['top_k_scores']    # (n_vocab, K) float32
        self.step_ids      = data['step_ids']         # (n_steps,) int32
        self.problem_ids   = data['problem_ids']      # (n_steps,) str
        self.n_steps       = len(self.step_ids)
        self.K             = self.top_k_indices.shape[1]
        print(f"[OfflineQueryEngine] 로드 완료: 어휘 {len(self.terms)}개 / Step {self.n_steps}개 / Top-{self.K}")

    @staticmethod
    def _tokenize(query: str) -> list[str]:
        """쿼리를 공백·구두점 기준으로 분리, 2글자 이상 토큰만 반환."""
        tokens = re.split(r'[\s·,·.·/·(·)·\[\]]+', query.strip())
        return [t for t in tokens if len(t) >= 2]

    def get_cos_sims(self, query: str, min_score: float = 0.0) -> np.ndarray:
        """
        쿼리에 대한 전체 Step 코사인 유사도 배열을 반환합니다.

        IDF 가중치: 적은 어휘에 매칭되는 구체적 토큰일수록 높은 가중치를 부여.
          weight_i = Σ log(N / df_t)  for t in query_tokens if t ∈ term_i
          (N = vocab 크기, df_t = 토큰 t를 포함하는 vocab term 수)

        반환값: np.ndarray shape=(n_steps,), dtype=float32
        """
        import math
        tokens = self._tokenize(query)
        if not tokens:
            return np.zeros(self.n_steps, dtype=np.float32)

        # 1) 각 토큰의 DF (몇 개 vocab term에 포함되는가) + term별 히트 목록을 한 번에 수집
        token_df: dict[str, int] = {t: 0 for t in tokens}
        term_hits: dict[int, list] = {}
        for i, term in enumerate(self.terms):
            hits = [t for t in tokens if t in term]
            if hits:
                term_hits[i] = hits
                for t in hits:
                    token_df[t] += 1

        if not term_hits:
            return np.zeros(self.n_steps, dtype=np.float32)

        # 2) IDF: log(N / df) — df가 클수록(광범위 토큰) 낮은 가중치
        n_vocab = len(self.terms)
        token_idf = {t: math.log(n_vocab / df) for t, df in token_df.items() if df > 0}

        # 3) vocab term별 가중치 = 매칭 토큰들의 IDF 합
        vocab_weights: dict[int, float] = {}
        for i, hits in term_hits.items():
            w = sum(token_idf.get(t, 0.0) for t in hits)
            if w > 0:
                vocab_weights[i] = w

        if not vocab_weights:
            return np.zeros(self.n_steps, dtype=np.float32)

        # 4) 정규화 후 Step 점수 집계
        total_weight = sum(vocab_weights.values())
        step_scores = np.zeros(self.n_steps, dtype=np.float32)
        for vocab_idx, weight in vocab_weights.items():
            w = weight / total_weight
            indices = self.top_k_indices[vocab_idx]  # (K,)
            scores  = self.top_k_scores[vocab_idx]   # (K,)
            np.add.at(step_scores, indices, w * scores)

        return step_scores

    def is_available(self) -> bool:
        return True
