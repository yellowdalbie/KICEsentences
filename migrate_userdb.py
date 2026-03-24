"""
migrate_userdb.py
─────────────────
기존 kice_database.sqlite에서 유저 데이터 테이블을 kice_userdata.sqlite로 복사합니다.
서버에서 단 한 번만 실행하세요.

실행 방법:
    python3 migrate_userdb.py

완료 후:
    - kice_userdata.sqlite 파일이 생성됩니다.
    - kice_database.sqlite의 원본 데이터는 그대로 유지됩니다 (삭제하지 않음).
    - 서버를 재시작하면 dashboard.py가 kice_userdata.sqlite를 사용합니다.
"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_FILE = os.path.join(BASE_DIR, 'kice_database.sqlite')
DST_FILE = os.path.join(BASE_DIR, 'kice_userdata.sqlite')

USER_TABLES = ['users', 'login_logs', 'access_logs', 'search_stats', 'cart_logs', 'problem_sets']


def migrate():
    if not os.path.exists(SRC_FILE):
        print(f"[오류] {SRC_FILE} 파일이 없습니다.")
        return

    if os.path.exists(DST_FILE):
        print(f"[경고] {DST_FILE} 이미 존재합니다. 덮어쓰지 않고 종료합니다.")
        print("       이미 마이그레이션이 완료된 경우 이 파일을 그대로 사용하세요.")
        return

    src = sqlite3.connect(SRC_FILE)
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(DST_FILE)

    # 소스 DB에 있는 테이블 목록 확인
    existing = {row[0] for row in src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    for table in USER_TABLES:
        if table not in existing:
            print(f"  [스킵] {table} 테이블 없음 (신규 설치 환경)")
            continue

        # 스키마 복사
        schema_row = src.execute(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not schema_row or not schema_row[0]:
            print(f"  [스킵] {table} 스키마 없음")
            continue

        dst.execute(schema_row[0])

        # 인덱스 복사
        for idx_row in src.execute(
            f"SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (table,)
        ).fetchall():
            try:
                dst.execute(idx_row[0])
            except Exception:
                pass

        # 데이터 복사
        rows = src.execute(f"SELECT * FROM {table}").fetchall()
        if rows:
            cols = rows[0].keys()
            placeholders = ','.join('?' for _ in cols)
            col_names = ','.join(cols)
            dst.executemany(
                f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})",
                [tuple(row) for row in rows]
            )
            print(f"  [완료] {table}: {len(rows)}건 복사")
        else:
            print(f"  [완료] {table}: 데이터 없음 (빈 테이블)")

    # users 테이블에 display_name 컬럼 없으면 추가
    try:
        cols = [row[1] for row in dst.execute("PRAGMA table_info(users)").fetchall()]
        if 'display_name' not in cols:
            dst.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
            print("  [마이그레이션] users.display_name 컬럼 추가")
    except Exception as e:
        print(f"  [경고] display_name 마이그레이션 실패: {e}")

    dst.commit()
    src.close()
    dst.close()

    print(f"\n마이그레이션 완료: {DST_FILE}")
    print("이제 서버를 재시작하세요.")


if __name__ == '__main__':
    migrate()
