"""정적(서버 없는) 오프라인 패키지 빌드.

인터넷이 없는 윈도우 PC에서 폴더만 복사해 쓰도록, 파이썬도 설치도 없이
브라우저만으로 도는 형태로 묶는다. 진입점은 시작하기.html 하나다.

브라우저는 file:// 에서 fetch/XHR 로 로컬 파일을 읽지 못한다(실측 확인).
그래서 데이터는 전부 <script> 로 싣고, 화면이 부르던 /api/... 호출은
offline-api.js 가 fetch 를 가로채 처리한다. 화면 코드는 거의 그대로 쓴다.

사전 준비:
    python3 build_static_data.py       # 문항·검색표·원문 → data/*.js
    python3 build_static_similar.py    # 유사 스텝 표 → data/similar.js

실행:
    python3 build_static.py
"""

import json
import os
import re
import shutil
import sys
import unicodedata
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, 'dist_static')
DATA = os.path.join(OUT, 'data')
LIB = os.path.join(OUT, 'lib')
THUMBS = os.path.join(OUT, 'thumbnails')

# 온라인 판과 같은 버전으로 고정한다(동작 차이를 만들지 않기 위해).
VENDOR = {
    'marked.min.js': 'https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js',
    'purify.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.6/purify.min.js',
    'mathlive.min.js': 'https://unpkg.com/mathlive@0.110.0/mathlive.min.js',
}


def step(msg):
    print(f'\n── {msg}')


def vendor_libs():
    """CDN 스크립트를 내려받아 동봉한다. 빌드할 때만 인터넷이 필요하다."""
    step('외부 스크립트 동봉')
    os.makedirs(LIB, exist_ok=True)
    for name, url in VENDOR.items():
        dst = os.path.join(LIB, name)
        if os.path.exists(dst):
            print(f'  {name:20s} 이미 있음')
            continue
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        open(dst, 'wb').write(data)
        print(f'  {name:20s} {len(data)/1e6:.2f} MB')


def copy_static():
    """katex, style.css, cart.js 등 기존 정적 파일."""
    step('정적 파일 복사')
    src = os.path.join(BASE, 'static')
    dst = os.path.join(OUT, 'static')
    if os.path.exists(dst):
        shutil.rmtree(dst)
    skip = {'thumbnails', 'thumbnails_test', 'tmplt.png', 'tmplt2.png', 'tmplt3.png'}
    os.makedirs(dst, exist_ok=True)
    n = 0
    for name in os.listdir(src):
        if name in skip or name.startswith('.'):
            continue
        s, d = os.path.join(src, name), os.path.join(dst, name)
        if os.path.isdir(s):
            shutil.copytree(s, d)
            n += sum(len(f) for _r, _d, f in os.walk(s))
        else:
            shutil.copy2(s, d)
            n += 1
    print(f'  {n}개 파일')


def convert_thumbnails(quality=None):
    """PNG → WebP 무손실. 화질 손실 없이 약 3분의 1로 줄어든다."""
    step('썸네일 변환 (PNG → WebP 무손실)')
    try:
        from PIL import Image
    except ImportError:
        print('  Pillow 가 없어 건너뜁니다. PNG 를 그대로 복사합니다.')
        shutil.copytree(os.path.join(BASE, 'static', 'thumbnails'), THUMBS, dirs_exist_ok=True)
        return
    src = os.path.join(BASE, 'static', 'thumbnails')
    os.makedirs(THUMBS, exist_ok=True)
    files = [f for f in os.listdir(src) if f.lower().endswith('.png')]
    before = after = 0
    for i, f in enumerate(files, 1):
        sp = os.path.join(src, f)
        dp = os.path.join(THUMBS, unicodedata.normalize('NFC', f[:-4]) + '.webp')
        before += os.path.getsize(sp)
        if not os.path.exists(dp):
            im = Image.open(sp)
            if quality:
                im.convert('RGB').save(dp, 'WEBP', quality=quality, method=4)
            else:
                im.save(dp, 'WEBP', lossless=True)
        after += os.path.getsize(dp)
        if i % 400 == 0:
            print(f'    {i:,}/{len(files):,}')
    print(f'  {len(files):,}장  {before/1e6:.0f} MB → {after/1e6:.0f} MB '
          f'({100 - after/before*100:.0f}% 절감)')


def render_index():
    """Jinja 템플릿을 오프라인 모드로 한 번 렌더링해 정적 HTML 로 만든다."""
    step('진입 페이지 생성')
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(os.path.join(BASE, 'templates')))
    env.globals['url_for'] = lambda endpoint, **kw: 'static/' + kw.get('filename', '')
    html = env.get_template('index.html').render(offline_mode=True)

    # 서버 경로 → 폴더 안 상대 경로
    html = html.replace('"/static/', '"static/').replace("'/static/", "'static/")

    # 외부 스크립트 → 동봉본
    for name, url in VENDOR.items():
        html = re.sub(r'<script[^>]*src="' + re.escape(url) + r'"[^>]*></script>',
                      f'<script defer src="lib/{name}"></script>', html)

    # 데이터와 API 계층을 다른 스크립트보다 먼저 싣는다
    inject = (
        '\n<!-- 오프라인 데이터 (file:// 에서는 fetch 가 막히므로 script 로 싣는다) -->\n'
        '<script src="data/particles.js"></script>\n'
        '<script src="data/db.js"></script>\n'
        '<script src="data/vocab.js"></script>\n'
        '<script src="data/similar.js"></script>\n'
        '<script src="data/mdref.js"></script>\n'
        '<script src="offline-api.js"></script>\n'
    )
    html = html.replace('</head>', inject + '</head>', 1)

    # 썸네일 경로: 서버 라우트 → 폴더 안 파일
    html = html.replace('/thumbnail/${encodeURIComponent(pid)}', 'thumbnails/${encodeURIComponent(pid)}.webp')
    html = html.replace('/thumbnail/${pid}', 'thumbnails/${pid}.webp')

    open(os.path.join(OUT, '시작하기.html'), 'w', encoding='utf-8').write(html)
    print(f'  시작하기.html  {len(html)/1e6:.2f} MB')

    # cart.js 안의 썸네일 경로도 같이 고친다
    cart = os.path.join(OUT, 'static', 'cart.js')
    if os.path.exists(cart):
        s = open(cart, encoding='utf-8').read()
        s2 = (s.replace('/thumbnail/${encodeURIComponent(pid)}', '../thumbnails/${encodeURIComponent(pid)}.webp')
                .replace('/thumbnail/${pid}', '../thumbnails/${pid}.webp'))
        if s != s2:
            open(cart, 'w', encoding='utf-8').write(s2)
            print('  cart.js 썸네일 경로 수정')


def copy_api_layer():
    step('API 계층 복사')
    shutil.copy2(os.path.join(BASE, 'static_src', 'offline-api.js'),
                 os.path.join(OUT, 'offline-api.js'))
    # 토크나이저가 쓰는 조사 목록을 파이썬 원본에서 그대로 가져온다
    sys.path.insert(0, BASE)
    from search_engine import _PARTICLES
    with open(os.path.join(DATA, 'particles.js'), 'w', encoding='utf-8') as f:
        f.write('// 조사 목록 (search_engine.py 와 동일)\nwindow.KL_PARTICLES=')
        json.dump(_PARTICLES, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print(f'  offline-api.js · particles.js ({len(_PARTICLES)}개 조사)')


def write_readme():
    step('사용 안내 작성')
    html = '''<!doctype html><meta charset="utf-8"><title>사용 안내</title>
<style>
body{font-family:"Malgun Gothic","Apple SD Gothic Neo",sans-serif;max-width:44rem;margin:0 auto;
padding:3rem 1.5rem;line-height:1.8;color:#1a1d21;background:#fafafa}
h1{font-size:1.6rem;margin:0 0 .4rem}h2{font-size:1.1rem;margin:2.2rem 0 .5rem}
.lead{color:#666;margin:0 0 2rem}code{background:#eceff3;padding:.1em .4em;border-radius:3px}
.box{background:#fff;border:1px solid #dde2e8;padding:1rem 1.2rem;margin:1rem 0}
b{color:#0f6355}
</style>
<h1>THINK LYNX 오프라인 판</h1>
<p class="lead">인터넷 없이 쓰는 버전입니다. 설치할 것이 없습니다.</p>

<h2>실행 방법</h2>
<div class="box"><b>시작하기.html</b> 파일을 두 번 누르면 끝입니다.</div>
<p>크롬 또는 엣지에서 열립니다. 파이썬을 설치할 필요도, 터미널을 열 필요도 없습니다.
폴더를 USB 나 다른 PC 로 옮겨도 그대로 동작하며, 경로에 한글이나 공백이 있어도 상관없습니다.</p>

<h2>쓸 수 있는 기능</h2>
<p>문항 검색(개념유사도 · 기출표현 · 문항번호), 해설 보기, 유사 스텝 찾기,
장바구니에 담아 순서를 바꾸고 인쇄하기까지 온라인판과 같습니다.</p>

<h2>쓸 수 없는 기능</h2>
<p>게시판, 로그인, 오류 제보는 인터넷이 필요해 빠져 있습니다.</p>

<h2>담아 둔 문항이 사라졌다면</h2>
<p>장바구니와 저장한 세트는 브라우저 안에 보관됩니다.
브라우저의 <em>인터넷 사용 기록 삭제</em>에서 쿠키·사이트 데이터를 지우면 함께 사라집니다.
중요한 세트는 인쇄해 두시거나 PDF 로 저장해 두시기 바랍니다.</p>

<h2>내용을 새로 받으려면</h2>
<p>새 폴더를 받아 통째로 바꾸시면 됩니다. 기존 폴더는 지우셔도 됩니다.</p>
'''
    open(os.path.join(OUT, '사용안내.html'), 'w', encoding='utf-8').write(html)
    print('  사용안내.html')


def summary():
    step('결과')
    total = 0
    rows = []
    for name in sorted(os.listdir(OUT)):
        p = os.path.join(OUT, name)
        if os.path.isdir(p):
            sz = sum(os.path.getsize(os.path.join(r, f))
                     for r, _d, fs in os.walk(p) for f in fs)
            cnt = sum(len(fs) for _r, _d, fs in os.walk(p))
            rows.append((name + '/', sz, f'{cnt:,}개'))
        else:
            sz = os.path.getsize(p)
            rows.append((name, sz, ''))
        total += sz
    for name, sz, extra in rows:
        print(f'  {name:22s} {sz/1e6:8.2f} MB  {extra}')
    print(f'  {"합계":22s} {total/1e6:8.2f} MB')
    print(f'\n  → {OUT}')


def main():
    if not os.path.exists(os.path.join(DATA, 'db.js')):
        print('먼저 build_static_data.py 를 실행하세요.')
        sys.exit(1)
    os.makedirs(OUT, exist_ok=True)
    print('=== 정적 오프라인 패키지 빌드 ===')
    vendor_libs()
    copy_static()
    copy_api_layer()
    convert_thumbnails()
    render_index()
    write_readme()
    summary()


if __name__ == '__main__':
    main()
