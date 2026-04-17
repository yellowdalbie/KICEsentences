import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# .env 로드 (다른 모듈 임포트 전에 실행하여 환경 변수 전파)
env_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.strip().split('=', 1)
                os.environ[k] = v.strip()

import sqlite3
import json
import re
import unicodedata
import subprocess
import numpy as np
import bleach as bleach_module
import markdown as markdown_module
import html as html_module
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory, send_file, session, redirect
from sklearn.metrics.pairwise import cosine_similarity
from werkzeug.security import generate_password_hash, check_password_hash
import psutil
app = Flask(__name__)
from routes_landing import landing_bp
app.register_blueprint(landing_bp)

app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

DB_FILE = os.path.join(BASE_DIR, 'kice_database.sqlite')
USER_DB_FILE = os.path.join(BASE_DIR, 'kice_userdata.sqlite')
THUMBNAIL_DIR = os.path.join(BASE_DIR, 'static', 'thumbnails')
VECTORS_FILE = os.path.join(BASE_DIR, 'kice_step_vectors.npz')
STEP_CLUSTERS_FILE = os.path.join(BASE_DIR, 'step_clusters.json')
TRIGGER_VECS_FILE = os.path.join(BASE_DIR, 'trigger_category_vectors.npz')
MD_REF_DIR = os.path.join(BASE_DIR, 'MD_Ref')
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

# 오프라인 패키지 모드: 관리자 패널 및 오류 제보 기능 비활성화
OFFLINE_MODE = os.environ.get('OFFLINE_MODE', '0') == '1'

# ── 벡터 인덱스 및 오프라인 쿼리 엔진 로드 ──────────────────────
_vec_data = None
_offline_query_engine = None

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


def load_offline_query_engine():
    global _offline_query_engine
    try:
        _offline_query_engine = OfflineQueryEngine()
    except FileNotFoundError as e:
        print(f"[경고] {e}")
        print("[경고] 개념유사도 검색은 build_query_vocab.py 실행 후 사용 가능합니다.")


def load_cluster_data():
    """step_clusters.json + trigger_category_vectors.npz 로드해 _vec_data에 주입"""
    global _vec_data
    if _vec_data is None:
        return

    # 클러스터 ID 배열 (이진 판별용, 폴백)
    if os.path.exists(STEP_CLUSTERS_FILE):
        with open(STEP_CLUSTERS_FILE, encoding='utf-8') as f:
            step_cluster_map = json.load(f)
        cluster_ids = np.array(
            [step_cluster_map.get(str(sid), -1) for sid in _vec_data['step_ids']],
            dtype=np.int32,
        )
        _vec_data['step_cluster_ids'] = cluster_ids
        n_clusters = len(set(cluster_ids[cluster_ids >= 0]))
        print(f"[클러스터 데이터 로드됨] {n_clusters}개 클러스터 / {(cluster_ids >= 0).sum()}개 스텝 매핑")

    # 트리거 카테고리 벡터 배열 (연속 유사도용)
    if os.path.exists(TRIGGER_VECS_FILE):
        tvec_data = np.load(TRIGGER_VECS_FILE, allow_pickle=True)
        tvec_step_ids = tvec_data['step_ids']       # (M,) int32
        tvec_vecs = tvec_data['step_trigger_vecs']  # (M, D) float32
        # _vec_data['step_ids'] 순서에 맞춰 정렬
        tvec_id_to_row = {int(sid): i for i, sid in enumerate(tvec_step_ids)}
        D = tvec_vecs.shape[1]
        step_trigger_vecs = np.zeros((len(_vec_data['step_ids']), D), dtype=np.float32)
        mapped = 0
        for i, sid in enumerate(_vec_data['step_ids']):
            row = tvec_id_to_row.get(int(sid))
            if row is not None:
                step_trigger_vecs[i] = tvec_vecs[row]
                mapped += 1
        _vec_data['step_trigger_vecs'] = step_trigger_vecs
        print(f"[트리거 벡터 로드됨] {mapped}개 스텝 매핑 (차원: {D})")


load_cluster_data()

# ── 하이브리드 검색 엔진 초기화 (벡터 인덱스 로드 후) ───────────────
from search_engine import HybridSearchEngine, ProblemSimilarity, OfflineQueryEngine
_search_engine = None
_problem_sim = None

load_offline_query_engine()

def load_search_engine():
    global _search_engine, _problem_sim
    if _vec_data is None:
        return
    _search_engine = HybridSearchEngine(_vec_data)
    _problem_sim = ProblemSimilarity(_vec_data)

load_search_engine()


def get_db_connection():
    """콘텐츠 DB (problems, steps, concepts 등) - git으로 관리"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def get_user_db():
    """유저 데이터 DB (users, logs, sets 등) - 서버 전용, git 미추적"""
    conn = sqlite3.connect(USER_DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT UNIQUE NOT NULL,
                  password_hash TEXT NOT NULL,
                  is_paid INTEGER DEFAULT 0,
                  display_name TEXT,
                  created_at DATETIME DEFAULT (datetime('now', '+9 hours')))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS login_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  email TEXT,
                  ip TEXT,
                  country TEXT,
                  city TEXT,
                  user_agent TEXT,
                  created_at DATETIME DEFAULT (datetime('now', '+9 hours')))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS access_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  ip TEXT,
                  country TEXT,
                  city TEXT,
                  user_agent TEXT,
                  path TEXT,
                  user_email TEXT,
                  created_at DATETIME DEFAULT (datetime('now', '+9 hours')))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS search_stats
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_email TEXT,
                  search_type TEXT,
                  query_text TEXT,
                  result_count INTEGER,
                  created_at DATETIME DEFAULT (datetime('now', '+9 hours')))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cart_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_email TEXT,
                  event_type TEXT,
                  problem_count INTEGER,
                  problem_ids TEXT,
                  created_at DATETIME DEFAULT (datetime('now', '+9 hours')))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS problem_sets (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        status       TEXT    NOT NULL DEFAULT 'final',
        title        TEXT    NOT NULL,
        problem_ids  TEXT    NOT NULL,
        print_config TEXT,
        is_favorite  INTEGER NOT NULL DEFAULT 0,
        source_query TEXT,
        created_at   DATETIME DEFAULT (datetime('now', '+9 hours')),
        updated_at   DATETIME DEFAULT (datetime('now', '+9 hours'))
    )''')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sets_user ON problem_sets(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sets_status ON problem_sets(user_id, status)")
    conn.commit()
    return conn

# (get_geo 기능이 제외되었습니다: 서버 부하 방지 및 접속 로그 간소화)

# 로그인 실패 횟수 추적 (IP별, 인메모리)
import time as _time
_login_fail_tracker = {}  # { ip: [timestamp, ...] }
_LOGIN_FAIL_LIMIT = 10    # 최대 실패 횟수
_LOGIN_FAIL_WINDOW = 600  # 10분 윈도우 (초)

def _check_login_rate_limit(ip):
    now = _time.time()
    timestamps = _login_fail_tracker.get(ip, [])
    # 윈도우 초과 항목 제거
    timestamps = [t for t in timestamps if now - t < _LOGIN_FAIL_WINDOW]
    _login_fail_tracker[ip] = timestamps
    return len(timestamps) >= _LOGIN_FAIL_LIMIT

def _record_login_fail(ip):
    _login_fail_tracker.setdefault(ip, []).append(_time.time())


@app.before_request
def csrf_protect():
    """CSRF 방어: 상태 변경 API 요청(POST/DELETE/PATCH/PUT)의 Origin/Referer 검증"""
    if request.method not in ('POST', 'DELETE', 'PATCH', 'PUT'):
        return
    if not request.path.startswith('/api/'):
        return
    origin = request.headers.get('Origin', '')
    referer = request.headers.get('Referer', '')
    host = request.host  # e.g. "158.180.90.73:5050" or "localhost:5050"
    # Origin 또는 Referer 중 하나가 같은 호스트여야 함
    allowed = origin.endswith(host) or referer.startswith(f'http://{host}') or referer.startswith(f'https://{host}')
    # 로컬호스트는 항상 허용 (오프라인 패키지 등)
    if not allowed and host.split(':')[0] not in ('127.0.0.1', 'localhost'):
        return jsonify({'error': '잘못된 요청입니다.'}), 403


# (log_access 기능이 제외되었습니다: 서버 부하 발생 요인 제거)
def log_search(search_type, query_text=None, result_count=None):
    email = session.get('user_email') or session.get('email')
    try:
        conn = get_user_db()
        conn.execute(
            'INSERT INTO search_stats (user_email, search_type, query_text, result_count) VALUES (?, ?, ?, ?)',
            (email, search_type, query_text, result_count)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging search: {e}")

# ── Authentication API ─────────────────────────────────────────

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    pw = data.get('password', '')
    if not email or not pw:
        return jsonify({'error': '이메일과 비밀번호를 입력해주세요.'}), 400
    if '@' not in email or '.' not in email:
        return jsonify({'error': '유효한 이메일 형식이 아닙니다.'}), 400
    if len(pw) < 6:
        return jsonify({'error': '비밀번호는 최소 6자리 이상이어야 합니다.'}), 400
        
    conn = get_user_db()
    user = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
    if user:
        conn.close()
        return jsonify({'error': '이미 가입된 이메일 계정입니다.'}), 400
        
    hashed_pw = generate_password_hash(pw)
    conn.execute('INSERT INTO users (email, password_hash, is_paid, created_at) VALUES (?, ?, ?, datetime("now", "+9 hours"))', (email, hashed_pw, 0))
    conn.commit()
    
    # 바로 로그인 처리
    user_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    
    session['user_id'] = user_id
    session['email'] = email
    session['is_paid'] = 0
    session.permanent = True
    
    return jsonify({'status': 'ok'}), 200

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    login_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    if _check_login_rate_limit(login_ip):
        return jsonify({'error': '로그인 시도가 너무 많습니다. 잠시 후 다시 시도해주세요.'}), 429

    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip().lower()
    pw = data.get('password', '')
    if not email or not pw:
        return jsonify({'error': '이메일과 비밀번호를 입력해주세요.'}), 400

    conn = get_user_db()
    user = conn.execute('SELECT id, email, password_hash, is_paid FROM users WHERE email=?', (email,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user['password_hash'], pw):
        _record_login_fail(login_ip)
        return jsonify({'error': '이메일 또는 비밀번호가 일치하지 않습니다.'}), 401
        
    session['user_id'] = user['id']
    session['email'] = user['email']
    session['is_paid'] = user['is_paid']
    session.permanent = True
    
    # 로그인 기록 저장
    try:
        login_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        login_geo = get_geo(login_ip)
        log_conn = get_user_db()
        log_conn.execute(
            'INSERT INTO login_logs (user_id, email, ip, country, city, user_agent, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime("now", "+9 hours"))',
            (user['id'], user['email'], login_ip, login_geo.get('country', ''), login_geo.get('city', ''), request.user_agent.string)
        )
        log_conn.commit()
        log_conn.close()
    except Exception as e:
        print(f"[LoginLog] Error: {e}")

    return jsonify({'status': 'ok', 'email': user['email'], 'is_paid': bool(user['is_paid'])}), 200

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'status': 'ok'}), 200

@app.route('/api/auth/change_password', methods=['POST'])
def auth_change_password():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    data = request.get_json() or {}
    new_password = data.get('new_password', '').strip()
    if len(new_password) < 6:
        return jsonify({'error': '비밀번호는 6자리 이상이어야 합니다.'}), 400
    hashed = generate_password_hash(new_password)
    conn = get_user_db()
    conn.execute('UPDATE users SET password_hash=? WHERE id=?', (hashed, session['user_id']))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'}), 200

@app.route('/api/auth/delete_account', methods=['POST'])
def auth_delete_account():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    user_id = session['user_id']
    conn = get_user_db()
    try:
        conn.execute('DELETE FROM users WHERE id=?', (user_id,))
        conn.execute('DELETE FROM login_logs WHERE user_id=?', (user_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f'[ERROR] 회원 탈퇴 오류: {e}')
        return jsonify({'error': '처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.'}), 500
    finally:
        conn.close()
    
    session.clear()
    return jsonify({'status': 'ok'}), 200

@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    if 'user_id' in session:
        # DB에서 최신 is_paid 상태 조회
        conn = get_user_db()
        user = conn.execute('SELECT is_paid, display_name FROM users WHERE id=?', (session['user_id'],)).fetchone()
        conn.close()
        if user:
            session['is_paid'] = user['is_paid']  # 세션 캐시 갱신
            email = session['email']
            display_name = user['display_name'] if user['display_name'] else email.split('@')[0]
            return jsonify({
                'isLoggedIn': True,
                'email': email,
                'isPaid': bool(user['is_paid']),
                'displayName': display_name
            }), 200

    return jsonify({'isLoggedIn': False, 'isPaid': False}), 200

# ─────────────────────────────────────────────────────────────

@app.route('/ping')
def ping():
    return 'ok', 200

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    if not OFFLINE_MODE:
        return jsonify({'error': 'not allowed'}), 403
    import threading
    def _stop():
        import time, os, signal
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)
    threading.Thread(target=_stop, daemon=True).start()
    return jsonify({'status': 'shutting down'})

def is_server_overloaded():
    if OFFLINE_MODE:
        return False
    try:
        if psutil.cpu_percent(interval=0.1) > 90.0:
            return True
        if psutil.virtual_memory().percent > 90.0:
            return True
    except Exception as e:
        print(f"[Overload Check Error] {e}")
    return False

@app.route('/app')
def app_index():
    if is_server_overloaded():
        return redirect('/busy')
    return render_template('index.html', offline_mode=OFFLINE_MODE)

@app.route('/busy')
def busy_page():
    return render_template('busy.html')

@app.route('/pdf/<path:filename>')
def serve_pdf(filename):
    safe = os.path.normpath(filename)
    if safe.startswith('..') or safe.startswith('/'):
        return '', 403
    return send_from_directory('PDF_Ref', safe)

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
    log_search('개념유사도', f'step_id:{step_id}')
    if _search_engine is None:
        return jsonify({'error': '검색 엔진이 초기화되지 않았습니다. build_vectors.py를 실행하세요.'}), 503

    top_n = int(request.args.get('top_n', 10))

    # 하이브리드 검색 (BM25 + CPT + 벡터)
    engine_result = _search_engine.search_steps(step_id, top_k=top_n)
    if 'error' in engine_result:
        return jsonify(engine_result), 404

    # DB에서 메타데이터 보강
    conn = get_db_connection()
    enriched = []
    for r in engine_result['results']:
        row = conn.execute('''
            SELECT s.step_id, s.problem_id, s.step_number, s.step_title, s.action_concept_id,
                   c.standard_name, c.id AS ref_code
            FROM steps s
            LEFT JOIN concepts c ON s.action_concept_id = c.id
            WHERE s.step_id = ?
        ''', (r['step_id'],)).fetchone()
        if row:
            enriched.append({
                'step_id':          row['step_id'],
                'problem_id':       row['problem_id'],
                'step_number':      row['step_number'],
                'step_title':       row['step_title'],
                'action_concept_id':row['action_concept_id'],
                'standard_name':    row['standard_name'],
                'ref_code':         row['ref_code'],
                'hybrid_score':     r['score'],
                'bm25_score':       r['bm25_score'],
                'vec_score':        r['vec_score'],
                'cpt_score':        r['cpt_score'],
                'same_concept':     r['same_concept'],
                # 하위 호환성 유지
                'cos_similarity':   r['vec_score'],
            })

    q_info = conn.execute(
        'SELECT step_title, action_concept_id, problem_id, step_number FROM steps WHERE step_id=?',
        (step_id,)
    ).fetchone()
    conn.close()

    return jsonify({
        'query': {
            'step_id':          step_id,
            'step_title':       q_info['step_title'] if q_info else '',
            'action_concept_id':q_info['action_concept_id'] if q_info else '',
            'problem_id':       q_info['problem_id'] if q_info else '',
            'step_number':      q_info['step_number'] if q_info else 0,
        },
        'results': enriched,
    })


@app.route('/api/similar_problems/<problem_id>')
def similar_problems(problem_id):
    log_search('개념유사도', f'prob_id:{problem_id}')
    """
    문항-레벨 유사도 검색.

    쿼리 파라미터:
      anchor_step_id (int): 검색을 유발한 스텝 ID (없으면 Step 1 사용)
      top_k (int): 반환할 최대 문항 수 (기본 10)
    """
    if _problem_sim is None:
        return jsonify({'error': '검색 엔진이 초기화되지 않았습니다.'}), 503

    anchor_step_id = int(request.args.get('anchor_step_id', 0))
    top_k = int(request.args.get('top_k', 10))

    # anchor_step_id가 없으면 해당 문항의 첫 번째 스텝 사용
    if anchor_step_id == 0:
        conn = get_db_connection()
        first_step = conn.execute(
            'SELECT step_id FROM steps WHERE problem_id=? ORDER BY step_number LIMIT 1',
            (problem_id,)
        ).fetchone()
        conn.close()
        if not first_step:
            return jsonify({'error': f'문항 {problem_id} 를 찾을 수 없습니다.'}), 404
        anchor_step_id = first_step['step_id']

    raw_results = _problem_sim.compare(problem_id, anchor_step_id, top_k=top_k)

    # DB에서 문항 메타데이터 보강
    conn = get_db_connection()
    enriched = []
    for r in raw_results:
        # 각 매칭 스텝에 c_step_title, q_step_title 추가
        for m in r['step_matches']:
            row_c = conn.execute(
                'SELECT step_title FROM steps WHERE step_id=?', (m['c_step_id'],)
            ).fetchone()
            m['c_step_title'] = row_c['step_title'] if row_c else ''

            row_q = conn.execute(
                'SELECT step_title FROM steps WHERE step_id=?', (m['q_step_id'],)
            ).fetchone()
            m['q_step_title'] = row_q['step_title'] if row_q else ''
        
        enriched.append(r)
    conn.close()

    return jsonify({
        'query_problem_id':  problem_id,
        'anchor_step_id':    anchor_step_id,
        'results':           enriched,
    })


_STATS_CACHE = {'timestamp': 0, 'data': None}

@app.route('/api/stats')
def stats():
    global _STATS_CACHE
    import time
    if time.time() - _STATS_CACHE['timestamp'] < 3600 and _STATS_CACHE['data']:
        return jsonify(_STATS_CACHE['data'])
        
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
        SELECT c.id, c.standard_name, c.id AS ref_code, COUNT(*) as cnt 
        FROM steps s
        JOIN concepts c ON s.action_concept_id = c.id
        GROUP BY c.id ORDER BY cnt DESC LIMIT 5
    ''').fetchall()]
    
    stats_data['top_pairs'] = [dict(row) for row in conn.execute('''
        SELECT t.normalized_text as trigger_cat, c.standard_name, c.id AS ref_code, COUNT(*) as cnt
        FROM triggers t
        JOIN step_triggers st ON t.trigger_id = st.trigger_id
        JOIN steps s ON st.step_id = s.step_id
        LEFT JOIN concepts c ON s.action_concept_id = c.id
        WHERE t.normalized_text != "" AND t.normalized_text != "[미분류 기타 조건]"
        GROUP BY t.normalized_text, s.action_concept_id
        ORDER BY cnt DESC LIMIT 7
    ''').fetchall()]
    
    conn.close()
    
    _STATS_CACHE['timestamp'] = time.time()
    _STATS_CACHE['data'] = stats_data
    return jsonify(stats_data)

@app.route('/api/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        log_search('개념유사도', query, result_count=0)
        return jsonify({"results": []})
        
    conn = get_db_connection()
    is_exact_code = bool(__import__('re').match(r'\d{1,2}[가-힣ⅠⅡ]', query)) or (len(query) > 3 and query[0].isdigit() and ('모' in query or '수능' in query))

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
                WHERE t.trigger_text LIKE ? OR t.normalized_text LIKE ? OR c.standard_name LIKE ? OR s.action_concept_id LIKE ? OR c.id LIKE ? OR s.step_title LIKE ? OR p.problem_id LIKE ?
            )
            SELECT s.step_id, s.problem_id, s.step_number, s.explanation_text, s.explanation_html,
                   (SELECT COUNT(*) FROM steps s2 WHERE s2.problem_id = s.problem_id) AS total_steps,
                   COALESCE(s.step_title, '') AS trigger_text,
                   s.step_title,
                   '' AS normalized_text,
                   s.action_concept_id,
                   c.standard_name,
                   c.id AS ref_code
            FROM steps s
            JOIN matched_problems mp ON s.problem_id = mp.problem_id
            LEFT JOIN concepts c ON s.action_concept_id = c.id
            ORDER BY s.problem_id DESC, s.step_number ASC
        ''', (f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()]
        conn.close()
        prob_count = len(set(r['problem_id'] for r in results))
        log_search('개념유사도', query, result_count=prob_count)
        return jsonify({"results": results})
    
    # Semantic Search Flow (오프라인 어휘 룩업)
    if _offline_query_engine is None:
        conn.close()
        return jsonify({"results": [], "error": "개념유사도 엔진 미초기화. build_query_vocab.py를 실행하세요."})

    cos_sims = _offline_query_engine.get_cos_sims(query)

    # Get indices sorted by similarity
    top_indices = np.argsort(cos_sims)[::-1]

    top_unique_probs = []
    seen_probs = set()
    prob_scores = {}

    for idx in top_indices:
        score = float(cos_sims[idx])
        if score < 0.15:   # 오프라인 엔진 분포 기준 하한
            break
        prob_id = str(_vec_data['problem_ids'][idx])
        if prob_id not in seen_probs:
            seen_probs.add(prob_id)
            top_unique_probs.append(prob_id)
            prob_scores[prob_id] = {
                'cos_similarity': round(score, 4),
                'match_step_id': int(_vec_data['step_ids'][idx])
            }
        if len(top_unique_probs) >= 100:   # 안전 상한
            break
            
    if not top_unique_probs:
        conn.close()
        return jsonify({"results": []})
        
    placeholder = ','.join('?' for _ in top_unique_probs)
    rows = conn.execute(f'''
        SELECT s.step_id, s.problem_id, s.step_number, s.step_title, s.action_concept_id, s.explanation_text, s.explanation_html,
               c.standard_name, c.id AS ref_code,
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
    log_search('개념유사도', query, result_count=len(top_unique_probs))
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
               c.id AS ref_code
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
    concept_id = request.args.get('concept_id', '').strip()
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
               c.id AS ref_code
        FROM steps s
        JOIN matched_problems mp ON s.problem_id = mp.problem_id
        LEFT JOIN concepts c ON s.action_concept_id = c.id
        ORDER BY s.problem_id DESC, s.step_number ASC
    ''', (concept_id,)).fetchall()
    result_list = [dict(r) for r in rows]
    prob_count = len(set(r['problem_id'] for r in result_list))
    log_search('성취기준', concept_id, result_count=prob_count)
    conn.close()

    return jsonify({'results': result_list})

@app.route('/api/problem_answers', methods=['POST'])
def problem_answers():
    """주어진 problem_id 목록에 대해 DB의 problems 테이블에서 정답을 읽어 반환합니다."""
    data = request.get_json()
    problem_ids = data.get('problem_ids', [])
    if not problem_ids or not isinstance(problem_ids, list):
        return jsonify({'error': '유효하지 않은 problem_ids 목록입니다.'}), 400

    answers = {}
    if not problem_ids:
        return jsonify({'answers': {}})

    try:
        conn = get_db_connection()
        # 정답 추출: SQL IN 절을 사용하여 대량 조회 최적화
        placeholders = ', '.join(['?'] * len(problem_ids))
        query = f"SELECT problem_id, answer FROM problems WHERE problem_id IN ({placeholders})"
        rows = conn.execute(query, problem_ids).fetchall()
        
        # 조회된 데이터 맵에 저장
        for pid, ans in rows:
            answers[pid] = ans
        conn.close()
            
        # 조회되지 않은 ID들은 None(null)으로 채움
        for pid in problem_ids:
            if pid not in answers:
                answers[pid] = None
                
    except Exception as e:
        app.logger.error(f"Error reading answers from DB: {e}")
        # 오류 발생 시 빈 결과 반환
        for pid in problem_ids:
            answers[pid] = None

    return jsonify({'answers': answers})


@app.route('/api/concepts_tree')

def concepts_tree():
    try:
        with open('concepts.json', 'r', encoding='utf-8') as f:
            concepts = json.load(f)
            
        tree = {}
        for c in concepts:
            ref = c.get('id', '')
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

            # Extract chapter number from id (e.g., 12대수03-02 -> 03, 12미적Ⅰ-01-04 -> 01)
            m = re.search(r'(\d{2})-\d{2}', ref)
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

def compile_query(query):
    path_filter = None
    path_match = re.search(r'path:(\S+)', query)
    if path_match:
        path_filter = path_match.group(1)
        query = query.replace(path_match.group(0), '')

    try:
        tokens = shlex.split(query)
    except ValueError:
        tokens = query.split()

    if not tokens:
        return {'path_filter': path_filter, 'groups': [], 'has_tokens': False}

    raw_groups = query.replace(' | ', ' OR ').split(' OR ')
    parsed_groups = []
    
    for r_group in raw_groups:
        try:
            g_tokens = shlex.split(r_group)
        except ValueError:
            g_tokens = r_group.split()
            
        group_terms = []
        for token in g_tokens:
            is_not = token.startswith('-')
            term = token[1:] if is_not else token
            is_regex = False
            regex_obj = None
            if term.startswith('/') and term.endswith('/') and len(term) > 2:
                is_regex = True
                pattern = term[1:-1]
                try:
                    regex_obj = re.compile(pattern)
                except re.error:
                    pass
            group_terms.append({
                'is_not': is_not,
                'term': term,
                'is_regex': is_regex,
                'regex_obj': regex_obj
            })
        if group_terms:
            parsed_groups.append(group_terms)

    return {'path_filter': path_filter, 'groups': parsed_groups, 'has_tokens': True}

def evaluate_compiled_query(compiled, text, file_path):
    path_filter = compiled['path_filter']
    if path_filter and path_filter.lower() not in file_path.lower():
        return False, []
        
    if not compiled['has_tokens']:
        return (True, []) if path_filter else (False, [])

    highlights = set()
    matched_any_group = False

    for group_terms in compiled['groups']:
        group_match = True
        group_highlights = set()
        
        for term_info in group_terms:
            term_found = False
            if term_info['is_regex']:
                if term_info['regex_obj']:
                    matches = list(term_info['regex_obj'].finditer(text))
                    if matches:
                        term_found = True
                        for m in matches:
                            group_highlights.add(m.group(0))
            else:
                if term_info['term'] in text:
                    term_found = True
                    group_highlights.add(term_info['term'])
                    
            if term_info['is_not']:
                if term_found:
                    group_match = False
                    break
            else:
                if not term_found:
                    group_match = False
                    break
                    
        if group_match and group_terms:
            matched_any_group = True
            highlights.update(group_highlights)

    if matched_any_group or (not compiled['has_tokens'] and path_filter):
        return True, list(highlights)
    return False, []

def parse_and_evaluate_query(query, text, file_path):
    compiled = compile_query(query)
    return evaluate_compiled_query(compiled, text, file_path)

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

_MD_REF_CACHE = None

def load_md_ref_cache():
    global _MD_REF_CACHE
    if _MD_REF_CACHE is not None:
        return
    _MD_REF_CACHE = {}
    if not os.path.exists(MD_REF_DIR):
        print(f"[경고] MD_Ref 디렉토리가 없습니다: {MD_REF_DIR}")
        return
    
    count = 0
    for root, dirs, files in os.walk(MD_REF_DIR):
        for file in files:
            if not file.endswith('.md'):
                continue
            problem_id_str = unicodedata.normalize('NFC', file.replace('.md', ''))
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, MD_REF_DIR)
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    raw_content = f.read()
            except Exception:
                continue
                
            searchable_content = strip_frontmatter(raw_content)
            _MD_REF_CACHE[problem_id_str] = {
                'rel_path': rel_path,
                'searchable_content': searchable_content
            }
            count += 1
    print(f"[MD_Ref 캐시 로드됨] {count}개 파일")

# 서버 구동 시 1회 로드하여 캐싱
load_md_ref_cache()


def _find_latex_regions(text):
    """원본 텍스트(원시 문자열)에서 LaTeX 블록의 (start, end) 목록을 반환."""
    regions = []
    # Display: $$...$$
    for m in re.finditer(r'\$\$[\s\S]*?\$\$', text):
        regions.append((m.start(), m.end()))
    # Display: \[...\]
    for m in re.finditer(r'\\\[[\s\S]*?\\\]', text):
        regions.append((m.start(), m.end()))
    # Inline: $...$ (단, $$ 내부 제외)
    for m in re.finditer(r'(?<!\$)\$(?!\$)[^\n$]+?\$(?!\$)', text):
        if not any(rs <= m.start() < re for rs, re in regions):
            regions.append((m.start(), m.end()))
    regions.sort(key=lambda r: r[0])
    return regions


def extract_snippet(text, highlights, surround=80):
    """검색 하이라이트 주변 텍스트를 추출하여 HTML-safe snippet 반환.

    - LaTeX 블록 경계까지 snippet을 확장해 불완전한 수식을 방지
    - HTML 특수문자(<, >, &)를 이스케이프한 후 <mark> 삽입
    - 결과 HTML을 innerHTML에 직접 설정해도 안전하며 KaTeX가 정상 렌더링 가능
    """
    if not highlights:
        return html_module.escape(text[:150]) + "..."

    # 1) 가장 빠른 하이라이트 위치 탐색
    earliest_idx = len(text)
    best_hl = ""
    for hl in highlights:
        idx = text.find(hl)
        if idx != -1 and idx < earliest_idx:
            earliest_idx = idx
            best_hl = hl

    if earliest_idx == len(text):
        return html_module.escape(text[:150]) + "..."

    # 2) 기본 범위 설정
    start = max(0, earliest_idx - surround)
    end = min(len(text), earliest_idx + len(best_hl) + surround)

    # 3) LaTeX 블록 경계까지 확장 (블록 중간에서 잘리지 않도록)
    regions = _find_latex_regions(text)
    for rs, re_end in regions:
        if rs < start < re_end:   # 시작점이 블록 내부 → 블록 시작으로 후퇴
            start = rs
        if rs < end < re_end:     # 끝점이 블록 내부 → 블록 끝으로 전진
            end = re_end
        if start <= rs and re_end <= end:
            pass  # 블록 전체가 이미 포함
        elif rs >= start and rs < end and re_end > end:
            end = re_end  # 블록이 끝점 너머로 열려 있으면 닫힘까지 포함

    start = max(0, start)
    end = min(len(text), end)

    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    raw_snippet = text[start:end]

    # 4) snippet 안의 LaTeX 영역 재계산 (offset 반영)
    snippet_regions = _find_latex_regions(raw_snippet)

    def in_latex_region(pos, length):
        return any(rs <= pos and pos + length <= re_end
                   for rs, re_end in snippet_regions)

    # 5) 텍스트를 LaTeX / 비-LaTeX 세그먼트로 분리
    segments = []  # (raw_text, is_latex)
    cursor = 0
    for rs, re_end in snippet_regions:
        if cursor < rs:
            segments.append((raw_snippet[cursor:rs], False))
        segments.append((raw_snippet[rs:re_end], True))
        cursor = re_end
    if cursor < len(raw_snippet):
        segments.append((raw_snippet[cursor:], False))

    # 6) 각 세그먼트별 처리:
    #    - 비-LaTeX: HTML 이스케이프 후 <mark> 삽입
    #    - LaTeX: HTML 이스케이프만 (mark 삽입 안 함)
    result_parts = []
    for seg_text, is_latex in segments:
        escaped = html_module.escape(seg_text)
        if is_latex:
            result_parts.append(escaped)
        else:
            for hl in highlights:
                escaped_hl = html_module.escape(hl)
                escaped = escaped.replace(
                    escaped_hl,
                    f'<mark>{escaped_hl}</mark>'
                )
            result_parts.append(escaped)

    return prefix + ''.join(result_parts) + suffix

@app.route('/api/search_expression', methods=['GET'])
def search_expression():
    query = request.args.get('q', '').strip()
    if not query:
        log_search('기출표현', query, result_count=0)
        return jsonify({"count": 0, "results": []})
        
    global _MD_REF_CACHE
    if _MD_REF_CACHE is None:
        load_md_ref_cache()
        
    if not _MD_REF_CACHE:
        return jsonify({"error": f"MD_Ref cache is empty or not found"}), 404

    matched_files = []
    
    # 컴파일된 쿼리를 생성 (루프 외부에서 1회 수행)
    compiled_q = compile_query(query)

    for problem_id_str, md_data in _MD_REF_CACHE.items():
        rel_path = md_data['rel_path']
        searchable_content = md_data['searchable_content']

        is_match, highlights = evaluate_compiled_query(compiled_q, searchable_content, rel_path)

        if is_match:
            snippet = extract_snippet(searchable_content, highlights)
            matched_files.append({
                "problem_id": problem_id_str,
                "file_path": rel_path,
                "snippet": snippet,
                "title": problem_id_str,
                "highlights": highlights
            })

    log_search('기출표현', query, result_count=len(matched_files))
    return jsonify({
        "count": len(matched_files),
        "results": matched_files
    })

@app.route('/api/search_probid')
def search_probid():
    query = request.args.get('q', '').strip()
    if not query:
        log_search('문항번호', query, result_count=0)
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
               c.id AS ref_code
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

    # Data from DB
    db_matched_pids = set(r['problem_id'] for r in matched_results)

    # Search in MD_Ref cache for problems that match the logic but are missing from DB
    global _MD_REF_CACHE
    if _MD_REF_CACHE is None:
        load_md_ref_cache()
        
    if _MD_REF_CACHE:
        for pid in _MD_REF_CACHE.keys():
            if pid in db_matched_pids:
                continue
            
            norm_pid = normalize_string(pid)
            is_match = False
            
            if norm_query.isdigit() and len(norm_query) <= 2:
                last_part = norm_pid.rsplit('_', 1)[-1]
                trailing_num = re.search(r'(\d+)$', last_part)
                if trailing_num and trailing_num.group(1) == norm_query:
                    is_match = True
            else:
                if is_subsequence(norm_query, norm_pid):
                    is_match = True
                    
            if is_match:
                db_matched_pids.add(pid)
                matched_results.append({
                    'step_id': None,
                    'problem_id': pid,
                    'step_number': '',
                    'explanation_text': "",
                    'explanation_html': "",
                    'total_steps': 1,
                    'trigger_text': "2028 수능 수학의 출제범위가 아닌 문항에 대해서는 해설과 정답을 제공하지 않습니다.",
                    'step_title': "",
                    'action_concept_id': '',
                    'standard_name': '',
                    'ref_code': ''
                })

    prob_count = len(db_matched_pids)
    log_search('문항번호', query, result_count=prob_count)
    return jsonify({"results": matched_results})

@app.route('/docs/search_rules')
def serve_search_rules():
    rules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Docs', 'search_rules.md')
    if os.path.exists(rules_path):
        with open(rules_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
            html_content = markdown_module.markdown(md_content, extensions=['fenced_code', 'tables'])
            
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
                    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; table-layout: fixed; }}
                    th {{ background: #f1f5f9; text-align: left; padding: 0.5rem 0.75rem; border: 1px solid #e2e8f0; font-weight: 600; }}
                    th:first-child, td:first-child {{ width: 35%; }}
                    th:last-child, td:last-child {{ width: 65%; }}
                    td {{ padding: 0.5rem 0.75rem; border: 1px solid #e2e8f0; vertical-align: top; word-break: break-all; }}
                    td:first-child {{ font-family: "Courier New", Courier, monospace; font-size: 0.92em; color: #ef4444; background: #fff5f5; }}
                    td:last-child {{ font-family: "Georgia", "Noto Serif KR", serif; color: #475569; }}
                    em {{ font-style: normal; }}
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
                   c.standard_name, c.id AS ref_code
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
        with open(ADMIN_KEY_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return None


def _check_admin_key():
    import hmac
    key = request.args.get('key') or request.headers.get('X-Admin-Key')
    expected = _load_admin_key()
    if not expected or not key:
        return False
    return hmac.compare_digest(key, expected)



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
    m = re.match(r'^(\d{4})', problem_id)
    if m:
        candidate = os.path.join(MD_REF_DIR, m.group(1), f'{problem_id}.md')
        if os.path.exists(candidate):
            return candidate
    candidate = os.path.join(MD_REF_DIR, f'{problem_id}.md')
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
                   c.standard_name, c.id AS ref_code
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


@app.route('/api/log_event', methods=['POST'])
def log_event():
    if OFFLINE_MODE:
        return jsonify({'status': 'ok'}), 200
    data = request.get_json(silent=True) or {}
    event_type = data.get('event_type', '').strip()
    problem_ids = data.get('problem_ids', [])
    if not event_type:
        return jsonify({'error': 'event_type required'}), 400
    email = session.get('user_email') or session.get('email')
    try:
        conn = get_user_db()
        conn.execute(
            'INSERT INTO cart_logs (user_email, event_type, problem_count, problem_ids) VALUES (?, ?, ?, ?)',
            (email, event_type, len(problem_ids), ','.join(str(p) for p in problem_ids))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[log_event] Error: {e}")
    return jsonify({'status': 'ok'}), 200


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

    # 더블 기능 사용 로그
    try:
        email = session.get('user_email') or session.get('email')
        conn = get_user_db()
        conn.execute(
            'INSERT INTO cart_logs (user_email, event_type, problem_count, problem_ids) VALUES (?, ?, ?, ?)',
            (email, 'double_cart', len(cart_ids), ','.join(cart_ids))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[double_cart log] Error: {e}")

    return jsonify({'added': added, 'unmatched': unmatched})


# ── 문항지 세트 기능 ──────────────────────────────────────────────

def _generate_set_title(problem_ids):
    """problem_ids 배열로부터 자동 세트 명칭 생성"""
    if not problem_ids:
        return '문항 세트'
    try:
        conn = get_db_connection()
        placeholders = ','.join('?' for _ in problem_ids)
        rows = conn.execute(f'''
            SELECT s.action_concept_id
            FROM steps s
            WHERE s.problem_id IN ({placeholders})
              AND s.action_concept_id IS NOT NULL
        ''', problem_ids).fetchall()
        conn.close()

        # 성취기준 분류 집계
        from collections import Counter
        cpt_counter = Counter()
        for row in rows:
            cid = row['action_concept_id'] or ''
            if 'CA1' in cid:
                cpt_counter['미적분Ⅰ'] += 1
            elif 'STA' in cid:
                cpt_counter['확률과통계'] += 1
            elif 'ALG' in cid:
                cpt_counter['대수'] += 1
            elif 'CM1' in cid or 'CM2' in cid:
                cpt_counter['공통수학'] += 1
            elif 'MID' in cid:
                cpt_counter['중학수학'] += 1

        subject = cpt_counter.most_common(1)[0][0] if cpt_counter else '혼합'

        # 난이도 힌트 (문항번호 기준)
        nums = []
        for pid in problem_ids:
            try:
                n = int(pid.rsplit('_', 1)[-1])
                nums.append(n)
            except:
                pass
        difficulty = ''
        if nums:
            high_count = sum(1 for n in nums if n >= 21)
            low_count = sum(1 for n in nums if n <= 15)
            if high_count > len(nums) / 2:
                difficulty = ' 고난도'
            elif low_count > len(nums) / 2:
                difficulty = ' 기본'

        return f'{subject}{difficulty} {len(problem_ids)}문항'
    except:
        return f'{len(problem_ids)}문항 세트'


@app.route('/api/sets/auto_title')
def sets_auto_title():
    if OFFLINE_MODE:
        return jsonify({'title': '문항 세트'})
    ids_str = request.args.get('ids', '').strip()
    if not ids_str:
        return jsonify({'title': '문항 세트'})
    problem_ids = [x.strip() for x in ids_str.split(',') if x.strip()]
    title = _generate_set_title(problem_ids)
    return jsonify({'title': title})


@app.route('/api/sets/temp', methods=['POST'])
def sets_save_temp():
    if OFFLINE_MODE:
        return jsonify({'status': 'ok'})
    if 'user_id' not in session:
        return jsonify({'error': '로그인 필요'}), 401
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    problem_ids = data.get('problem_ids', [])
    title = data.get('title', '문항 세트')
    source_query = data.get('source_query')
    if not problem_ids:
        return jsonify({'error': '문항 없음'}), 400
    import json as json_module
    conn = get_user_db()
    conn.execute("DELETE FROM problem_sets WHERE user_id=? AND status='temp'", (user_id,))
    cursor = conn.execute(
        "INSERT INTO problem_sets (user_id, status, title, problem_ids, source_query) VALUES (?, 'temp', ?, ?, ?)",
        (user_id, title, json_module.dumps(problem_ids, ensure_ascii=False), source_query)
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'id': new_id})


@app.route('/api/sets/restore', methods=['GET'])
def sets_restore():
    if OFFLINE_MODE:
        return jsonify({'has_temp': False})
    if 'user_id' not in session:
        return jsonify({'has_temp': False})
    user_id = session['user_id']
    import json as json_module
    conn = get_user_db()
    row = conn.execute(
        "SELECT id, title, problem_ids, created_at FROM problem_sets WHERE user_id=? AND status='temp'",
        (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({'has_temp': False})
    return jsonify({
        'has_temp': True,
        'id': row['id'],
        'title': row['title'],
        'problem_ids': json_module.loads(row['problem_ids']),
        'created_at': row['created_at']
    })


@app.route('/api/sets/restore', methods=['DELETE'])
def sets_delete_temp():
    if OFFLINE_MODE:
        return jsonify({'status': 'ok'})
    if 'user_id' not in session:
        return jsonify({'error': '로그인 필요'}), 401
    user_id = session['user_id']
    conn = get_user_db()
    conn.execute("DELETE FROM problem_sets WHERE user_id=? AND status='temp'", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/sets/final', methods=['POST'])
def sets_save_final():
    if OFFLINE_MODE:
        return jsonify({'status': 'ok'})
    if 'user_id' not in session:
        return jsonify({'error': '로그인 필요'}), 401
    user_id = session['user_id']
    data = request.get_json(silent=True) or {}
    problem_ids = data.get('problem_ids', [])
    title = (data.get('title') or '').strip() or '문항 세트'
    source_query = data.get('source_query')
    if not problem_ids:
        return jsonify({'error': '문항 없음'}), 400
    import json as json_module
    ids_json = json_module.dumps(problem_ids, ensure_ascii=False)
    conn = get_user_db()
    # 기존 temp 레코드를 final로 승격
    existing = conn.execute(
        "SELECT id FROM problem_sets WHERE user_id=? AND status='temp'",
        (user_id,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE problem_sets SET status='final', title=?, problem_ids=?, updated_at=datetime('now','+9 hours') WHERE id=?",
            (title, ids_json, existing['id'])
        )
        new_id = existing['id']
    else:
        cursor = conn.execute(
            "INSERT INTO problem_sets (user_id, status, title, problem_ids, source_query) VALUES (?, 'final', ?, ?, ?)",
            (user_id, title, ids_json, source_query)
        )
        new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'id': new_id})


@app.route('/api/sets/my')
def sets_my():
    if OFFLINE_MODE:
        return jsonify({'sets': []})
    if 'user_id' not in session:
        return jsonify({'error': '로그인 필요'}), 401
    user_id = session['user_id']
    import json as json_module
    conn = get_user_db()
    rows = conn.execute(
        "SELECT id, status, title, problem_ids, is_favorite, created_at FROM problem_sets WHERE user_id=? ORDER BY is_favorite DESC, updated_at DESC",
        (user_id,)
    ).fetchall()
    conn.close()
    sets = []
    for row in rows:
        try:
            ids = json_module.loads(row['problem_ids'])
            count = len(ids)
        except:
            count = 0
        sets.append({
            'id': row['id'],
            'status': row['status'],
            'title': row['title'],
            'problem_count': count,
            'is_favorite': row['is_favorite'],
            'created_at': row['created_at'][:16] if row['created_at'] else ''
        })
    return jsonify({'sets': sets})


@app.route('/api/sets/<int:set_id>', methods=['GET'])
def sets_get(set_id):
    if OFFLINE_MODE:
        return jsonify({'error': 'not available'}), 404
    if 'user_id' not in session:
        return jsonify({'error': '로그인 필요'}), 401
    user_id = session['user_id']
    import json as json_module
    conn = get_user_db()
    row = conn.execute(
        "SELECT id, status, title, problem_ids, is_favorite, created_at FROM problem_sets WHERE id=? AND user_id=?",
        (set_id, user_id)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': '없음'}), 404
    return jsonify({
        'id': row['id'],
        'status': row['status'],
        'title': row['title'],
        'problem_ids': json_module.loads(row['problem_ids']),
        'is_favorite': row['is_favorite'],
        'created_at': row['created_at'][:16] if row['created_at'] else ''
    })


@app.route('/api/sets/<int:set_id>', methods=['DELETE'])
def sets_delete(set_id):
    if OFFLINE_MODE:
        return jsonify({'status': 'ok'})
    if 'user_id' not in session:
        return jsonify({'error': '로그인 필요'}), 401
    user_id = session['user_id']
    conn = get_user_db()
    conn.execute("DELETE FROM problem_sets WHERE id=? AND user_id=?", (set_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})


@app.route('/api/sets/<int:set_id>/favorite', methods=['PATCH'])
def sets_toggle_favorite(set_id):
    if OFFLINE_MODE:
        return jsonify({'is_favorite': 0})
    if 'user_id' not in session:
        return jsonify({'error': '로그인 필요'}), 401
    user_id = session['user_id']
    conn = get_user_db()
    conn.execute(
        "UPDATE problem_sets SET is_favorite=CASE WHEN is_favorite=1 THEN 0 ELSE 1 END, updated_at=datetime('now','+9 hours') WHERE id=? AND user_id=?",
        (set_id, user_id)
    )
    conn.commit()
    row = conn.execute("SELECT is_favorite FROM problem_sets WHERE id=?", (set_id,)).fetchone()
    conn.close()
    return jsonify({'is_favorite': row['is_favorite'] if row else 0})


@app.route('/api/users/display_name', methods=['PATCH'])
def update_display_name():
    if 'user_id' not in session:
        return jsonify({'error': '로그인 필요'}), 401
    data = request.get_json(silent=True) or {}
    display_name = (data.get('display_name') or '').strip()
    if len(display_name) > 20:
        return jsonify({'error': '별칭은 최대 20자입니다.'}), 400
    conn = get_user_db()
    conn.execute(
        "UPDATE users SET display_name=? WHERE id=?",
        (display_name or None, session['user_id'])
    )
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok', 'display_name': display_name or None})


if __name__ == '__main__':
    host = os.environ.get('KICE_HOST', '127.0.0.1')
    port = int(os.environ.get('KICE_PORT', '5050'))
    app.run(host=host, port=port, debug=False)
