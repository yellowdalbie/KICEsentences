"""
KICE Lynx 런처
- 포트 자동 탐색
- 이미 실행 중이면 브라우저만 열기
- Chrome/Edge 앱 모드 우선, 없으면 기본 브라우저 + 트레이 아이콘
"""
import os
import sys
import socket
import subprocess
import threading
import time
import webbrowser
import urllib.request
import traceback
from pathlib import Path

APP_DIR = Path(__file__).parent.resolve()
ROCK_LOG = APP_DIR / 'launcher.log'

def log_msg(msg):
    with open(ROCK_LOG, 'a', encoding='utf-8') as f:
        f.write(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {msg}\n')

LOADING_HTML = APP_DIR / 'loading.html'


# ── 포트 탐색 ──────────────────────────────────────────────
def find_free_port(start=5050, limit=20):
    for port in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start  # 최후 수단


def is_server_running(port):
    try:
        req = urllib.request.urlopen(
            f'http://127.0.0.1:{port}/ping', timeout=1)
        return req.status == 200
    except Exception:
        return False


# ── Chrome / Edge 탐색 ─────────────────────────────────────
def find_app_browser():
    import platform
    system = platform.system()

    if system == 'Darwin':
        candidates = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
            os.path.expanduser(
                '~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
        ]
    elif system == 'Windows':
        import winreg
        candidates = []
        # 레지스트리에서 Chrome/Edge 경로 탐색
        keys = [
            (winreg.HKEY_LOCAL_MACHINE,
             r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe'),
            (winreg.HKEY_LOCAL_MACHINE,
             r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe'),
            (winreg.HKEY_CURRENT_USER,
             r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe'),
        ]
        for hive, subkey in keys:
            try:
                with winreg.OpenKey(hive, subkey) as k:
                    path, _ = winreg.QueryValueEx(k, '')
                    if path:
                        candidates.append(path)
            except Exception:
                pass
        # 일반적인 설치 경로도 추가
        pf = os.environ.get('PROGRAMFILES', r'C:\Program Files')
        pf86 = os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')
        candidates += [
            os.path.join(pf, r'Google\Chrome\Application\chrome.exe'),
            os.path.join(pf86, r'Google\Chrome\Application\chrome.exe'),
            os.path.join(pf, r'Microsoft\Edge\Application\msedge.exe'),
        ]
        local = os.environ.get('LOCALAPPDATA', '')
        if local:
            candidates.append(
                os.path.join(local, r'Google\Chrome\Application\chrome.exe'))
    else:
        candidates = []

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


# ── 브라우저 열기 ───────────────────────────────────────────
def open_app_mode(browser_path, url):
    """일반 브라우저 탭으로 URL 열기 (앱 모드 해제). 프로세스 반환."""
    try:
        proc = subprocess.Popen(
            [browser_path, url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return proc
    except Exception as e:
        log_msg(f"open_app_mode failed: {e}")
        return None


def open_default_browser(url):
    webbrowser.open(url)
    # Windows에서 기본 브라우저로 열 때도 최대화 시도
    import platform
    if platform.system() == 'Windows':
        try:
            import ctypes
            import time as _time
            _time.sleep(1.5)  # 브라우저 창이 뜰 때까지 잠깐 대기
            # Win+Up 키를 눌러 창 최대화
            SW_MAXIMIZE = 3
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, SW_MAXIMIZE)
        except Exception:
            pass


def loading_url(port, first_run=False):
    # Not used anymore
    pass


# ── 트레이 아이콘 (Chrome/Edge 없을 때 폴백) ────────────────
def run_tray(flask_proc):
    try:
        import pystray
        from PIL import Image, ImageDraw

        # 간단한 16×16 아이콘 생성
        img = Image.new('RGB', (64, 64), color='#0f1117')
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 8, 56, 56], fill='#5b8dee')

        def on_quit(icon, _):
            icon.stop()
            if flask_proc and flask_proc.poll() is None:
                flask_proc.terminate()

        icon = pystray.Icon(
            'KICE Lynx',
            img,
            'KICE Lynx',
            menu=pystray.Menu(
                pystray.MenuItem('열기', lambda: open_default_browser(
                    f'http://127.0.0.1:{flask_proc._port}')),
                pystray.MenuItem('종료', on_quit),
            )
        )
        icon.run()
    except Exception:
        # pystray 없거나 실패 시 그냥 대기
        try:
            flask_proc.wait()
        except Exception:
            pass


# ── Flask 서버 시작 ─────────────────────────────────────────
def start_flask(port):
    env = os.environ.copy()
    env['OFFLINE_MODE'] = '1'
    env['KICE_PORT'] = str(port)

    python = sys.executable
    import platform
    if platform.system() == 'Windows':
        proc = subprocess.Popen(
            [python, str(APP_DIR / 'dashboard.py')],
            env=env,
            cwd=str(APP_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=0x08000000
        )
    else:
        proc = subprocess.Popen(
            [python, str(APP_DIR / 'dashboard.py')],
            env=env,
            cwd=str(APP_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
    return proc


def wait_for_flask(port, proc=None, timeout=60):
    """Flask가 응답할 때까지 대기. 진행 바 출력. 성공 여부 반환."""
    BAR_WIDTH = 28
    ESTIMATED = 20   # 예상 시작 시간(초) — 진행 바 기준
    spinners = ['|', '/', '-', '\\']

    start = time.time()
    deadline = start + timeout
    i = 0

    print('KICE Lynx 시작 중...', flush=True)

    while time.time() < deadline:
        if proc and proc.poll() is not None:
            print('', flush=True)
            log_msg(f"wait_for_flask: flask_proc died early (returncode={proc.returncode})")
            return False
        if is_server_running(port):
            elapsed = time.time() - start
            bar = '#' * BAR_WIDTH
            print(f'\r[{bar}] 완료! ({elapsed:.0f}초)          ', flush=True)
            print('브라우저가 열립니다...', flush=True)
            return True

        elapsed = time.time() - start
        progress = min(0.9, elapsed / ESTIMATED)
        filled = int(BAR_WIDTH * progress)
        bar = '#' * filled + '-' * (BAR_WIDTH - filled)
        spinner = spinners[i % len(spinners)]
        print(f'\r{spinner} [{bar}] {elapsed:.0f}초 경과...', end='', flush=True)
        i += 1
        time.sleep(0.5)

    print('', flush=True)
    log_msg("wait_for_flask: timed out.")
    return False


def detect_error(flask_proc):
    """Flask 프로세스 stderr에서 알려진 오류 패턴 감지."""
    try:
        out = flask_proc.stderr.read(4096).decode('utf-8', errors='replace')
    except Exception:
        out = ''

    if 'ModuleNotFoundError' in out or 'ImportError' in out:
        return 'missing_package'
    if 'PermissionError' in out or 'Access is denied' in out:
        return 'permission'
    if out:
        return 'unknown'
    return None


# ── 오류 메시지 표시 ────────────────────────────────────────
ERROR_MESSAGES = {
    'missing_package': (
        "패키지 오류",
        "필요한 구성 요소가 설치되지 않았습니다.\n"
        "프로그램 폴더를 삭제하고 다시 다운로드해주세요."
    ),
    'permission': (
        "권한 오류",
        "파일 접근 권한이 없습니다.\n"
        "바탕화면 또는 문서 폴더로 이동 후 다시 실행해주세요."
    ),
    'port': (
        "포트 오류",
        "사용 가능한 포트를 찾지 못했습니다.\n"
        "컴퓨터를 재시작 후 다시 시도해주세요."
    ),
    'unknown': (
        "실행 오류",
        "알 수 없는 오류가 발생했습니다.\n"
        "컴퓨터를 재시작 후 다시 시도해주세요."
    ),
}


def show_error(error_key):
    import platform
    title, msg = ERROR_MESSAGES.get(error_key, ERROR_MESSAGES['unknown'])
    system = platform.system()
    if system == 'Darwin':
        subprocess.run([
            'osascript', '-e',
            f'display dialog "{msg}" with title "KICE Lynx — {title}" buttons {{"확인"}} default button 1 with icon stop'
        ])
    elif system == 'Windows':
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, f'KICE Lynx — {title}', 0x10)
    else:
        print(f'[오류] {title}: {msg}')


# ── 메인 ───────────────────────────────────────────────────
def main():
    log_msg("--- Launcher Started ---")
    os.chdir(APP_DIR)

    # 이미 실행 중이면 브라우저만 열고 종료
    if is_server_running(5050):
        log_msg("Server already running on port 5050.")
        browser = find_app_browser()
        url = 'http://127.0.0.1:5050'
        if browser:
            open_app_mode(browser, url)
        else:
            open_default_browser(url)
        return

    port = find_free_port(5050)
    log_msg(f"Free port found: {port}")
    browser = find_app_browser()
    log_msg(f"Browser path: {browser}")

    # Flask 시작
    flask_proc = start_flask(port)
    flask_proc._port = port  # 트레이 아이콘에서 참조용
    log_msg("Flask process started.")

    # 준비 대기
    ready = wait_for_flask(port, proc=flask_proc, timeout=60)
    log_msg(f"Server ready: {ready}")

    if not ready:
        # Flask가 죽었는지 확인
        if flask_proc.poll() is not None:
            log_msg("Flask process failed.")
            error_key = detect_error(flask_proc)
            show_error(error_key or 'unknown')
            return
        # 60초 초과 → 그냥 진행

    # 브라우저 열기 (서버 준비 후)
    url = f'http://127.0.0.1:{port}'
    log_msg(f"Opening browser to {url}")
    if browser:
        open_app_mode(browser, url)
    else:
        open_default_browser(url)

    # Chrome/Edge 없는 경우: 트레이 아이콘으로 종료 제공
    if not browser:
        log_msg("Starting tray icon...")
        run_tray(flask_proc)
    # Chrome/Edge 있는 경우: 브라우저를 통해 /api/shutdown 호출 시 종료
    log_msg("Launcher finished gracefully.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log_msg(f"Fatal exception: {e}\n{traceback.format_exc()}")
