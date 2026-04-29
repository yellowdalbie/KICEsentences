"""
KICE Lynx 랜딩 서버
- 방문자 추적 (방문 횟수 집계)
- 다운로드 기록 + GitHub Releases 리다이렉트
- 이메일 구독
- 관리자 대시보드

실행:
  ADMIN_KEY=your-secret python3 app.py

환경 변수:
  ADMIN_KEY  관리자 대시보드 접근 키 (기본: change-me)
  PORT       서버 포트 (기본: 8080)
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import (Blueprint, g, jsonify, make_response, redirect,
                   render_template, request, session)
import psutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 유저 데이터 DB 파일 경로 (dashboard.py와 동기화)
MAIN_DB_FILE = os.path.join(BASE_DIR, 'kice_userdata.sqlite')
# 문항/스텝 DB 파일 경로 (step 정보 룩업용)
KICE_DB_FILE = os.path.join(BASE_DIR, 'kice_database.sqlite')

landing_bp = Blueprint('landing_bp', __name__)

DB_PATH = Path(__file__).parent / 'landing' / 'data.sqlite'
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'change-me')

DOWNLOAD_TOKEN = 'XO0VLTwE_XYV6vehodDmzvgVj'
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'yellowsouls@naver.com').strip().lower()

def _check_admin_session():
    return session.get('email', '').strip().lower() == ADMIN_EMAIL

VERSION = 'v2025.11'
DOWNLOAD_URLS = {
    'mac-arm64': f'https://github.com/yellowdalbie/KICEsentences/releases/download/{VERSION}/THINK_LYNX_{VERSION}_mac-arm64.zip',
    'mac-x86':   f'https://github.com/yellowdalbie/KICEsentences/releases/download/{VERSION}/THINK_LYNX_{VERSION}_mac-x86.zip',
    'windows':   f'https://github.com/yellowdalbie/KICEsentences/releases/download/{VERSION}/THINK_LYNX_{VERSION}_windows.zip',
}
FILE_SIZES = {
    'mac-arm64': '358.7 MB',
    'mac-x86': '363.3 MB',
    'windows': '344.0 MB',
}
OFFLINE_MODE = os.environ.get('OFFLINE_MODE', '0') == '1'

def is_server_overloaded():
    if OFFLINE_MODE: return False
    try:
        if psutil.cpu_percent(interval=0.1) > 90.0: return True
        if psutil.virtual_memory().percent > 90.0: return True
    except Exception: pass
    return False


# ── DB ──────────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS visits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email  TEXT,
            created_at  TEXT DEFAULT (datetime('now', '+9 hours'))
        );
        CREATE TABLE IF NOT EXISTS downloads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            platform    TEXT,
            created_at  TEXT DEFAULT (datetime('now', '+9 hours'))
        );
        CREATE TABLE IF NOT EXISTS subscribers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE,
            created_at  TEXT DEFAULT (datetime('now', '+9 hours'))
        );
        CREATE TABLE IF NOT EXISTS error_reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id  TEXT UNIQUE,
            status      TEXT DEFAULT 'reported',
            created_at  TEXT DEFAULT (datetime('now', '+9 hours'))
        );
        CREATE TABLE IF NOT EXISTS portal_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT DEFAULT (datetime('now', '+9 hours'))
        );
        CREATE INDEX IF NOT EXISTS idx_visits_date   ON visits(created_at);
        CREATE INDEX IF NOT EXISTS idx_dl_date       ON downloads(created_at);
    ''')
    db.commit()
    # visits.user_email 컬럼 마이그레이션 (기존 DB 호환)
    try:
        db.execute('ALTER TABLE visits ADD COLUMN user_email TEXT')
        db.commit()
    except Exception:
        pass
    db.close()

init_db()




# ── 메인 페이지 ──────────────────────────────────────────────
@landing_bp.route('/')
def landing_index():
    db = get_db()
    user_email = session.get('user_email') or session.get('email') or None
    db.execute(
        "INSERT INTO visits (user_email, created_at) VALUES (?, datetime('now', '+9 hours'))",
        (user_email,)
    )
    db.commit()
    db.close()

    return render_template(
        'landing.html',
        version=VERSION,
        file_sizes=FILE_SIZES,
    )


# ── 다운로드 기록 + 리다이렉트 ──────────────────────────────
@landing_bp.route('/download/<path:platform>', strict_slashes=False)
def download(platform):
    orig_platform = platform
    platform = platform.lower().strip().strip('/')
    
    if platform not in DOWNLOAD_URLS:
        if 'win' in platform:
            platform = 'windows'
        elif 'mac' in platform or 'apple' in platform:
            platform = 'mac-arm64'
        else:
            return f'Not found. (Invalid target: {orig_platform})', 404

    db = get_db()
    db.execute(
        "INSERT INTO downloads (platform, created_at) VALUES (?, datetime('now', '+9 hours'))",
        (platform,)
    )
    db.commit()
    db.close()

    return redirect(DOWNLOAD_URLS[platform])





# ── 오류 신고 API ──────────────────────────────────────────
@landing_bp.route('/api/errors', methods=['GET', 'POST'])
def handle_errors():
    db = get_db()
    if request.method == 'GET':
        rows = db.execute("SELECT problem_id FROM error_reports WHERE status='reported'").fetchall()
        db.close()
        return jsonify({'errors': [r['problem_id'] for r in rows]}), 200
        
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        problem_ids = data.get('problem_ids', [])
        # Fallback for single legacy requests
        if 'problem_id' in data and data['problem_id']:
            problem_ids.append(data['problem_id'])
            
        if not problem_ids:
            db.close()
            return jsonify({'error': 'no problem_ids provided'}), 400
            
        try:
            for pid in problem_ids:
                try:
                    db.execute(
                        'INSERT INTO error_reports (problem_id) VALUES (?)',
                        (str(pid).strip(),)
                    )
                except sqlite3.IntegrityError:
                    pass # Skip duplicate records
            db.commit()
            return jsonify({'status': 'ok'}), 200
        finally:
            db.close()

@landing_bp.route('/api/errors/delete', methods=['POST'])
def delete_error():
    data = request.get_json(silent=True) or {}
    if not _check_admin_session():
        return jsonify({'error': 'Unauthorized'}), 401
        
    problem_id = data.get('problem_id', '').strip()
    if not problem_id:
        return jsonify({'error': 'no problem_id'}), 400
        
    db = get_db()
    db.execute('DELETE FROM error_reports WHERE problem_id=?', (problem_id,))
    db.commit()
    db.close()
    return jsonify({'status': 'ok'}), 200

@landing_bp.route('/api/errors/delete_all', methods=['POST'])
def delete_all_errors():
    data = request.get_json(silent=True) or {}
    if not _check_admin_session():
        return jsonify({'error': 'Unauthorized'}), 401
        
    db = get_db()
    db.execute('DELETE FROM error_reports')
    db.commit()
    db.close()
    return jsonify({'status': 'ok'}), 200


# ── 관리자: 사용자별 cart 로그 상세 조회 ──────────────────────
@landing_bp.route('/api/admin/user_cart_logs')
def admin_user_cart_logs():
    if not _check_admin_session():
        return jsonify({'error': 'Unauthorized'}), 401
    email = request.args.get('email', '').strip()
    event_type = request.args.get('event_type', '').strip()
    if not email or not event_type:
        return jsonify({'error': 'email and event_type required'}), 400
    if not os.path.exists(MAIN_DB_FILE):
        return jsonify({'logs': []})
    conn = sqlite3.connect(MAIN_DB_FILE)
    conn.row_factory = sqlite3.Row
    if event_type == 'open_preview':
        rows = conn.execute(
            '''SELECT id, event_type, problem_count, problem_ids, created_at
               FROM cart_logs WHERE user_email=? AND event_type IN ('open_preview','print_preview')
               ORDER BY id DESC LIMIT 100''',
            (email,)
        ).fetchall()
    else:
        rows = conn.execute(
            '''SELECT id, event_type, problem_count, problem_ids, created_at
               FROM cart_logs WHERE user_email=? AND event_type=?
               ORDER BY id DESC LIMIT 100''',
            (email, event_type)
        ).fetchall()
    conn.close()
    return jsonify({'logs': [dict(r) for r in rows]})


@landing_bp.route('/api/admin/visit_stats')
def admin_visit_stats():
    if not _check_admin_session():
        return jsonify({'error': 'Unauthorized'}), 401
    period = int(request.args.get('period', 14))
    gran = request.args.get('gran', 'day')  # hour | day | month

    if gran == 'hour':
        label_expr = "strftime('%Y-%m-%d %H:00', created_at)"
        date_filter = f"created_at >= datetime('now', '-{period} days')"
    elif gran == 'month':
        label_expr = "strftime('%Y-%m', created_at)"
        date_filter = f"created_at >= datetime('now', '-{period} days')"
    else:
        label_expr = "date(created_at, '-6 hours')"
        date_filter = f"date(created_at, '-6 hours') >= date('now', '-{period} days')"

    if not DB_PATH.exists():
        return jsonify([])
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    rows = db.execute(f'''
        SELECT {label_expr} as label,
               COUNT(*) as visits,
               COUNT(DISTINCT visitor_id) as uniq
        FROM visits
        WHERE {date_filter}
        GROUP BY label ORDER BY label
    ''').fetchall()
    db.close()
    return jsonify([{'label': r['label'], 'visits': r['visits'], 'uniq': r['uniq']} for r in rows])


# ── 관리자 대시보드 ──────────────────────────────────────────
@landing_bp.route('/admin')
def admin():
    if OFFLINE_MODE:
        return '', 404
    if is_server_overloaded():
        return redirect('/busy')
    if not _check_admin_session():
        return redirect('/')

    db = get_db()

    stats = {
        'total_visits':         db.execute('SELECT COUNT(*) FROM visits').fetchone()[0],
        'login_visits':         db.execute("SELECT COUNT(*) FROM visits WHERE user_email IS NOT NULL AND user_email != ''").fetchone()[0],
        'anon_visits':          db.execute("SELECT COUNT(*) FROM visits WHERE user_email IS NULL OR user_email = ''").fetchone()[0],
        'unique_visitors':      db.execute('SELECT COUNT(DISTINCT visitor_id) FROM visits').fetchone()[0],
        'login_unique':         db.execute("SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE user_email IS NOT NULL AND user_email != ''").fetchone()[0],
        'anon_unique':          db.execute("SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE user_email IS NULL OR user_email = ''").fetchone()[0],
        'today_visits':         db.execute("SELECT COUNT(*) FROM visits WHERE date(created_at, '-6 hours')=date('now', '+3 hours')").fetchone()[0],
        'today_login_visits':   db.execute("SELECT COUNT(*) FROM visits WHERE date(created_at, '-6 hours')=date('now', '+3 hours') AND user_email IS NOT NULL AND user_email != ''").fetchone()[0],
        'today_unique':         db.execute("SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE date(created_at, '-6 hours')=date('now', '+3 hours')").fetchone()[0],
        'today_login_unique':   db.execute("SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE date(created_at, '-6 hours')=date('now', '+3 hours') AND user_email IS NOT NULL AND user_email != ''").fetchone()[0],
        'subscribers':          0,
        'return_visitors':      db.execute('SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE is_new=0').fetchone()[0],
        'portal_visits':        db.execute('SELECT COUNT(*) FROM portal_logs').fetchone()[0],
        'search_totals':      {},
        'search_anon_totals': {},
        'top_concepts':    [],
        'top_expressions': [],
        'top_probids':     [],
        'top_units':       [],
        'top_steps':       [],
        'zero_result_concepts': [],
        'cart_totals':      {},
        'cart_anon_totals': {},
        'recent_cart_logs': [],
    }

    # 메인 DB에서 가입된 사용자, 로그인 기록 가져오기
    users = []
    login_logs = []
    total_users = 0
    stats['search_totals'] = {}

    if os.path.exists(MAIN_DB_FILE):
        try:
            main_conn = sqlite3.connect(MAIN_DB_FILE)
            main_conn.row_factory = sqlite3.Row
            users_raw = main_conn.execute(
                'SELECT id, email, is_paid, is_verified, created_at, last_seen_at, visit_count FROM users ORDER BY id DESC'
            ).fetchall()
            total_users = len(users_raw)

            # 사용자별 검색 유형별 횟수
            search_counts = {}
            for r in main_conn.execute(
                '''SELECT user_email, search_type, COUNT(*) as cnt
                   FROM search_stats WHERE user_email IS NOT NULL AND user_email != ""
                   GROUP BY user_email, search_type'''
            ).fetchall():
                search_counts.setdefault(r['user_email'], {})[r['search_type']] = r['cnt']

            # 사용자별 cart 이벤트 횟수
            cart_counts = {}
            for r in main_conn.execute(
                '''SELECT user_email, event_type, COUNT(*) as cnt
                   FROM cart_logs WHERE user_email IS NOT NULL AND user_email != ""
                   GROUP BY user_email, event_type'''
            ).fetchall():
                cart_counts.setdefault(r['user_email'], {})[r['event_type']] = r['cnt']

            # 풍부한 사용자 목록 구성
            users = []
            for u in users_raw:
                email = u['email']
                sc = search_counts.get(email, {})
                cc = cart_counts.get(email, {})
                users.append({
                    'email': email,
                    'is_paid': u['is_paid'],
                    'is_verified': u['is_verified'],
                    'created_at': u['created_at'] or '',
                    'last_login': u['last_seen_at'] or '',
                    'visit_count': u['visit_count'] or 0,
                    'search_concept':    sc.get('개념유사도', 0),
                    'search_expression': sc.get('기출표현', 0),
                    'search_probid':     sc.get('문항번호', 0),
                    'search_unit':       sc.get('성취기준', 0),
                    'print_preview':     cc.get('open_preview', 0),
                    'save_pdf':          cc.get('save_pdf', 0),
                })
            
            login_logs = main_conn.execute(
                'SELECT email, created_at FROM login_logs ORDER BY id DESC LIMIT 50'
            ).fetchall()
            
            # 검색 통계 — 로그인 사용자만 (가입 사용자 합계와 일치)
            search_rows = main_conn.execute(
                "SELECT search_type, COUNT(*) as cnt FROM search_stats "
                "WHERE user_email IS NOT NULL AND user_email != '' GROUP BY search_type"
            ).fetchall()
            stats['search_totals'] = { r['search_type']: r['cnt'] for r in search_rows }
            # 비로그인 검색 통계
            anon_search_rows = main_conn.execute(
                "SELECT search_type, COUNT(*) as cnt FROM search_stats "
                "WHERE user_email IS NULL OR user_email = '' GROUP BY search_type"
            ).fetchall()
            stats['search_anon_totals'] = { r['search_type']: r['cnt'] for r in anon_search_rows }
            
            # 인기 검색어 (유형별 Top 10) — step_id: 접두사 항목은 별도 테이블로
            stats['top_concepts'] = main_conn.execute('''
                SELECT query_text, COUNT(*) as cnt FROM search_stats
                WHERE search_type = '개념유사도' AND query_text IS NOT NULL AND query_text != ""
                  AND query_text NOT LIKE 'step_id:%'
                GROUP BY query_text ORDER BY cnt DESC LIMIT 10
            ''').fetchall()

            stats['top_expressions'] = main_conn.execute('''
                SELECT query_text, COUNT(*) as cnt FROM search_stats
                WHERE search_type = '기출표현' AND query_text IS NOT NULL AND query_text != ""
                GROUP BY query_text ORDER BY cnt DESC LIMIT 10
            ''').fetchall()

            stats['top_probids'] = main_conn.execute('''
                SELECT query_text, COUNT(*) as cnt FROM search_stats
                WHERE search_type = '문항번호' AND query_text IS NOT NULL AND query_text != ""
                GROUP BY query_text ORDER BY cnt DESC LIMIT 10
            ''').fetchall()

            # Top 성취기준 — concepts JOIN 제거 (다른 DB 파일이라 불가), 이름은 별도 룩업
            raw_units = [dict(r) for r in main_conn.execute('''
                SELECT query_text as concept_id, COUNT(*) as cnt
                FROM search_stats
                WHERE search_type = '성취기준' AND query_text IS NOT NULL
                GROUP BY query_text ORDER BY cnt DESC LIMIT 10
            ''').fetchall()]

            # 인기 Step 검색 (step_id:XXX 형식 항목) — 이름은 별도 룩업
            raw_top_steps = [dict(r) for r in main_conn.execute('''
                SELECT query_text, COUNT(*) as cnt FROM search_stats
                WHERE search_type = '개념유사도' AND query_text LIKE 'step_id:%'
                GROUP BY query_text ORDER BY cnt DESC LIMIT 10
            ''').fetchall()]

            # 0건 결과 검색어 (개념유사도, Top 10)
            stats['zero_result_concepts'] = main_conn.execute('''
                SELECT query_text, COUNT(*) as cnt FROM search_stats
                WHERE search_type = '개념유사도' AND result_count = 0
                  AND query_text IS NOT NULL AND query_text != ""
                  AND query_text NOT LIKE 'step_id:%' AND query_text NOT LIKE 'prob_id:%'
                GROUP BY query_text ORDER BY cnt DESC LIMIT 10
            ''').fetchall()

            # 장바구니/인쇄 이벤트 집계 — 로그인 사용자만 (가입 사용자 합계와 일치)
            cart_rows = main_conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM cart_logs "
                "WHERE user_email IS NOT NULL AND user_email != '' GROUP BY event_type"
            ).fetchall()
            stats['cart_totals'] = {r['event_type']: r['cnt'] for r in cart_rows}
            # 비로그인 이벤트 집계
            cart_anon_rows = main_conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM cart_logs "
                "WHERE user_email IS NULL OR user_email = '' GROUP BY event_type"
            ).fetchall()
            stats['cart_anon_totals'] = {r['event_type']: r['cnt'] for r in cart_anon_rows}

            # 최근 장바구니/인쇄 이벤트 (50건)
            stats['recent_cart_logs'] = main_conn.execute('''
                SELECT user_email, event_type, problem_count, problem_ids, created_at
                FROM cart_logs ORDER BY id DESC LIMIT 50
            ''').fetchall()

            main_conn.close()

            # ── kice_database.sqlite 에서 성취기준 이름 + Step 정보 룩업 ──
            if os.path.exists(KICE_DB_FILE):
                try:
                    kice_conn = sqlite3.connect(KICE_DB_FILE)
                    kice_conn.row_factory = sqlite3.Row

                    # top_units: standard_name 보완
                    top_units_result = []
                    for row in raw_units:
                        cid = row['concept_id']
                        name_row = kice_conn.execute(
                            'SELECT standard_name FROM concepts WHERE id=?', (cid,)
                        ).fetchone()
                        top_units_result.append({
                            'concept_id': cid,
                            'standard_name': name_row['standard_name'] if name_row else None,
                            'cnt': row['cnt'],
                        })
                    stats['top_units'] = top_units_result

                    # top_steps: step 정보 보완
                    top_steps_result = []
                    for row in raw_top_steps:
                        qt = row['query_text']   # "step_id:1336"
                        try:
                            step_id = int(qt.split(':', 1)[1])
                        except (ValueError, IndexError):
                            continue
                        step_row = kice_conn.execute(
                            'SELECT problem_id, step_number, step_title FROM steps WHERE step_id=?',
                            (step_id,)
                        ).fetchone()
                        top_steps_result.append({
                            'step_id': step_id,
                            'problem_id': step_row['problem_id'] if step_row else '?',
                            'step_number': step_row['step_number'] if step_row else '?',
                            'step_title': (step_row['step_title'] or '')[:45] if step_row else '(제목 없음)',
                            'cnt': row['cnt'],
                        })
                    stats['top_steps'] = top_steps_result

                    kice_conn.close()
                except Exception as e:
                    print(f"[Admin] kice_db lookup error: {e}")
                    # fallback: top_units without standard_name
                    stats['top_units'] = [
                        {'concept_id': r['concept_id'], 'standard_name': None, 'cnt': r['cnt']}
                        for r in raw_units
                    ]
            else:
                stats['top_units'] = [
                    {'concept_id': r['concept_id'], 'standard_name': None, 'cnt': r['cnt']}
                    for r in raw_units
                ]
        except Exception as e:
            print(f"[Admin] Error fetching data from main DB: {e}")

    stats['subscribers'] = total_users
    
    # 오류 신고 내역 가져오기
    errors = db.execute('SELECT * FROM error_reports ORDER BY id DESC').fetchall()

    daily_stats = db.execute(
        '''SELECT date(created_at, '-6 hours') as day, COUNT(*) as visits
           FROM visits GROUP BY day ORDER BY day DESC LIMIT 14'''
    ).fetchall()

    db.close()

    return render_template('admin.html', stats=stats, daily_stats=daily_stats, country_stats=[],
                           emails=users, login_logs=login_logs, errors=errors)


# ── 다운로드 전용 페이지 ─────────────────────────────────────
@landing_bp.route('/get/<token>')
def download_portal(token):
    if token != DOWNLOAD_TOKEN:
        return '', 404
    try:
        db = get_db()
        db.execute("INSERT INTO portal_logs (created_at) VALUES (datetime('now', '+9 hours'))")
        db.commit()
        db.close()
    except Exception:
        pass
    return render_template(
        'download_portal.html',
        version=VERSION,
        urls=DOWNLOAD_URLS,
        sizes=FILE_SIZES,
    )


# ── 개인정보처리방침 ─────────────────────────────────────────
@landing_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')


# ── 이용약관 ─────────────────────────────────────────────────
@landing_bp.route('/terms')
def terms():
    return render_template('terms.html')


# ── ping ────────────────────────────────────────────────────
@landing_bp.route('/ping')
def ping():
    return 'ok', 200


# ── SEO: Google Search Console 소유 확인 ────────────────────
@landing_bp.route('/google94e999ee1d56a815.html')
def google_site_verification():
    from flask import Response
    return Response('google-site-verification: google94e999ee1d56a815.html', mimetype='text/html')


# ── SEO: robots.txt ─────────────────────────────────────────
@landing_bp.route('/robots.txt')
def robots_txt():
    content = (
        'User-agent: *\n'
        'Allow: /\n'
        'Sitemap: https://www.thinklynx.xyz/sitemap.xml\n'
    )
    from flask import Response
    return Response(content, mimetype='text/plain')


# ── SEO: sitemap.xml ────────────────────────────────────────
@landing_bp.route('/sitemap.xml')
def sitemap_xml():
    content = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.thinklynx.xyz/</loc>
    <changefreq>monthly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>'''
    from flask import Response
    return Response(content, mimetype='application/xml')


