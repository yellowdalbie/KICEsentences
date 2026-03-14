"""
search_engine.py
================
하이브리드 스텝 검색 및 문항-레벨 유사도 판정 엔진.

구성:
  HybridSearchEngine  - BM25 + CPT + 벡터 임베딩 결합 스텝 검색
  ProblemSimilarity   - N×M 헝가리안 매칭으로 문항 간 유사도 산출

의존 패키지:
  rank_bm25, kiwipiepy, scipy
"""

import re
import json
import numpy as np
from rank_bm25 import BM25Okapi
from kiwipiepy import Kiwi
from scipy.optimize import linear_sum_assignment

# 형태소 분석기 (모듈 로드 시 1회 초기화)
print("[search_engine] Kiwi 형태소 분석기 초기화 중...")
_kiwi = Kiwi()
print("[search_engine] 초기화 완료.")

# BM25에서 의미 있는 품사 태그 (명사, 외국어, 기호 등)
_MEANINGFUL_TAGS = {'NNG', 'NNP', 'NNB', 'SL', 'SW', 'XR'}

# step_title 표시용 LaTeX 제거 (BM25 토크나이징에 사용)
_LATEX_STRIP = re.compile(r'\$[^$]*\$|[\[\]\\${}^_]')


def _tokenize(text: str) -> list:
    """한국어 형태소 분석 + 수학 용어 추출 (BM25용)"""
    if not text:
        return []
    # LaTeX 수식 제거 후 분석
    clean = _LATEX_STRIP.sub(' ', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    try:
        tokens = _kiwi.tokenize(clean)
        return [t.form for t in tokens if t.tag in _MEANINGFUL_TAGS and len(t.form) > 1]
    except Exception:
        return clean.split()


class HybridSearchEngine:
    """
    스텝-레벨 하이브리드 검색 엔진.

    점수 구성:
      최종 = 0.3 × CPT점수 + 0.4 × BM25정규화 + 0.3 × 벡터코사인
    """

    def __init__(self, vec_data: dict):
        """
        vec_data: dashboard.py의 _vec_data 딕셔너리
          (step_ids, vectors, concept_ids, problem_ids, step_numbers, step_texts)
        """
        self.vec_data = vec_data
        self._build_bm25()

    def _build_bm25(self):
        """step_texts로 BM25 인덱스 구축"""
        print("[HybridSearchEngine] BM25 인덱스 구축 중...")
        tokenized = [_tokenize(t) for t in self.vec_data['step_texts']]
        self._bm25 = BM25Okapi(tokenized)
        self._tokenized = tokenized
        print(f"[HybridSearchEngine] BM25 인덱스 완료 ({len(tokenized)}개 스텝)")

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

        # 최종 점수
        # CPT 가중치를 낮게 유지: 같은 교과 단원이라도 코드 번호가 달라도
        # 개념적으로 동일한 유형이 존재하므로 BM25/벡터를 주 신호로 사용
        final = 0.15 * cpt_scores + 0.45 * bm25_norm + 0.40 * vec_scores
        final[q_idx] = -1.0   # 자기 자신 제외

        top_indices = np.argsort(final)[::-1][:top_k]

        results = []
        for idx in top_indices:
            results.append({
                'step_id':    int(step_ids[idx]),
                'problem_id': str(self.vec_data['problem_ids'][idx]),
                'step_number':int(self.vec_data['step_numbers'][idx]),
                'concept_id': str(self.vec_data['concept_ids'][idx]),
                'score':      round(float(final[idx]), 4),
                'bm25_score': round(float(bm25_norm[idx]), 4),
                'vec_score':  round(float(vec_scores[idx]), 4),
                'cpt_score':  round(float(cpt_scores[idx]), 4),
                'same_concept': bool(self.vec_data['concept_ids'][idx] == q_concept and q_concept != ''),
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
