import sqlite3
import json
import re
import os
import unicodedata
import subprocess
import numpy as np
import bleach as bleach_module
import markdown as markdown_module
import html as html_module
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory, send_file
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

app = Flask(__name__)
DB_FILE = 'kice_database.sqlite'
THUMBNAIL_DIR = os.path.join('static', 'thumbnails')
VECTORS_FILE = 'kice_step_vectors.npz'
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

# 오프라인 패키지 모드: 관리자 패널 및 오류 제보 기능 비활성화
OFFLINE_MODE = os.environ.get('OFFLINE_MODE', '0') == '1'

# ── 텍스트 임베딩 모델 및 벡터 인덱스 로드 ──────────────────────
print("[로딩 중] 한국어 문장 임베딩 모델...")
model = SentenceTransformer('dragonkue/BGE-m3-ko')
_vec_data = None

def load_vector_index():
    global _vec_data
    if os.path.exists(VECTORS_FILE):
        data = np.load(VECTORS_FILE, allow_pickle=True)
        _vec_data = {
            'step_ids':    data['step_ids'],
            'vectors':     data['vectors'],
            'concept_ids': data['concept_ids'],
            'problem_ids': data['problem_ids'],
            'step_numbers':data['step_numbers'],
            'step_texts':  data['step_texts'],
        }
        print(f"[벡터 인덱스 로드됨] {len(_vec_data['step_ids'])}개 스텝")
    else:
        print(f"[경고] {VECTORS_FILE} 없음. build_vectors.py를 실행하세요.")

load_vector_index()


def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html', offline_mode=OFFLINE_MODE)

@app.route('/pdf/<path:filename>')
def serve_pdf(filename):
    return send_from_directory('PDF_Ref', filename)

@app.route('/thumbnail/<problem_id>')
def serve_thumbnail(problem_id):
    # Normalize to NFC for consistent lookup
    problem_id = unicodedata.normalize('NFC', problem_id)
    thumb_path = os.path.join(THUMBNAIL_DIR, f'{problem_id}.png')
    if os.path.exists(thumb_path):
        return send_file(thumb_path, mimetype='image/png')
    return '', 404


@app.route('/api/similar_steps/<int:step_id>')
def similar_steps(step_id):
    if _vec_data is None:
        return jsonify({'error': '벡터 인덱스가 로드되지 않았습니다. build_vectors.py를 실행하세요.'}), 503

    top_n = int(request.args.get('top_n', 10))
    step_ids = _vec_data['step_ids']

    # 쿼리 스텝 인덱스 찾기
    matches = np.where(step_ids == step_id)[0]
    if len(matches) == 0:
        return jsonify({'error': f'step_id {step_id} 를 벡터 인덱스에서 찾을 수 없습니다.'}), 404
    q_idx = matches[0]

    q_vector = _vec_data['vectors'][q_idx:q_idx+1]  # (1, D)
    q_concept = _vec_data['concept_ids'][q_idx]

    # 코사인 유사도 계산 (벡터가 정규화되어 있으므로 내적 = 코사인)
    cos_sims = cosine_similarity(q_vector, _vec_data['vectors'])[0]  # (N,)

    # concept_id 일치 보너스 (0.0 or 0.5)
    concept_bonus = np.array([
        0.5 if (c == q_concept and q_concept != '') else 0.0
        for c in _vec_data['concept_ids']
    ], dtype=np.float32)

    # 하이브리드 점수 = 0.5 * cos_sim + 0.5 * concept_bonus (bonus는 0 또는 0.5이므로 총합 0~1 범위)
    hybrid_scores = 0.5 * cos_sims + concept_bonus

    # 자기 자신 제외 후 상위 top_n 정렬
    hybrid_scores[q_idx] = -1.0
    top_indices = np.argsort(hybrid_scores)[::-1][:top_n]

    # DB에서 추가 메타데이터 조회
    conn = get_db_connection()
    results = []
    for idx in top_indices:
        sid = int(step_ids[idx])
        row = conn.execute('''
            SELECT s.step_id, s.problem_id, s.step_number, s.step_title, s.action_concept_id,
                   c.standard_name, c.ref_code
            FROM steps s
            LEFT JOIN concepts c ON s.action_concept_id = c.id
            WHERE s.step_id = ?
        ''', (sid,)).fetchone()
        if row:
            results.append({
                'step_id': row['step_id'],
                'problem_id': row['problem_id'],
                'step_number': row['step_number'],
                'step_title': row['step_title'],
                'action_concept_id': row['action_concept_id'],
                'standard_name': row['standard_name'],
                'ref_code': row['ref_code'],
                'cos_similarity': round(float(cos_sims[idx]), 4),
                'hybrid_score': round(float(hybrid_scores[idx]), 4),
                'same_concept': bool(_vec_data['concept_ids'][idx] == q_concept and q_concept != ''),
            })
    conn.close()

    query_row = conn = get_db_connection()
    q_info = get_db_connection().execute(
        'SELECT step_title, action_concept_id, problem_id, step_number FROM steps WHERE step_id=?',
        (step_id,)
    ).fetchone()
    return jsonify({
        'query': {
            'step_id': step_id,
            'step_title': q_info['step_title'] if q_info else '',
            'action_concept_id': q_info['action_concept_id'] if q_info else '',
            'problem_id': q_info['problem_id'] if q_info else '',
            'step_number': q_info['step_number'] if q_info else 0,
        },
        'results': results
    })


@app.route('/api/stats')
def stats():
    conn = get_db_connection()
    stats_data = {}
    
    # Helper for exclusion logic
    def is_excluded_problem(year_val, filename):
        try:
            y_int = int(year_val)
        except:
            return False
        n = unicodedata.normalize('NFC', filename)
        if y_int >= 2022:
            return bool(re.search(r'[미기](2[3-9]|30)', n))
        elif 2017 <= y_int <= 2021:
            m = re.search(r'가_?(\d{1,2})', n)
            return bool(m and 1 <= int(m.group(1)) <= 30)
        elif y_int <= 2016:
            m = re.search(r'B_?(\d{1,2})', n)
            return bool(m and 1 <= int(m.group(1)) <= 30)
        return False
    
    # 1. PDF File Counts and Yearly Progress (Filtered)
    pdf_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'PDF_Ref')
    yearly_pdfs = {}
    total_pdfs = 0
    if os.path.exists(pdf_dir):
        for f in os.listdir(pdf_dir):
            if f.endswith('.pdf'):
                m = re.match(r'^(\d{4})', f)
                if m:
                    year = m.group(1)
                    if not is_excluded_problem(year, f):
                        total_pdfs += 1
                        yearly_pdfs[year] = yearly_pdfs.get(year, 0) + 1
    
    stats_data['total_pdfs'] = total_pdfs
    
    # 2. Analyzed Problems counting (Filtered)
    all_problems = conn.execute('SELECT problem_id, year FROM problems').fetchall()
    analyzed_filtered = [p for p in all_problems if not is_excluded_problem(p['year'], p['problem_id'])]
    stats_data['total_analyzed'] = len(analyzed_filtered)
    
    # 3. Yearly Analysis Status (Filtered)
    yearly_analyzed = {}
    for p in analyzed_filtered:
        y_str = str(p['year'])
        yearly_analyzed[y_str] = yearly_analyzed.get(y_str, 0) + 1
        
    # Combine into a sorted list
    progress_list = []
    # Use all years found in either PDFs or DB
    all_years = sorted(list(set(yearly_pdfs.keys()) | set(yearly_analyzed.keys())), reverse=True)
    for y in all_years:
        total = yearly_pdfs.get(y, 0)
        analyzed = yearly_analyzed.get(y, 0)
        percent = round((analyzed / total * 100), 1) if total > 0 else 0
        progress_list.append({
            'year': y,
            'total': total,
            'analyzed': analyzed,
            'percent': percent
        })
    
    stats_data['yearly_progress'] = progress_list
    
    # 4. Top Concepts and Pairs (Existing)
    stats_data['top_concepts'] = [dict(row) for row in conn.execute('''
        SELECT c.id, c.standard_name, c.ref_code, COUNT(*) as cnt 
        FROM steps s
        JOIN concepts c ON s.action_concept_id = c.id
        GROUP BY c.id ORDER BY cnt DESC LIMIT 5
    ''').fetchall()]
    
    stats_data['top_pairs'] = [dict(row) for row in conn.execute('''
        SELECT t.normalized_text as trigger_cat, c.standard_name, c.ref_code, COUNT(*) as cnt
        FROM triggers t
        JOIN step_triggers st ON t.trigger_id = st.trigger_id
        JOIN steps s ON st.step_id = s.step_id
        LEFT JOIN concepts c ON s.action_concept_id = c.id
        WHERE t.normalized_text != "" AND t.normalized_text != "[미분류 기타 조건]"
        GROUP BY t.normalized_text, s.action_concept_id
        ORDER BY cnt DESC LIMIT 7
    ''').fetchall()]
    
    conn.close()
    return jsonify(stats_data)

@app.route('/api/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"results": []})
        
    conn = get_db_connection()
    is_exact_code = query.startswith('CPT-') or (len(query) > 3 and query[0].isdigit() and ('모' in query or '수능' in query))

    if is_exact_code or _vec_data is None:
        # Fallback to pure DB LIKE search for Concept IDs or Problem IDs
        results = [dict(row) for row in conn.execute('''
            WITH matched_problems AS (
                SELECT DISTINCT p.problem_id
                FROM problems p
                JOIN steps s ON p.problem_id = s.problem_id
                LEFT JOIN step_triggers st ON s.step_id = st.step_id
                LEFT JOIN triggers t ON st.trigger_id = t.trigger_id
                LEFT JOIN concepts c ON s.action_concept_id = c.id
                WHERE t.trigger_text LIKE ? OR t.normalized_text LIKE ? OR c.standard_name LIKE ? OR s.action_concept_id LIKE ? OR c.ref_code LIKE ? OR s.step_title LIKE ? OR p.problem_id LIKE ?
            )
            SELECT s.step_id, s.problem_id, s.step_number, s.explanation_text, s.explanation_html,
                   (SELECT COUNT(*) FROM steps s2 WHERE s2.problem_id = s.problem_id) AS total_steps,
                   COALESCE(s.step_title, '') AS trigger_text, 
                   s.step_title,
                   '' AS normalized_text,
                   s.action_concept_id, 
                   c.standard_name, 
                   c.ref_code
            FROM steps s
            JOIN matched_problems mp ON s.problem_id = mp.problem_id
            LEFT JOIN concepts c ON s.action_concept_id = c.id
            ORDER BY s.problem_id DESC, s.step_number ASC
        ''', (f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()]
        conn.close()
        return jsonify({"results": results})
    
    # Semantic Search Flow
    q_vector = model.encode([query])[0]
    q_vector_norm = q_vector / np.linalg.norm(q_vector)
    
    # Calculate cosine similarity against all step vectors
    cos_sims = np.dot(_vec_data['vectors'], q_vector_norm)
    
    # Get indices sorted by similarity
    top_indices = np.argsort(cos_sims)[::-1]
    
    top_unique_probs = []
    seen_probs = set()
    prob_scores = {}
    
    for idx in top_indices:
        prob_id = str(_vec_data['problem_ids'][idx])
        score = round(float(cos_sims[idx]), 4)
        if prob_id not in seen_probs:
            seen_probs.add(prob_id)
            top_unique_probs.append(prob_id)
            prob_scores[prob_id] = {
                'cos_similarity': score,
                'match_step_id': int(_vec_data['step_ids'][idx])
            }
        if len(top_unique_probs) >= 20: 
            break
            
    if not top_unique_probs:
        conn.close()
        return jsonify({"results": []})
        
    placeholder = ','.join('?' for _ in top_unique_probs)
    rows = conn.execute(f'''
        SELECT s.step_id, s.problem_id, s.step_number, s.step_title, s.action_concept_id, s.explanation_text, s.explanation_html,
               c.standard_name, c.ref_code,
               (SELECT COUNT(*) FROM steps s2 WHERE s2.problem_id = s.problem_id) AS total_steps
        FROM steps s
        LEFT JOIN concepts c ON s.action_concept_id = c.id
        WHERE s.problem_id IN ({placeholder})
    ''', top_unique_probs).fetchall()
    
    results = []
    for row in rows:
        res_dict = dict(row)
        res_dict['trigger_text'] = row['step_title'] or ''
        
        pid = row['problem_id']
        res_score_dict = prob_scores.get(pid, {})
        res_dict['cos_similarity'] = res_score_dict.get('cos_similarity', 0.0)
        res_dict['hybrid_score'] = res_score_dict.get('cos_similarity', 0.0)
        res_dict['match_step_id'] = res_score_dict.get('match_step_id', None)
        res_dict['same_concept'] = False
        results.append(res_dict)
        
    results.sort(key=lambda r: (-r['cos_similarity'], r['step_number']))
    
    conn.close()
    return jsonify({"results": results})


@app.route('/api/steps_by_problems')
def steps_by_problems():
    """Return all steps for a given list of problem_ids (comma-separated).
    Used by the similar-steps main view to show all steps per problem."""
    prob_ids_str = request.args.get('ids', '')
    if not prob_ids_str:
        return jsonify({'results': []})

    prob_ids = [p.strip() for p in prob_ids_str.split(',') if p.strip()]
    if not prob_ids:
        return jsonify({'results': []})

    placeholders = ','.join('?' * len(prob_ids))
    conn = get_db_connection()
    rows = [dict(r) for r in conn.execute(f'''
        SELECT s.step_id, s.problem_id, s.step_number, s.explanation_text, s.explanation_html,
               (SELECT COUNT(*) FROM steps s2 WHERE s2.problem_id = s.problem_id) AS total_steps,
               COALESCE(s.step_title, '') AS trigger_text,
               s.step_title,
               s.action_concept_id,
               c.standard_name,
               c.ref_code
        FROM steps s
        LEFT JOIN concepts c ON s.action_concept_id = c.id
        WHERE s.problem_id IN ({placeholders})
        ORDER BY s.step_number ASC
    ''', prob_ids).fetchall()]
    conn.close()

    # Re-order rows so problem_ids appear in the original given order
    order = {pid: i for i, pid in enumerate(prob_ids)}
    rows.sort(key=lambda r: (order.get(r['problem_id'], 999), r['step_number']))
    return jsonify({'results': rows})

@app.route('/api/steps_by_concept')
def steps_by_concept():
    """concept_id(CPT-...)가 적용된 문항들의 모든 스텝을 반환.
    해당 성취기준을 가진 스텝만이 아니라, 그 문항의 전체 스텝을 반환한다."""
    concept_id = request.args.get('concept_id', '').strip()
    if not concept_id:
        return jsonify({'results': []})

    conn = get_db_connection()
    rows = conn.execute('''
        WITH matched_problems AS (
            SELECT DISTINCT problem_id FROM steps WHERE action_concept_id = ?
        )
        SELECT s.step_id, s.problem_id, s.step_number, s.explanation_text, s.explanation_html,
               (SELECT COUNT(*) FROM steps s2 WHERE s2.problem_id = s.problem_id) AS total_steps,
               COALESCE(s.step_title, '') AS trigger_text,
               s.step_title,
               s.action_concept_id,
               c.standard_name,
               c.ref_code
        FROM steps s
        JOIN matched_problems mp ON s.problem_id = mp.problem_id
        LEFT JOIN concepts c ON s.action_concept_id = c.id
        ORDER BY s.problem_id DESC, s.step_number ASC
    ''', (concept_id,)).fetchall()
    conn.close()

    return jsonify({'results': [dict(r) for r in rows]})

@app.route('/api/problem_answers', methods=['POST'])
def problem_answers():
    """주어진 problem_id 목록에 대해 Sol/ 폴더의 MD 파일을 읽어 정답을 추출하여 반환합니다."""
    data = request.get_json()
    problem_ids = data.get('problem_ids', [])
    if not problem_ids or not isinstance(problem_ids, list):
        return jsonify({'error': '유효하지 않은 problem_ids 목록입니다.'}), 400

    base_dir = os.path.dirname(os.path.abspath(__file__))
    answers = {}

    for pid in problem_ids:
        # 연도 폴더 유추
        year_match = re.match(r'^(\d{4})', pid)
        sol_path = None
        if year_match:
            year = year_match.group(1)
            candidate = os.path.join(base_dir, 'Sol', year, f'{pid}.md')
            if os.path.exists(candidate):
                sol_path = candidate
        
        if not sol_path:
            candidate = os.path.join(base_dir, 'Sol', f'{pid}.md')
            if os.path.exists(candidate):
                sol_path = candidate
        
        if not sol_path:
            answers[pid] = None
            continue
        
        try:
            with open(sol_path, 'r', encoding='utf-8') as f:
                content = f.read()
            matches = re.finditer(r'정답(?:은|:)?\s*(.+?)(?:입니다|번\s*입니다|번입니다|\.|\n|$)', content)
            found_ans = None
            for m in matches:
                ans_str = m.group(1).strip()
                # Clean up markdown styling, blockquote markers, and LaTeX dollar signs
                ans_str = re.sub(r'[\*\_>\$]+', '', ans_str).strip()
                
                if not ans_str:
                    continue
                
                # Extract digits inside parentheses: (5) -> 5
                paren_match = re.match(r'^\((\d)\)$', ans_str)
                if paren_match:
                    ans_str = paren_match.group(1)
                
                is_mcq = False
                if ans_str.endswith('번'):
                    ans_str = ans_str[:-1].strip()
                    is_mcq = True
                elif paren_match:
                    is_mcq = True
                
                # Check year and problem number for MCQ auto-conversion
                try:
                    year_val = 2022 # Default to current regime
                    year_extract = re.match(r'^(\d{4})', pid)
                    if year_extract:
                        year_val = int(year_extract.group(1))
                    
                    parts = pid.split('_')
                    if len(parts) >= 2:
                        num_part = ''.join(filter(str.isdigit, parts[-1]))
                        if num_part:
                            pnum = int(num_part)
                            if year_val >= 2022:
                                # 2022+ regime: Common (1-15 MCQ, 16-22 SA), Elective (23-28 MCQ, 29-30 SA)
                                if (1 <= pnum <= 15) or (23 <= pnum <= 28):
                                    is_mcq = True
                            else:
                                # Pre-2022 regime: 1-21 MCQ, 22-30 SA
                                if (1 <= pnum <= 21):
                                    is_mcq = True
                except:
                    pass
                
                if is_mcq:
                    # If it's an MCQ and we already have a circled number in the string (e.g. "① 65")
                    # just take the circled number part.
                    circled_match = re.search(r'([①②③④⑤])', ans_str)
                    if circled_match:
                        ans_str = circled_match.group(1)
                    elif ans_str in ['1', '2', '3', '4', '5']:
                        circled_map = {'1':'①', '2':'②', '3':'③', '4':'④', '5':'⑤'}
                        ans_str = circled_map[ans_str]
                
                if ans_str:
                    found_ans = ans_str

            answers[pid] = found_ans
        except Exception as e:
            app.logger.error(f"Error reading answer for {pid}: {e}")
            answers[pid] = None

    return jsonify({'answers': answers})


@app.route('/api/concepts_tree')

def concepts_tree():
    try:
        with open('concepts.json', 'r', encoding='utf-8') as f:
            concepts = json.load(f)
            
        tree = {}
        for c in concepts:
            ref = c.get('ref_code', '')
            if not ref: continue
            
            unit_full = c.get('curriculum_unit', '')
            if ' - ' in unit_full:
                parts = unit_full.split(' - ')
                raw_subj = parts[0].strip()
                unit_name = parts[-1].strip()
            else:
                raw_subj = '기타'
                unit_name = unit_full
                
            # Map raw subjects to display names
            if raw_subj.startswith('중학교 수학'):
                subject = '중학교 수학'
            elif raw_subj.startswith('공통수학'):
                subject = '공통수학'
            elif raw_subj == '대수':
                subject = '대수'
            elif raw_subj == '미적분Ⅰ':
                subject = '미적분I'
            elif raw_subj == '확률과 통계':
                subject = '확률과 통계'
            else:
                subject = raw_subj
                
            # Extract chapter number from ref_code if possible (e.g., [12대수01-02] -> 01)
            m = re.search(r'\[.+?(\d{2})-\d{2}\]', ref)
            chapter = m.group(1) if m else '00'
                
            combined_unit = f"{chapter}. {unit_name}"
            
            if subject not in tree:
                tree[subject] = {}
            if combined_unit not in tree[subject]:
                tree[subject][combined_unit] = []
                
            tree[subject][combined_unit].append({
                'id': c['id'],
                'ref_code': ref,
                'standard_name': c['standard_name']
            })
            
        return jsonify(tree)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

import ast
import operator
import shlex

def parse_and_evaluate_query(query, text, file_path):
    # This is a robust but simplified boolean evaluator.
    # To fully support arbitrary AND/OR/NOT/Grouping robustly without writing a full compiler frontend,
    # we can use a tokenizing approach and recursively evaluate.
    # For now, let's implement a capable subset:
    # 1. path: filter
    # 2. /regex/ filter
    # 3. "exact match"
    # 4. -NOT
    # 5. OR (|)
    # 6. implicit AND
    
    # Extract path filter
    path_filter = None
    path_match = re.search(r'path:(\S+)', query)
    if path_match:
        path_filter = path_match.group(1)
        query = query.replace(path_match.group(0), '')
        if path_filter.lower() not in file_path.lower():
            return False, []

    # Tokenize the remaining query
    try:
        # User might use quotes for exact match
        tokens = shlex.split(query)
    except ValueError:
        # Fallback if quotes are unbalanced
        tokens = query.split()
        
    if not tokens:
        return (True, []) if path_filter else (False, [])

    # We will collect 'highlights' (words/patterns that matched)
    highlights = set()

    # Simple evaluation:
    # If a token starts with '-', it must NOT be in text.
    # If tokens are joined by OR (or |), at least one must be in text.
    # Otherwise, all other (AND) tokens must be in text.
    
    # Group by ORs.
    # Actually, a proper boolean evaluator is complex. Let's do a simplified one:
    # Split by 'OR' or '|' into AND-groups.
    # "A B OR C -D" -> Group 1: ["A", "B"], Group 2: ["C", "-D"]
    # At least one AND-group must fully match.
    
    raw_groups = query.replace(' | ', ' OR ').split(' OR ')
    
    matched_any_group = False
    
    for r_group in raw_groups:
        try:
            g_tokens = shlex.split(r_group)
        except ValueError:
            g_tokens = r_group.split()
            
        group_match = True
        group_highlights = set()
        
        for token in g_tokens:
            is_not = token.startswith('-')
            term = token[1:] if is_not else token
            
            # Check for regex /.../
            is_regex = False
            if term.startswith('/') and term.endswith('/') and len(term) > 2:
                is_regex = True
                pattern = term[1:-1]
            
            term_found = False
            
            if is_regex:
                try:
                    matches = list(re.finditer(pattern, text))
                    if matches:
                        term_found = True
                        for m in matches:
                            group_highlights.add(m.group(0))
                except re.error:
                    pass # Invalid regex, ignore or treat as not found
            else:
                # Exact match or normal word
                if term in text:
                    term_found = True
                    group_highlights.add(term)
                    
            if is_not:
                if term_found:
                    group_match = False
                    break
            else:
                if not term_found:
                    group_match = False
                    break
                    
        if group_match and g_tokens:
            matched_any_group = True
            highlights.update(group_highlights)
            # We don't break early because we want to collect all possible highlights from OR groups if they also match
            
    if matched_any_group or (not tokens and path_filter):
        return True, list(highlights)
    return False, []

def strip_frontmatter(text):
    """YAML front matter(--- ... ---)와 Obsidian 이미지 링크(![[...]])를 제거하고
    실제 문제 본문만 반환합니다."""
    lines = text.splitlines(keepends=True)
    result_lines = []
    in_frontmatter = False
    frontmatter_done = False
    dashes_seen = 0

    for line in lines:
        stripped = line.strip()
        # YAML front matter: 파일 첫 줄이 --- 이면 블록 시작
        if not frontmatter_done:
            if stripped == '---':
                dashes_seen += 1
                in_frontmatter = not in_frontmatter
                if dashes_seen == 2:          # 닫는 --- 통과
                    frontmatter_done = True
                continue                       # --- 라인 자체는 제외
            elif in_frontmatter:
                continue                       # front matter 내부 키-값 제외
            else:
                frontmatter_done = True        # --- 가 없으면 front matter 없는 파일

        # Obsidian 이미지 링크: ![[파일명.pdf]] 형태 제외
        if stripped.startswith('![[') and stripped.endswith(']]'):
            continue

        result_lines.append(line)

    return ''.join(result_lines)

def extract_snippet(text, highlights, surround=50):
    if not highlights:
        return text[:100] + "..."
        
    # Find the earliest occurrence of any highlight
    earliest_idx = len(text)
    best_hl = ""
    for hl in highlights:
        idx = text.find(hl)
        if idx != -1 and idx < earliest_idx:
            earliest_idx = idx
            best_hl = hl
            
    if earliest_idx == len(text):
        return text[:100] + "..."
        
    start = max(0, earliest_idx - surround)
    end = min(len(text), earliest_idx + len(best_hl) + surround)
    
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
        
    # Apply <mark> tags
    for hl in highlights:
        # Simple string replace for highlighting.
        # Note: this might break if highlights overlap or contain HTML.
        snippet = snippet.replace(hl, f"<mark>{hl}</mark>")
        
    return snippet

@app.route('/api/search_expression', methods=['GET'])
def search_expression():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"count": 0, "results": []})
        
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MD_Ref')
    if not os.path.exists(base_dir):
        return jsonify({"error": "MD_Ref directory not found"}), 404

    matched_files = []

    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if not file.endswith('.md'):
                continue

            problem_id_str = unicodedata.normalize('NFC', file.replace('.md', ''))
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, base_dir)

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    raw_content = f.read()
            except Exception:
                continue

            # 메타데이터(front matter, 이미지 링크) 제거 후 실제 문제 본문만 검색
            searchable_content = strip_frontmatter(raw_content)

            is_match, highlights = parse_and_evaluate_query(query, searchable_content, rel_path)

            if is_match:
                snippet = extract_snippet(searchable_content, highlights)
                matched_files.append({
                    "problem_id": problem_id_str,
                    "file_path": rel_path,
                    "snippet": snippet,
                    "title": problem_id_str,
                    "highlights": highlights
                })

    return jsonify({
        "count": len(matched_files),
        "results": matched_files
    })

@app.route('/api/search_probid')
def search_probid():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"results": []})
        
    conn = get_db_connection()
    # Fetch all records since we need to do complex regex matching and the DB might be small enough.
    # Alternatively, we just fetch distinct problem_ids and do Python filtering.
    all_results = [dict(row) for row in conn.execute('''
        SELECT s.step_id, s.problem_id, s.step_number, s.explanation_text, s.explanation_html,
               (SELECT COUNT(*) FROM steps s2 WHERE s2.problem_id = s.problem_id) AS total_steps,
               COALESCE(s.step_title, '') AS trigger_text, 
               s.step_title,
               '' AS normalized_text,
               s.action_concept_id, 
               c.standard_name, 
               c.ref_code
        FROM steps s
        LEFT JOIN concepts c ON s.action_concept_id = c.id
        ORDER BY s.problem_id DESC, s.step_number ASC
    ''').fetchall()]
    conn.close()

    # Normalization helper
    def normalize_string(s):
        # Remove spaces, commas, "번", "학년도", "년" to make matching easier
        s = re.sub(r'[\s,번]', '', s)
        s = s.replace('학년도', '').replace('년', '')
        # Convert standalone 9월/6월 to 9모/6모
        s = s.replace('9월', '9모').replace('6월', '6모')
        # Map common shortened forms
        s = s.replace('확률과통계', '확').replace('확통', '확')
        s = s.replace('미적분', '미').replace('미적', '미')
        s = s.replace('기하', '기')
        s = s.replace('공통', '공')
        return s

    norm_query = normalize_string(query)

    def is_subsequence(sub, string):
        it = iter(string)
        return all(c in it for c in sub)

    matched_results = []

    for row in all_results:
        pid = row['problem_id']
        norm_pid = normalize_string(pid)

        # 쿼리가 순수 1~2자리 숫자(문항번호)인 경우: 마지막 _ 이후 숫자와 정확히 비교
        # 예) "30" or "30번"(→"30")이 "2023.수능_10"의 '3','0'에 잘못 매칭되는 것 방지
        if norm_query.isdigit() and len(norm_query) <= 2:
            last_part = norm_pid.rsplit('_', 1)[-1]  # e.g. "공30", "10", "미적28"
            trailing_num = re.search(r'(\d+)$', last_part)
            if trailing_num and trailing_num.group(1) == norm_query:
                matched_results.append(row)
        else:
            # 복합 쿼리(연도+시험+문항): 순서 포함 부분열 매칭
            if is_subsequence(norm_query, norm_pid):
                matched_results.append(row)

    return jsonify({"results": matched_results})

@app.route('/docs/search_rules')
def serve_search_rules():
    rules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Docs', 'search_rules.md')
    if os.path.exists(rules_path):
        with open(rules_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
            html_content = markdown.markdown(md_content, extensions=['fenced_code'])
            
            full_html = f'''
            <!DOCTYPE html>
            <html lang="ko">
            <head>
                <meta charset="UTF-8">
                <title>KICE 검색 규칙 가이드</title>
                <style>
                    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.6; padding: 2rem; max-width: 800px; margin: 0 auto; color: #333; }}
                    code {{ background: #f1f5f9; padding: 0.2rem 0.4rem; border-radius: 4px; font-family: monospace; color: #ef4444; }}
                    pre code {{ background: none; color: inherit; }}
                    pre {{ background: #f8fafc; padding: 1rem; border-radius: 8px; overflow-x: auto; }}
                    h1, h2, h3 {{ color: #0f172a; margin-top: 2rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.5rem; }}
                    a {{ color: #3b82f6; text-decoration: none; }}
                    a:hover {{ text-decoration: underline; }}
                    li {{ margin-bottom: 0.5rem; }}
                </style>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            '''
            return full_html
    return "문서를 찾을 수 없습니다.", 404

@app.route('/api/problem_steps', methods=['GET'])
def problem_steps():
    pid = request.args.get('pid', '').strip()
    pid = unicodedata.normalize('NFC', pid)
    if not pid:
        return jsonify({"error": "Missing pid parameter"}), 400
        
    conn = get_db_connection()
    try:
        rows = conn.execute('''
            SELECT s.step_id, s.step_number, s.step_title, s.action_concept_id, s.explanation_text, s.explanation_html,
                   c.standard_name, c.ref_code
            FROM steps s
            LEFT JOIN concepts c ON s.action_concept_id = c.id
            WHERE s.problem_id = ?
            ORDER BY s.step_number ASC
        ''', (pid,)).fetchall()
        
        steps = []
        for row in rows:
            steps.append({
                'step_id': row['step_id'],
                'step_number': row['step_number'],
                'step_title': row['step_title'],
                'explanation_text': row['explanation_text'],
                'explanation_html': row['explanation_html'],
                'action_concept_id': row['action_concept_id'],
                'standard_name': row['standard_name'],
                'ref_code': row['ref_code']
            })
            
        return jsonify({'problem_id': pid, 'steps': steps})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/problem_steps_bulk', methods=['POST'])
def problem_steps_bulk():
    """여러 problem_id의 스텝 해설을 한 번에 반환합니다."""
    data = request.get_json()
    problem_ids = data.get('problem_ids', [])
    if not problem_ids or not isinstance(problem_ids, list):
        return jsonify({'error': '유효하지 않은 problem_ids 목록입니다.'}), 400

    placeholders = ','.join('?' * len(problem_ids))
    conn = get_db_connection()
    try:
        rows = conn.execute(f'''
            SELECT s.problem_id, s.step_number, s.step_title,
                   s.explanation_html, s.explanation_text
            FROM steps s
            WHERE s.problem_id IN ({placeholders})
            ORDER BY s.problem_id, s.step_number ASC
        ''', problem_ids).fetchall()

        result = {}
        for row in rows:
            pid = row['problem_id']
            if pid not in result:
                result[pid] = []
            result[pid].append({
                'step_number':      row['step_number'],
                'step_title':       row['step_title'] or '',
                'explanation_html': row['explanation_html'] or row['explanation_text'] or ''
            })
        return jsonify({'steps': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# ── 공통 유틸 ────────────────────────────────────────────────────

ADMIN_KEY_FILE = 'admin.key'


def _load_admin_key():
    if os.path.exists(ADMIN_KEY_FILE):
        with open(ADMIN_KEY_FILE, 'r') as f:
            return f.read().strip()
    return None


def _check_admin_key():
    key = request.args.get('key') or request.headers.get('X-Admin-Key')
    expected = _load_admin_key()
    if not expected or key != expected:
        return False
    return True



def _get_sol_path(problem_id):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    m = re.match(r'^(\d{4})', problem_id)
    if m:
        candidate = os.path.join(base_dir, 'Sol', m.group(1), f'{problem_id}.md')
        if os.path.exists(candidate):
            return candidate
    candidate = os.path.join(base_dir, 'Sol', f'{problem_id}.md')
    return candidate if os.path.exists(candidate) else None


def _get_mdref_path(problem_id):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    m = re.match(r'^(\d{4})', problem_id)
    if m:
        candidate = os.path.join(base_dir, 'MD_Ref', m.group(1), f'{problem_id}.md')
        if os.path.exists(candidate):
            return candidate
    candidate = os.path.join(base_dir, 'MD_Ref', f'{problem_id}.md')
    return candidate if os.path.exists(candidate) else None


def _extract_step_block(md_content, step_number):
    """MD 내용에서 특정 step 블록 추출 (## [Step N] 부터 다음 ## [Step 또는 파일 끝까지)"""
    pattern = rf'(## \[Step {step_number}\][^\n]*\n.*?)(?=## \[Step \d+\]|\Z)'
    m = re.search(pattern, md_content, re.DOTALL)
    return m.group(1).rstrip() if m else None


def _parse_step_block(block):
    """step 블록에서 필드 추출 (build_db.py와 동일한 로직)"""
    step_title_m = re.match(r'## \[Step \d+\]([^\n]*)', block)
    step_title = step_title_m.group(1).strip() if step_title_m else ''

    trigger_m = re.search(r'- \*\*Trigger\*\*:\s*(.*?)\n- \*\*Action\*\*', block, re.DOTALL)
    action_m = re.search(r'- \*\*Action\*\*:\s*(?:\[(.*?)\])?\s*(.*?)\n- \*\*Result\*\*', block, re.DOTALL)
    result_m = re.search(r'- \*\*Result\*\*:\s*(.*?)\n>', block, re.DOTALL)
    if not all([trigger_m, action_m, result_m]):
        trigger_m = re.search(r'- \*\*Trigger\*\*:\s*(.*?)\n', block)
        action_m = re.search(r'- \*\*Action\*\*:\s*(?:\[(.*?)\])?\s*(.*?)\n', block)
        result_m = re.search(r'- \*\*Result\*\*:\s*(.*?)\n', block)

    action_concept_id = ''
    action_text = ''
    result_text = ''
    if action_m:
        action_concept_id = (action_m.group(1) or '').strip()
        action_text = re.sub(r'\s*\n\s*', ' ', (action_m.group(2) or '').strip())
    if result_m:
        result_text = re.sub(r'\s*\n\s*', ' ', result_m.group(1).strip())

    explanation_text = ''
    explanation_html = ''
    exp_m = re.search(r'> \*\*📝 해설.*?\n(.*)', block, re.DOTALL)
    if exp_m:
        exp_lines = exp_m.group(1).strip().split('\n')
        exp_lines = [l[2:] if l.startswith('> ') else (l[1:] if l.startswith('>') else l) for l in exp_lines]
        explanation_text = '\n'.join(exp_lines).strip()
        temp = explanation_text
        math_dict = {}
        counter = [0]

        def replacer(m):
            token = f'XMATH{counter[0]}X'
            math_dict[token] = m.group(0)
            counter[0] += 1
            return token

        temp = re.sub(r'(\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\$[^\$\n]+?\$|\\\([\s\S]*?\\\))', replacer, temp)
        parsed = markdown_module.markdown(temp, extensions=['nl2br'])
        for token, math_content in math_dict.items():
            parsed = parsed.replace(token, html_module.escape(math_content))
        allowed = ['b', 'i', 'strong', 'em', 'ul', 'li', 'br', 'p', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'blockquote']
        explanation_html = bleach_module.clean(parsed, tags=allowed)

    return {
        'step_title': step_title,
        'action_concept_id': action_concept_id,
        'action_text': action_text,
        'result_text': result_text,
        'explanation_text': explanation_text,
        'explanation_html': explanation_html,
    }

# ── 관리자 API ───────────────────────────────────────────────────

@app.route('/admin')
def admin_page():
    if OFFLINE_MODE:
        return '', 404
    if not _check_admin_key():
        return '접근 거부: 유효하지 않은 관리자 키입니다.', 403
    return render_template('admin.html')

@app.route('/api/admin/step_detail/<int:step_id>')
def admin_step_detail(step_id):
    if OFFLINE_MODE:
        return '', 404
    if not _check_admin_key():
        return jsonify({'error': '접근 거부'}), 403

    conn = get_db_connection()
    try:
        row = conn.execute('''
            SELECT s.step_id, s.problem_id, s.step_number, s.step_title,
                   s.explanation_text, s.explanation_html,
                   s.action_concept_id, s.action_text, s.result_text,
                   c.standard_name, c.ref_code
            FROM steps s
            LEFT JOIN concepts c ON s.action_concept_id = c.id
            WHERE s.step_id = ?
        ''', (step_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        return jsonify({'error': f'step_id {step_id} 없음'}), 404

    sol_path = _get_sol_path(row['problem_id'])
    sol_content = None
    raw_md = None
    if sol_path:
        with open(sol_path, 'r', encoding='utf-8') as f:
            sol_content = f.read()
        raw_md = _extract_step_block(sol_content, row['step_number'])

    mdref_path = _get_mdref_path(row['problem_id'])
    mdref_content = None
    if mdref_path:
        with open(mdref_path, 'r', encoding='utf-8') as f:
            mdref_content = f.read()

    return jsonify({
        'raw_md': raw_md or '',
        'sol_content': sol_content or '',
        'mdref_content': mdref_content or '',
        'db_row': {
            'step_title': row['step_title'] or '',
            'explanation_text': row['explanation_text'] or '',
            'explanation_html': row['explanation_html'] or '',
            'action_concept_id': row['action_concept_id'] or '',
            'standard_name': row['standard_name'] or '',
            'ref_code': row['ref_code'] or '',
        }
    })


@app.route('/api/double_cart', methods=['POST'])
def double_cart():
    """
    "더블" 기능: 카트의 각 문항에 대해 가장 유사한 쌍둥이 문항을 찾아 반환.
    - 유사도: 두 문항 사이에서 코사인 유사도 >= 0.85 인 스텝 쌍의 수
    - 동일 시험 회차 문항 제외 (예: 2026.6모_* 패턴)
    - 충돌 해소: 전체 쌍을 점수 내림차순 정렬 후 그리디 확정
    """
    if _vec_data is None:
        return jsonify({'error': '벡터 인덱스가 없습니다.'}), 503

    data = request.get_json()
    cart_ids = [str(pid) for pid in (data.get('problem_ids') or [])]
    if not cart_ids:
        return jsonify({'added': [], 'unmatched': []})

    COSINE_THRESHOLD = 0.85
    cart_set = set(cart_ids)

    # 시험 회차 접두어 추출 (e.g. "2026.6모", "2025수능", "2014.9모A")
    def exam_prefix(pid):
        # 마지막 _ 이전 부분 (문항번호 제거)
        return pid.rsplit('_', 1)[0]

    cart_prefixes = {exam_prefix(pid) for pid in cart_ids}

    # _vec_data 배열
    all_step_ids   = _vec_data['step_ids']    # (N,)
    all_vectors    = _vec_data['vectors']      # (N, D)
    all_prob_ids   = _vec_data['problem_ids']  # (N,) str

    # 원본 문항별 스텝 인덱스 맵
    def steps_for_prob(pid):
        return np.where(all_prob_ids == pid)[0]

    # 후보 문항 목록: 카트에 없고, 동일 시험 회차 아닌 문항들
    unique_candidate_pids = list({
        str(pid) for pid in all_prob_ids
        if str(pid) not in cart_set and exam_prefix(str(pid)) not in cart_prefixes
    })

    if not unique_candidate_pids:
        return jsonify({'added': [], 'unmatched': cart_ids})

    # 모든 (원본, 후보) 쌍의 매칭 점수 계산
    all_pairs = []  # (score, source_pid, candidate_pid)

    for src_pid in cart_ids:
        src_indices = steps_for_prob(src_pid)
        if len(src_indices) == 0:
            continue
        src_vecs = all_vectors[src_indices]  # (S, D)

        for cand_pid in unique_candidate_pids:
            cand_indices = steps_for_prob(cand_pid)
            if len(cand_indices) == 0:
                continue
            cand_vecs = all_vectors[cand_indices]  # (C, D)

            # 코사인 유사도 행렬: (S, C)
            sim_matrix = cosine_similarity(src_vecs, cand_vecs)

            # 원본의 각 스텝에 대해, 후보 스텝 중 >= THRESHOLD 인 것이 하나라도 있으면 "매칭"
            matched_src_steps = int(np.sum(np.any(sim_matrix >= COSINE_THRESHOLD, axis=1)))
            if matched_src_steps > 0:
                all_pairs.append((matched_src_steps, src_pid, cand_pid))

    # 점수 내림차순 정렬
    all_pairs.sort(key=lambda x: x[0], reverse=True)

    # 그리디 확정
    used_sources    = set()
    used_candidates = set()
    added           = []

    for score, src_pid, cand_pid in all_pairs:
        if src_pid in used_sources or cand_pid in used_candidates:
            continue
        used_sources.add(src_pid)
        used_candidates.add(cand_pid)
        added.append({'original': src_pid, 'match': cand_pid, 'score': score})

    unmatched = [pid for pid in cart_ids if pid not in used_sources]

    return jsonify({'added': added, 'unmatched': unmatched})


if __name__ == '__main__':
    # Run the Flask app on port 5050 to avoid conflicts
    app.run(host='0.0.0.0', port=5050, debug=False)
