"""요청 단위 DB 커넥션 정리.

라우트 함수 대부분이 커넥션을 열고 마지막 줄에서 close() 를 부른다. 중간에서
예외가 나면 그 close() 가 실행되지 않아 커넥션이 남고, 쓰기 트랜잭션이 열려
있었다면 다른 요청까지 막는다. 실제로 랜딩 페이지와 이메일 인증이 간헐적으로
500 이 나던 원인 중 하나였다.

함수 36곳을 각각 try/finally 로 감싸는 대신, 커넥션을 열 때 등록해 두고 요청이
끝날 때 한 번에 닫는다. 기존의 명시적 close() 는 그대로 두어도 된다.
sqlite3 의 close() 는 여러 번 불러도 안전하고, 일찍 닫는 편이 낫기 때문이다.
"""

from flask import g, has_app_context

_KEY = '_tracked_db_conns'


def track(conn):
    """커넥션을 요청 종료 시 정리 대상으로 등록한다.

    기동 시 마이그레이션처럼 요청 밖에서 열리는 경우도 있으므로,
    앱 컨텍스트가 없으면 아무것도 하지 않고 그대로 돌려준다.
    """
    if has_app_context():
        conns = getattr(g, _KEY, None)
        if conns is None:
            conns = []
            setattr(g, _KEY, conns)
        conns.append(conn)
    return conn


def close_tracked(_exc=None):
    """등록된 커넥션을 모두 닫는다. 이미 닫혀 있어도 문제없다."""
    conns = getattr(g, _KEY, None) if has_app_context() else None
    if not conns:
        return
    for conn in conns:
        try:
            conn.close()
        except Exception:
            pass
    conns.clear()


def register(app):
    """앱에 정리 훅을 건다."""
    app.teardown_appcontext(close_tracked)
