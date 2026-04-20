import os
import sqlite3
from datetime import datetime
from flask import Blueprint, jsonify, request, session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOARD_DB_FILE = os.path.join(BASE_DIR, 'kice_board.sqlite')
USER_DB_FILE  = os.path.join(BASE_DIR, 'kice_userdata.sqlite')
ADMIN_EMAIL   = os.environ.get('ADMIN_EMAIL', 'yellowsouls@naver.com').strip().lower()

board_bp = Blueprint('board', __name__)


# ── DB 초기화 ──────────────────────────────────────────────────────
def get_board_db():
    conn = sqlite3.connect(BOARD_DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS posts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            type        TEXT    NOT NULL CHECK(type IN ('notice','edit','question','error')),
            title       TEXT    NOT NULL,
            content     TEXT,
            author_id   INTEGER,
            author_email TEXT,
            is_anonymous INTEGER NOT NULL DEFAULT 0,
            pinned      INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','+9 hours')),
            updated_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS post_problems (
            post_id     INTEGER NOT NULL,
            problem_id  TEXT    NOT NULL,
            order_idx   INTEGER NOT NULL,
            PRIMARY KEY (post_id, problem_id),
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS post_problem_ref (
            post_id     INTEGER NOT NULL,
            problem_id  TEXT    NOT NULL,
            PRIMARY KEY (post_id, problem_id),
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS post_likes (
            post_id     INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','+9 hours')),
            PRIMARY KEY (post_id, user_id),
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS comments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id     INTEGER NOT NULL,
            parent_id   INTEGER,
            author_id   INTEGER NOT NULL,
            author_email TEXT,
            is_anonymous INTEGER NOT NULL DEFAULT 0,
            content     TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','+9 hours')),
            FOREIGN KEY (post_id)   REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_id) REFERENCES comments(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_posts_type    ON posts(type);
        CREATE INDEX IF NOT EXISTS idx_posts_pinned  ON posts(pinned);
        CREATE INDEX IF NOT EXISTS idx_likes_user    ON post_likes(user_id);
        CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
    ''')
    conn.commit()
    return conn


# ── 헬퍼 ──────────────────────────────────────────────────────────
def _current_user():
    """세션에서 user_id, email, is_verified, is_admin 반환. 없으면 None."""
    uid = session.get('user_id')
    if not uid:
        return None
    email = session.get('email', '').strip().lower()
    return {
        'id': uid,
        'email': email,
        'is_verified': bool(session.get('is_verified', False)),
        'is_admin': email == ADMIN_EMAIL,
    }


def _require_verified(user):
    """인증 회원이 아니면 에러 dict 반환."""
    if not user:
        return {'error': 'login_required', 'message': '로그인이 필요합니다.'}, 401
    if not user['is_verified']:
        return {'error': 'verify_required', 'message': '이메일 인증이 필요합니다.'}, 403
    return None


def _display_name(author_id, author_email, is_anonymous):
    """게시물 표시 작성자명 반환."""
    if is_anonymous:
        return '익명'
    if author_id:
        try:
            uconn = sqlite3.connect(USER_DB_FILE)
            uconn.row_factory = sqlite3.Row
            row = uconn.execute('SELECT display_name FROM users WHERE id=?', (author_id,)).fetchone()
            uconn.close()
            if row and row['display_name']:
                return row['display_name']
        except Exception:
            pass
    if author_email:
        return author_email.split('@')[0]
    return '알 수 없음'


def _like_count(conn, post_id):
    return conn.execute('SELECT COUNT(*) FROM post_likes WHERE post_id=?', (post_id,)).fetchone()[0]


def _user_liked(conn, post_id, user_id):
    if not user_id:
        return False
    return bool(conn.execute(
        'SELECT 1 FROM post_likes WHERE post_id=? AND user_id=?', (post_id, user_id)
    ).fetchone())


def _serialize_post(conn, row, user_id=None, include_problems=False):
    author_name = _display_name(row['author_id'], row['author_email'], row['is_anonymous'])
    d = {
        'id': row['id'],
        'type': row['type'],
        'title': row['title'],
        'content': row['content'],
        'author_name': author_name,
        'is_anonymous': bool(row['is_anonymous']),
        'pinned': bool(row['pinned']),
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'like_count': _like_count(conn, row['id']),
        'user_liked': _user_liked(conn, row['id'], user_id),
        'is_own': (user_id is not None and user_id == row['author_id']),
    }
    if include_problems:
        if row['type'] == 'edit':
            probs = conn.execute(
                'SELECT problem_id FROM post_problems WHERE post_id=? ORDER BY order_idx',
                (row['id'],)
            ).fetchall()
            d['problem_ids'] = [r['problem_id'] for r in probs]
        elif row['type'] in ('question', 'error'):
            refs = conn.execute(
                'SELECT problem_id FROM post_problem_ref WHERE post_id=?', (row['id'],)
            ).fetchall()
            d['problem_ids'] = [r['problem_id'] for r in refs]
        else:
            d['problem_ids'] = []
    return d


# ── 게시글 목록 ────────────────────────────────────────────────────
@board_bp.route('/api/board/posts', methods=['GET'])
def board_list():
    user = _current_user()
    uid = user['id'] if user else None

    filter_type = request.args.get('type', 'all')   # all|edit|question|error|liked
    page = max(1, int(request.args.get('page', 1)))
    per_page = 30
    offset = (page - 1) * per_page

    conn = get_board_db()
    try:
        # 공지 목록 (항상 포함, pinned=1)
        notices = conn.execute(
            'SELECT * FROM posts WHERE pinned=1 ORDER BY created_at DESC'
        ).fetchall()

        if filter_type == 'liked':
            if not uid:
                liked_posts = []
                others = []
            else:
                liked_ids = [r['post_id'] for r in conn.execute(
                    'SELECT post_id FROM post_likes WHERE user_id=?', (uid,)
                ).fetchall()]
                if liked_ids:
                    ph = ','.join('?' * len(liked_ids))
                    liked_posts = conn.execute(
                        f'SELECT * FROM posts WHERE id IN ({ph}) AND pinned=0 ORDER BY created_at DESC',
                        liked_ids
                    ).fetchall()
                else:
                    liked_posts = []
                others = conn.execute(
                    'SELECT p.* FROM posts p '
                    'JOIN (SELECT post_id, COUNT(*) as cnt FROM post_likes GROUP BY post_id) lc '
                    'ON p.id=lc.post_id WHERE p.pinned=0 ORDER BY lc.cnt DESC, p.created_at DESC '
                    'LIMIT ? OFFSET ?', (per_page, offset)
                ).fetchall()
            posts_section = {
                'notices': [_serialize_post(conn, r, uid) for r in notices],
                'liked': [_serialize_post(conn, r, uid) for r in liked_posts],
                'others': [_serialize_post(conn, r, uid) for r in others],
                'mode': 'liked',
            }
        else:
            if filter_type in ('edit', 'question', 'error'):
                where = 'WHERE pinned=0 AND type=?'
                params = (filter_type, per_page, offset)
            else:
                where = 'WHERE pinned=0'
                params = (per_page, offset)
            rows = conn.execute(
                f'SELECT * FROM posts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?',
                params
            ).fetchall()
            total = conn.execute(
                f'SELECT COUNT(*) FROM posts {where.replace("LIMIT ? OFFSET ?","")}',
                params[:-2] if filter_type in ('edit','question','error') else ()
            ).fetchone()[0]
            posts_section = {
                'notices': [_serialize_post(conn, r, uid) for r in notices],
                'posts': [_serialize_post(conn, r, uid) for r in rows],
                'total': total,
                'page': page,
                'per_page': per_page,
                'mode': filter_type,
            }
        return jsonify(posts_section)
    finally:
        conn.close()


# ── 게시글 생성 ────────────────────────────────────────────────────
@board_bp.route('/api/board/posts', methods=['POST'])
def board_create():
    user = _current_user()
    data = request.get_json(force=True) or {}
    post_type = data.get('type', '')

    # 관리자만 공지 작성
    if post_type == 'notice':
        if not user or not user['is_admin']:
            return jsonify({'error': 'forbidden'}), 403
    else:
        err = _require_verified(user)
        if err:
            return jsonify(err[0]), err[1]
        if post_type not in ('edit', 'question', 'error'):
            return jsonify({'error': 'invalid_type'}), 400

    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title_required'}), 400

    content = (data.get('content') or '').strip()
    is_anonymous = 1 if (data.get('is_anonymous') and post_type == 'edit') else 0
    problem_ids = data.get('problem_ids', [])
    problem_id_ref = data.get('problem_id')  # 질문/오류신고 단일 문항

    conn = get_board_db()
    try:
        cur = conn.execute(
            'INSERT INTO posts (type, title, content, author_id, author_email, is_anonymous) VALUES (?,?,?,?,?,?)',
            (post_type, title, content or None, user['id'], user['email'], is_anonymous)
        )
        post_id = cur.lastrowid

        if post_type == 'edit' and problem_ids:
            conn.executemany(
                'INSERT INTO post_problems (post_id, problem_id, order_idx) VALUES (?,?,?)',
                [(post_id, pid, idx) for idx, pid in enumerate(problem_ids)]
            )
        elif post_type in ('question', 'error') and problem_id_ref:
            conn.execute(
                'INSERT INTO post_problem_ref (post_id, problem_id) VALUES (?,?)',
                (post_id, problem_id_ref)
            )
        conn.commit()
        return jsonify({'id': post_id, 'ok': True}), 201
    finally:
        conn.close()


# ── 게시글 상세 ────────────────────────────────────────────────────
@board_bp.route('/api/board/posts/<int:post_id>', methods=['GET'])
def board_detail(post_id):
    user = _current_user()
    uid = user['id'] if user else None

    conn = get_board_db()
    try:
        row = conn.execute('SELECT * FROM posts WHERE id=?', (post_id,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404

        # 공지는 누구나, 나머지는 인증 회원만
        if row['type'] != 'notice':
            if not user:
                return jsonify({'error': 'login_required'}), 401
            if not user['is_verified']:
                return jsonify({'error': 'verify_required'}), 403

        post = _serialize_post(conn, row, uid, include_problems=True)

        # 댓글 (공지 제외)
        if row['type'] != 'notice':
            raw = conn.execute(
                'SELECT * FROM comments WHERE post_id=? ORDER BY created_at ASC', (post_id,)
            ).fetchall()
            comment_list = []
            for c in raw:
                comment_list.append({
                    'id': c['id'],
                    'post_id': c['post_id'],
                    'parent_id': c['parent_id'],
                    'author_name': _display_name(c['author_id'], c['author_email'], c['is_anonymous']),
                    'is_anonymous': bool(c['is_anonymous']),
                    'content': c['content'],
                    'created_at': c['created_at'],
                    'is_own': (uid is not None and uid == c['author_id']),
                    'is_admin': bool(user and user['is_admin']),
                })
            post['comments'] = comment_list
        else:
            post['comments'] = []

        return jsonify(post)
    finally:
        conn.close()


# ── 편집자 설명 수정 ───────────────────────────────────────────────
@board_bp.route('/api/board/posts/<int:post_id>', methods=['PATCH'])
def board_update(post_id):
    user = _current_user()
    err = _require_verified(user)
    if err:
        return jsonify(err[0]), err[1]

    conn = get_board_db()
    try:
        row = conn.execute('SELECT * FROM posts WHERE id=?', (post_id,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        if row['type'] != 'edit':
            return jsonify({'error': 'not_editable'}), 403
        if row['author_id'] != user['id']:
            return jsonify({'error': 'forbidden'}), 403

        data = request.get_json(force=True) or {}
        new_content = (data.get('content') or '').strip()
        conn.execute(
            "UPDATE posts SET content=?, updated_at=datetime('now','+9 hours') WHERE id=?",
            (new_content or None, post_id)
        )
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


# ── 좋아요 토글 ───────────────────────────────────────────────────
@board_bp.route('/api/board/posts/<int:post_id>/like', methods=['POST'])
def board_like(post_id):
    user = _current_user()
    err = _require_verified(user)
    if err:
        return jsonify(err[0]), err[1]

    conn = get_board_db()
    try:
        row = conn.execute('SELECT id FROM posts WHERE id=?', (post_id,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404

        existing = conn.execute(
            'SELECT 1 FROM post_likes WHERE post_id=? AND user_id=?', (post_id, user['id'])
        ).fetchone()
        if existing:
            conn.execute('DELETE FROM post_likes WHERE post_id=? AND user_id=?', (post_id, user['id']))
            liked = False
        else:
            conn.execute('INSERT INTO post_likes (post_id, user_id) VALUES (?,?)', (post_id, user['id']))
            liked = True
        conn.commit()
        count = _like_count(conn, post_id)
        return jsonify({'liked': liked, 'count': count})
    finally:
        conn.close()


# ── 댓글 작성 ─────────────────────────────────────────────────────
@board_bp.route('/api/board/posts/<int:post_id>/comments', methods=['POST'])
def board_comment_create(post_id):
    user = _current_user()
    err = _require_verified(user)
    if err:
        return jsonify(err[0]), err[1]

    conn = get_board_db()
    try:
        row = conn.execute('SELECT type FROM posts WHERE id=?', (post_id,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        if row['type'] == 'notice':
            return jsonify({'error': 'no_comments_on_notice'}), 403

        data = request.get_json(force=True) or {}
        content = (data.get('content') or '').strip()
        if not content:
            return jsonify({'error': 'content_required'}), 400
        parent_id = data.get('parent_id')
        is_anonymous = 1 if data.get('is_anonymous') else 0

        # parent 검증
        if parent_id:
            p = conn.execute('SELECT post_id FROM comments WHERE id=?', (parent_id,)).fetchone()
            if not p or p['post_id'] != post_id:
                return jsonify({'error': 'invalid_parent'}), 400

        cur = conn.execute(
            'INSERT INTO comments (post_id, parent_id, author_id, author_email, is_anonymous, content) VALUES (?,?,?,?,?,?)',
            (post_id, parent_id, user['id'], user['email'], is_anonymous, content)
        )
        conn.commit()
        return jsonify({'id': cur.lastrowid, 'ok': True}), 201
    finally:
        conn.close()


# ── 댓글 삭제 ─────────────────────────────────────────────────────
@board_bp.route('/api/board/comments/<int:comment_id>', methods=['DELETE'])
def board_comment_delete(comment_id):
    user = _current_user()
    err = _require_verified(user)
    if err:
        return jsonify(err[0]), err[1]

    conn = get_board_db()
    try:
        row = conn.execute('SELECT * FROM comments WHERE id=?', (comment_id,)).fetchone()
        if not row:
            return jsonify({'error': 'not_found'}), 404
        if row['author_id'] != user['id'] and not user['is_admin']:
            return jsonify({'error': 'forbidden'}), 403
        conn.execute('DELETE FROM comments WHERE id=?', (comment_id,))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()


# ── 게시글 일괄 삭제 (관리자 전용) ────────────────────────────────
@board_bp.route('/api/board/posts/bulk_delete', methods=['POST'])
def board_bulk_delete():
    user = _current_user()
    if not user or not user['is_admin']:
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(force=True) or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'error': 'no_ids'}), 400
    conn = get_board_db()
    try:
        ph = ','.join('?' * len(ids))
        conn.execute(f'DELETE FROM posts WHERE id IN ({ph})', ids)
        conn.commit()
        return jsonify({'ok': True, 'deleted': len(ids)})
    finally:
        conn.close()


# ── 공지 고정/해제 (관리자 전용) ──────────────────────────────────
@board_bp.route('/api/board/posts/<int:post_id>/pin', methods=['POST'])
def board_pin(post_id):
    user = _current_user()
    if not user or not user['is_admin']:
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(force=True) or {}
    pinned = 1 if data.get('pinned') else 0
    conn = get_board_db()
    try:
        conn.execute('UPDATE posts SET pinned=? WHERE id=?', (pinned, post_id))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        conn.close()
