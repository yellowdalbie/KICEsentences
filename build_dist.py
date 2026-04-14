"""
KICE Lynx 배포 패키지 빌더

Mac 한 대에서 3종 모두 빌드 가능.
wheels와 Python embeddable을 PyPI / python.org에서 자동 다운로드.

사용법:
  python3 build_dist.py --platform mac-arm64
  python3 build_dist.py --platform mac-x86
  python3 build_dist.py --platform windows
  python3 build_dist.py --platform all

생성 결과:
  dist/KICE_Lynx_{VERSION}_{platform}.zip
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = 'v2025.11'

# ── Windows embedded Python ──────────────────────────────────
PYTHON_WIN_VERSION = '3.11.9'
PYTHON_WIN_URL = (
    f'https://www.python.org/ftp/python/{PYTHON_WIN_VERSION}/'
    f'python-{PYTHON_WIN_VERSION}-embed-amd64.zip'
)
PYTHON_VERSION = '3.11'   # Windows pip --python-version

# ── Mac standalone Python (python-build-standalone) ─────────
PBS_RELEASE = '20260310'
PYTHON_MAC_VERSION = '3.11.15'
PYTHON_MAC_URLS = {
    'mac-arm64': (
        f'https://github.com/astral-sh/python-build-standalone/releases/download/{PBS_RELEASE}/'
        f'cpython-{PYTHON_MAC_VERSION}%2B{PBS_RELEASE}-aarch64-apple-darwin-install_only.tar.gz'
    ),
    'mac-x86': (
        f'https://github.com/astral-sh/python-build-standalone/releases/download/{PBS_RELEASE}/'
        f'cpython-{PYTHON_MAC_VERSION}%2B{PBS_RELEASE}-x86_64-apple-darwin-install_only.tar.gz'
    ),
}

SRC = Path(__file__).parent.resolve()
DIST = SRC / 'dist'
CACHE = SRC / '.build_cache'   # 다운로드 캐시 (재빌드 속도 향상)

# ── 배포 포함 파일 ──────────────────────────────────────────
APP_FILES = [
    'dashboard.py',
    'search_engine.py',
    'routes_landing.py',
    'launcher.py',
    'loading.html',
    'requirements_dist.txt',
    'concepts.json',
    'kice_database.sqlite',
    'kice_step_vectors.npz',
    'kice_query_vocab.npz',
    'step_clusters.json',
    'trigger_category_vectors.npz',
]
STATIC_EXCLUDES = {'tmplt.png', 'tmplt2.png', 'tmplt3.png'}
TEMPLATE_EXCLUDES = {'admin.html'}

# ── 플랫폼 설정 ─────────────────────────────────────────────
PLATFORM_CONFIGS = {
    'mac-arm64': {},   # standalone Python 사용, pip_platform 불필요
    'mac-x86': {},
    'windows': {
        'pip_platform': 'win_amd64',
        'pip_abi': 'cp311',
    },
}


# ── 유틸 ────────────────────────────────────────────────────
def run(cmd: list, **kwargs):
    print(f'    $ {" ".join(str(c) for c in cmd)}')
    result = subprocess.run(cmd, check=True, **kwargs)
    return result


def download(url: str, dest: Path):
    if dest.exists():
        print(f'    (캐시) {dest.name}')
        return
    print(f'    다운로드: {url}')
    urllib.request.urlretrieve(url, dest)


# ── Windows wheels 다운로드 (크로스 플랫폼) ─────────────────
def download_wheels_windows(wheels_dir: Path):
    cfg = PLATFORM_CONFIGS['windows']
    wheels_dir.mkdir(parents=True, exist_ok=True)
    req_file = SRC / 'requirements_dist.txt'
    run([
        sys.executable, '-m', 'pip', 'download',
        '--dest', str(wheels_dir),
        '--platform', cfg['pip_platform'],
        '--python-version', PYTHON_VERSION,
        '--only-binary', ':all:',
        '-r', str(req_file),
    ])
    print(f'    wheels {len(list(wheels_dir.glob("*")))}개 준비 완료')


# ── Mac standalone Python 구성 ───────────────────────────────
def setup_mac_python(platform: str, python_dir: Path):
    """
    python-build-standalone에서 Mac용 Python을 다운로드하고
    필요한 패키지를 설치한다.
    현재 Mac이 arm64이므로 arm64 Python은 네이티브로 실행 가능.
    """
    import tarfile

    url = PYTHON_MAC_URLS[platform]
    fname = (
        f'cpython-{PYTHON_MAC_VERSION}+{PBS_RELEASE}-'
        f'{"aarch64" if "arm64" in platform else "x86_64"}'
        f'-apple-darwin-install_only.tar.gz'
    )
    tar_cache = CACHE / fname
    CACHE.mkdir(exist_ok=True)
    download(url, tar_cache)

    print('    Python standalone 압축 해제 중...')
    extract_tmp = CACHE / f'_extract_{platform}'
    if extract_tmp.exists():
        shutil.rmtree(extract_tmp)
    extract_tmp.mkdir(parents=True)

    with tarfile.open(tar_cache, 'r:gz') as tf:
        tf.extractall(extract_tmp)

    # python-build-standalone은 'python/' 폴더로 압축 해제됨
    extracted = extract_tmp / 'python'
    shutil.move(str(extracted), str(python_dir))
    shutil.rmtree(extract_tmp)

    # standalone Python의 pip로 패키지 설치
    python_bin = python_dir / 'bin' / 'python3'
    req_file = SRC / 'requirements_dist.txt'
    wheels_dir = CACHE / f'wheels_{platform}'
    wheels_dir.mkdir(parents=True, exist_ok=True)

    print('    패키지 다운로드 중...')
    run([
        str(python_bin), '-m', 'pip', 'download',
        '--dest', str(wheels_dir),
        '--only-binary', ':all:',
        '-r', str(req_file),
    ])

    print('    패키지 설치 중...')
    run([
        str(python_bin), '-m', 'pip', 'install',
        '--no-index', '--find-links', str(wheels_dir),
        '-r', str(req_file), '-q',
    ])

    print(f'    python3: {"✅" if python_bin.exists() else "⚠️ 없음"}')


# ── Windows embedded Python 구성 ────────────────────────────
def setup_windows_python(python_dir: Path):
    """
    python_dir 안에 embeddable Python + pip + 패키지 설치.
    Mac에서도 실행 가능 (wheels를 직접 unzip으로 설치).
    """
    python_dir.mkdir(parents=True, exist_ok=True)

    # 1. embeddable zip 다운로드 및 압축 해제
    zip_cache = CACHE / f'python-{PYTHON_WIN_VERSION}-embed-amd64.zip'
    CACHE.mkdir(exist_ok=True)
    download(PYTHON_WIN_URL, zip_cache)

    print('    embeddable Python 압축 해제 중...')
    with zipfile.ZipFile(zip_cache) as zf:
        zf.extractall(python_dir)

    # 2. site-packages 활성화 (.pth 파일 수정)
    pth_files = list(python_dir.glob('python3*._pth'))
    if pth_files:
        pth = pth_files[0]
        content = pth.read_text(encoding='utf-8')
        # '#import site' 주석 해제
        content = content.replace('#import site', 'import site')
        # app\ 폴더(상위 디렉토리)를 sys.path에 추가 — search_engine.py 등 탐색용
        if '..\n' not in content and '..\\n' not in content:
            content = content.rstrip('\n') + '\n..\n'
        pth.write_text(content, encoding='utf-8')
        print(f'    {pth.name} — import site 활성화, .. 경로 추가')

    # 3. site-packages 폴더 생성
    site_packages = python_dir / 'Lib' / 'site-packages'
    site_packages.mkdir(parents=True, exist_ok=True)

    # 4. Windows wheels 다운로드 후 site-packages에 설치
    #    (Mac에서 .exe 없이 wheel을 직접 unzip)
    wheels_dir = CACHE / 'wheels_windows'
    download_wheels_windows(wheels_dir)

    print('    패키지를 site-packages에 설치 중...')
    for whl in wheels_dir.glob('*.whl'):
        with zipfile.ZipFile(whl) as zf:
            # .dist-info 포함 전체 내용을 site-packages에 압축 해제
            zf.extractall(site_packages)

    # whl 파일이 site-packages에 복사된 경우 제거 (unzip 부산물)
    for stray in site_packages.glob('*.whl'):
        stray.unlink()

    # 5. pythonw.exe 확인
    pythonw = python_dir / 'pythonw.exe'
    print(f'    pythonw.exe: {"✅" if pythonw.exists() else "⚠️ 없음"}')


# ── app/ 파일 구성 ───────────────────────────────────────────
def copy_app_files(app_dst: Path):
    app_dst.mkdir(parents=True, exist_ok=True)
    # landing/ 디렉토리 생성 (routes_landing.py가 DB를 이 경로에 생성)
    (app_dst / 'landing').mkdir(exist_ok=True)

    for fname in APP_FILES:
        src = SRC / fname
        if src.exists():
            shutil.copy2(src, app_dst / fname)
        else:
            print(f'  [경고] 없음: {fname}')

    # static/
    _copy_filtered(SRC / 'static', app_dst / 'static', STATIC_EXCLUDES)
    # templates/ (admin.html 제외)
    _copy_filtered(SRC / 'templates', app_dst / 'templates', TEMPLATE_EXCLUDES)

    # MD_Ref/
    if (SRC / 'MD_Ref').exists():
        shutil.copytree(SRC / 'MD_Ref', app_dst / 'MD_Ref', dirs_exist_ok=True)


def _copy_filtered(src: Path, dst: Path, excludes: set):
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name in excludes:
            continue
        dest = dst / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


# ── 메인 빌드 ───────────────────────────────────────────────
def build(platform: str):
    cfg = PLATFORM_CONFIGS[platform]
    pkg_name = f'KICE_Lynx_{VERSION}_{platform}'
    build_dir = DIST / pkg_name
    zip_path = DIST / f'{pkg_name}.zip'

    print(f'\n{"="*55}')
    print(f'  KICE Lynx 빌드: {platform} ({VERSION})')
    print(f'{"="*55}')

    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    # app/ 공통 파일
    app_dst = build_dir / 'app'
    print('\n  [1/3] app/ 파일 복사...')
    copy_app_files(app_dst)

    # 플랫폼별 처리
    if platform in ('mac-arm64', 'mac-x86'):
        print(f'\n  [2/3] Python 환경 구성 ({platform})...')
        python_dir = CACHE / f'python_{platform}'
        if not python_dir.exists():
            setup_mac_python(platform, python_dir)
        else:
            print(f'    (캐시) python_{platform}/')
        shutil.copytree(python_dir, app_dst / 'python', dirs_exist_ok=True)

        # Mac 런처 — .app 번들
        app_bundle = build_dir / 'KICE Lynx.app'
        macos_dir  = app_bundle / 'Contents' / 'MacOS'
        macos_dir.mkdir(parents=True)
        resources_dir = app_bundle / 'Contents' / 'Resources'
        resources_dir.mkdir(parents=True)

        # Icon copy
        if Path('icon.icns').exists():
            shutil.copy2('icon.icns', resources_dir / 'AppIcon.icns')

        # Info.plist
        ver_num = VERSION.lstrip('v')
        (app_bundle / 'Contents' / 'Info.plist').write_text(
            f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleExecutable</key><string>KICE Lynx</string>
  <key>CFBundleIdentifier</key><string>kr.kice.lynx</string>
  <key>CFBundleName</key><string>KICE Lynx</string>
  <key>CFBundleDisplayName</key><string>KICE Lynx</string>
  <key>CFBundleVersion</key><string>{ver_num}</string>
  <key>CFBundleShortVersionString</key><string>{ver_num}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSUIElement</key><true/>
</dict></plist>
''', encoding='utf-8')

        # 실행 스크립트
        exec_script = macos_dir / 'KICE Lynx'
        exec_script.write_text(
            '#!/bin/bash\n'
            '# .app 내부에서의 경로 계산\n'
            'BASE_DIR="$(cd "$(dirname "$0")/../../../.." && pwd)"\n'
            'export APP_DIR="$BASE_DIR/app"\n'
            'DEBUG_LOG="$BASE_DIR/mac_launch.log"\n'
            'echo "Start: $(date)" > "$DEBUG_LOG"\n'
            'echo "BASE_DIR: $BASE_DIR" >> "$DEBUG_LOG"\n'
            'PYTHON="$APP_DIR/python/bin/python3"\n'
            'if [ ! -f "$PYTHON" ]; then\n'
            '  # 한 단계 위에서도 시도 (ZIP 구성에 따라 가변적)\n'
            '  BASE_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"\n'
            '  export APP_DIR="$BASE_DIR/app"\n'
            '  PYTHON="$APP_DIR/python/bin/python3"\n'
            '  echo "Retry BASE_DIR: $BASE_DIR" >> "$DEBUG_LOG"\n'
            'fi\n'
            'if [ ! -x "$PYTHON" ]; then\n'
            '  chmod +x "$PYTHON" 2>/dev/null\n'
            'fi\n'
            '# 실행 가능 여부 최종 확인 (App Translocation/Sandbox 체크)\n'
            'if ! "$PYTHON" -c "pass" 2>/dev/null; then\n'
            '  echo "Error: Python execution blocked by sandbox. Advising move to /Applications." >> "$DEBUG_LOG"\n'
            '  osascript -e \'display dialog "macOS 보안 정책으로 인해 [다운로드] 폴더에서는 실행이 제한됩니다.\\n\\n폴더 전체를 [응용 프로그램(Applications)] 폴더로 이동한 후 다시 실행해 주세요." '
            'with title "KICE Lynx — 실행 차단" buttons {"확인"} default button 1 with icon caution\'\n'
            '  exit 1\n'
            'fi\n'
            'cd "$APP_DIR"\n'
            'export OFFLINE_MODE=1\n'
            './python/bin/python3 launcher.py >> "$DEBUG_LOG" 2>&1\n',
            encoding='utf-8')
        os.chmod(exec_script, 0o755)

        # Mac 실행 전용 도움 스크립트 (Gatekeeper 우회)
        helper_script = build_dir / 'Mac_실행이_안될때_클릭.command'
        helper_script.write_text(
            '#!/bin/bash\n'
            'cd "$(dirname "$0")"\n'
            'echo "KICE Lynx 보안 인증을 일시적으로 허용하고 실행합니다..."\n'
            'xattr -cr "KICE Lynx.app" "app" 2>/dev/null\n'
            'chmod +x "KICE Lynx.app/Contents/MacOS/KICE Lynx" 2>/dev/null\n'
            'chmod +x "app/python/bin/python3" 2>/dev/null\n'
            'open "KICE Lynx.app"\n',
            encoding='utf-8')
        os.chmod(helper_script, 0o755)

    elif platform == 'windows':
        print('\n  [2/3] Windows Python 환경 구성...')
        python_dir = CACHE / 'python_windows'
        # 캐시 있으면 재사용
        if not python_dir.exists():
            setup_windows_python(python_dir)
        else:
            print('    (캐시) python_windows/')
        shutil.copytree(python_dir, app_dst / 'python', dirs_exist_ok=True)

        # Offline Guide copy for Windows (icon removed)
        if Path('KICE_Lynx_실행가이드.png').exists():
            shutil.copy2('KICE_Lynx_실행가이드.png', build_dir / 'KICE_Lynx_실행가이드.png')
        if Path('README_실행방법.txt').exists():
            shutil.copy2('README_실행방법.txt', build_dir / 'README_실행방법.txt')

    # 사용설명서
    print('\n  [3/3] 패키징...')
    manual = SRC / '사용설명서.pdf'
    if manual.exists():
        shutil.copy2(manual, build_dir / '사용설명서.pdf')

    # ZIP 생성
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in build_dir.rglob('*'):
            if f.is_file():
                zf.write(f, f.relative_to(DIST))

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f'\n  ✅ 완료: {zip_path.name} ({size_mb:.1f} MB)')

    # shutil.rmtree(build_dir)


# ── 진입점 ───────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='KICE Lynx 배포 패키지 빌더')
    parser.add_argument(
        '--platform',
        choices=[*PLATFORM_CONFIGS.keys(), 'all'],
        required=True,
    )
    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='다운로드 캐시 삭제 후 빌드',
    )
    args = parser.parse_args()

    if args.clear_cache and CACHE.exists():
        shutil.rmtree(CACHE)
        print('캐시 삭제 완료.')

    DIST.mkdir(exist_ok=True)

    platforms = list(PLATFORM_CONFIGS.keys()) if args.platform == 'all' else [args.platform]
    for p in platforms:
        build(p)
