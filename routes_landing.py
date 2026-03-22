"""
KICE Lynx 랜딩 서버
- 방문자 추적 (UUID 쿠키 + GeoIP)
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
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from flask import (Blueprint, g, jsonify, make_response, redirect,
                   render_template, request)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 메인 서비스 DB 파일 경로 (dashboard.py와 동기화)
MAIN_DB_FILE = os.path.join(BASE_DIR, 'kice_database.sqlite')

landing_bp = Blueprint('landing_bp', __name__)

DB_PATH = Path(__file__).parent / 'landing' / 'data.sqlite'
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'change-me')

VERSION = 'v2025.11'
DOWNLOAD_URLS = {
    'mac-arm64': f'https://github.com/yellowdalbie/KICEsentences/releases/download/{VERSION}/KICE_Lynx_{VERSION}_mac-arm64.zip',
    'mac-x86':   f'https://github.com/yellowdalbie/KICEsentences/releases/download/{VERSION}/KICE_Lynx_{VERSION}_mac-x86.zip',
    'windows':   f'https://github.com/yellowdalbie/KICEsentences/releases/download/{VERSION}/KICE_Lynx_{VERSION}_windows.zip',
}
FILE_SIZES = {
    'mac-arm64': '358.7 MB',
    'mac-x86': '363.3 MB',
    'windows': '344.0 MB',
}


# ── DB ──────────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS visits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            visitor_id  TEXT,
            ip          TEXT,
            country     TEXT,
            region      TEXT,
            city        TEXT,
            user_agent  TEXT,
            referer     TEXT,
            is_new      INTEGER DEFAULT 1,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS downloads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            visitor_id  TEXT,
            platform    TEXT,
            ip          TEXT,
            country     TEXT,
            city        TEXT,
            user_agent  TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS subscribers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE,
            visitor_id  TEXT,
            country     TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS error_reports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id  TEXT UNIQUE,
            status      TEXT DEFAULT 'reported',
            visitor_id  TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_visits_vid    ON visits(visitor_id);
        CREATE INDEX IF NOT EXISTS idx_visits_date   ON visits(created_at);
        CREATE INDEX IF NOT EXISTS idx_dl_date       ON downloads(created_at);
    ''')
    db.commit()
    db.close()

init_db()


# ── GeoIP (ip-api.com 무료, 등록 불필요) ────────────────────
def get_geo(ip: str) -> dict:
    try:
        url = f'http://ip-api.com/json/{ip}?fields=country,regionName,city'
        req = urllib.request.Request(url, headers={'User-Agent': 'KICE-Lynx-Landing/1.0'})
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def get_ip() -> str:
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()


# ── 방문자 추적 훅 ───────────────────────────────────────────
@landing_bp.before_app_request
def attach_visitor():
    vid = request.cookies.get('vid')
    g.is_new_visitor = vid is None
    g.visitor_id = vid or str(uuid.uuid4())


# ── 메인 페이지 ──────────────────────────────────────────────
@landing_bp.route('/')
def landing_index():
    db = get_db()
    ip = get_ip()
    geo = get_geo(ip)

    # 이전 방문 여부
    existing = db.execute(
        'SELECT id FROM visits WHERE visitor_id = ?', (g.visitor_id,)
    ).fetchone()

    db.execute(
        '''INSERT INTO visits (visitor_id, ip, country, region, city, user_agent, referer, is_new)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (g.visitor_id, ip,
         geo.get('country', ''), geo.get('regionName', ''), geo.get('city', ''),
         request.user_agent.string, request.referrer or '',
         1 if existing is None else 0)
    )
    db.commit()

    total_dl = db.execute('SELECT COUNT(*) FROM downloads').fetchone()[0]
    db.close()

    resp = make_response(render_template(
        'landing.html',
        total_downloads=total_dl,
        version=VERSION,
        file_sizes=FILE_SIZES,
    ))
    if g.is_new_visitor:
        resp.set_cookie('vid', g.visitor_id, max_age=60*60*24*365*2,
                        samesite='Lax', httponly=True)
    return resp


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
    ip = get_ip()
    geo = get_geo(ip)

    db.execute(
        '''INSERT INTO downloads (visitor_id, platform, ip, country, city, user_agent)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (g.visitor_id, platform, ip,
         geo.get('country', ''), geo.get('city', ''),
         request.user_agent.string)
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
                        'INSERT INTO error_reports (problem_id, visitor_id) VALUES (?, ?)',
                        (str(pid).strip(), g.visitor_id)
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
    key = data.get('key')
    if key != ADMIN_KEY:
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
    key = data.get('key')
    if key != ADMIN_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
        
    db = get_db()
    db.execute('DELETE FROM error_reports')
    db.commit()
    db.close()
    return jsonify({'status': 'ok'}), 200


# ── 관리자 대시보드 ──────────────────────────────────────────
@landing_bp.route('/admin')
def admin():
    if request.args.get('key') != ADMIN_KEY:
        return '401 Unauthorized', 401

    db = get_db()

    stats = {
        'total_visits':    db.execute('SELECT COUNT(*) FROM visits').fetchone()[0],
        'unique_visitors': db.execute('SELECT COUNT(DISTINCT visitor_id) FROM visits').fetchone()[0],
        'today_visits':    db.execute("SELECT COUNT(*) FROM visits WHERE date(created_at)=date('now', '+9 hours')").fetchone()[0],
        'today_unique':    db.execute("SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE date(created_at)=date('now', '+9 hours')").fetchone()[0],
        'subscribers':     0, # Will be updated from main DB
        'return_visitors': db.execute('SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE is_new=0').fetchone()[0],
    }

    # 메인 DB에서 가입된 사용자, 로그인 기록, 접속 기록 가져오기
    users = []
    login_logs = []
    access_logs = []
    total_users = 0
    if os.path.exists(MAIN_DB_FILE):
        try:
            main_conn = sqlite3.connect(MAIN_DB_FILE)
            main_conn.row_factory = sqlite3.Row
            users = main_conn.execute(
                'SELECT email, is_paid, created_at FROM users ORDER BY id DESC'
            ).fetchall()
            total_users = len(users)
            
            login_logs = main_conn.execute(
                'SELECT email, ip, user_agent, created_at FROM login_logs ORDER BY id DESC LIMIT 50'
            ).fetchall()
            
            access_logs = main_conn.execute(
                'SELECT ip, country, city, path, user_agent, created_at FROM access_logs ORDER BY id DESC LIMIT 100'
            ).fetchall()
            
            main_conn.close()
        except Exception as e:
            print(f"[Admin] Error fetching data from main DB: {e}")

    stats['subscribers'] = total_users # 기존 통계 항목 재활용 (UI 호환용)

    recent_dl = [] # 다운로드 기록은 더 이상 표시하지 않음

    country_stats = db.execute(
        '''SELECT country, COUNT(*) as cnt FROM visits
           WHERE country != "" GROUP BY country ORDER BY cnt DESC LIMIT 15'''
    ).fetchall()

    daily_stats = db.execute(
        '''SELECT date(created_at) as day, COUNT(*) as visits,
                  COUNT(DISTINCT visitor_id) as uniq
           FROM visits GROUP BY day ORDER BY day DESC LIMIT 14'''
    ).fetchall()

    daily_dl = [] # 다운로드 통계는 더 이상 표시하지 않음

    emails = db.execute(
        'SELECT email, country, created_at FROM subscribers ORDER BY id DESC'
    ).fetchall()

    errors = db.execute(
        "SELECT problem_id, status, created_at FROM error_reports ORDER BY id DESC"
    ).fetchall()

    db.close()

    return render_template(
        'admin.html',
        stats=stats,
        recent_dl=recent_dl,
        access_logs=access_logs, 
        country_stats=country_stats,
        daily_stats=daily_stats,
        emails=users, 
        login_logs=login_logs,
        errors=errors,
    )


# ── ping ────────────────────────────────────────────────────
@landing_bp.route('/ping')
def ping():
    return 'ok', 200


