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
    skip = {'thumbnails', 'thumbnails_test', 'tmplt.png', 'tmplt2.png', 'tmplt3.png', 'board.js'}
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


def strip_board(html):
    """게시판을 흔적까지 걷어낸다.

    오프라인 판에는 게시판이 아예 없어야 하므로, 보이지 않는 모달·오버레이와
    board.js 까지 함께 지운다. 남겨 두면 사용자가 존재를 눈치채게 되고,
    눌러도 아무 일이 없는 요소가 생긴다.
    """
    import re as _re

    def drop_block(h, marker):
        """marker 로 시작하는 요소를 여는/닫는 div 짝을 세어 통째로 제거."""
        i = h.find(marker)
        if i == -1:
            return h, False
        j = h.rfind('<div', 0, h.find('>', i) + 1)
        j = h.find('<div', i) if j < i else j
        depth, k, end = 0, j, None
        while k < len(h):
            m = _re.compile(r'<div\b|</div>').search(h, k)
            if not m:
                break
            if m.group(0) == '</div>':
                depth -= 1
                if depth == 0:
                    end = m.end()
                    break
            else:
                depth += 1
            k = m.end()
        if end is None:
            return h, False
        return h[:i] + h[end:], True

    removed = []
    # 화면에 보이는 게시판 패널
    html, ok = drop_block(html, '<!-- 게시판 패널 -->')
    if ok:
        removed.append('게시판 패널')
    # 숨어 있는 오버레이·모달
    for marker in ['<div id="board-detail-overlay"', '<div id="board-auth-modal"',
                   '<div id="board-edit-desc-modal"', '<div id="board-notice-modal"',
                   '<div id="board-write-overlay"', '<div id="board-publish-modal"']:
        html, ok = drop_block(html, marker)
        if ok:
            removed.append(marker.split('"')[1])
    # board.js 와, 지워진 요소를 직접 만지는 인라인 스크립트
    html = _re.sub(r'<script[^>]*board\.js[^>]*></script>\s*', '', html)
    html = _re.sub(r"<script>document\.getElementById\('board-[^']*'\)[^<]*</script>\s*", '', html)
    removed.append('board.js')

    # 남은 주석까지 지운다 (파일을 열어 보는 사람에게도 흔적이 없도록)
    html = _re.sub(r'[ \t]*<!--[^>]*게시판[^>]*-->\n?', '', html)
    html = _re.sub(r'[ \t]*//[^\n]*게시판[^\n]*\n', '', html)
    # board.js 가 없으니 절대 참이 될 수 없는 가드 블록도 지운다
    html = _re.sub(
        r"[ \t]*if \(typeof window\.closeBoardDetail === 'function'\) \{[^}]*\}\n?",
        '', html)
    print(f'  게시판 제거: {", ".join(removed)}')

    left = len(_re.findall(r'id="board-[\w-]+"', html))
    if left:
        print(f'  경고: board- 요소가 {left}개 남아 있습니다')
    return html


def render_index():
    """Jinja 템플릿을 오프라인 모드로 한 번 렌더링해 정적 HTML 로 만든다."""
    step('진입 페이지 생성')
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(os.path.join(BASE, 'templates')))
    env.globals['url_for'] = lambda endpoint, **kw: 'static/' + kw.get('filename', '')
    html = env.get_template('index.html').render(offline_mode=True)

    html = strip_board(html)

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
    """처음 이 폴더를 여는 사람을 위한 사용 안내.

    guide/ 의 실제 화면 캡처를 함께 보여 준다. 제작자용 메모가 아니라,
    무엇을 어떻게 누르면 되는지 알려주는 문서여야 한다.
    """
    step('사용 안내 작성')
    guide_dir = os.path.join(OUT, 'guide')
    shots = set(os.listdir(guide_dir)) if os.path.isdir(guide_dir) else set()

    def shot(name, caption):
        """캡처가 있으면 그림을, 없으면 자리 표시를 넣는다."""
        f = f'{name}.webp'
        if f in shots:
            return (f'<figure><img src="guide/{f}" alt="{caption}">'
                    f'<figcaption>{caption}</figcaption></figure>')
        return (f'<figure class="ph"><div class="phbox">화면 그림</div>'
                f'<figcaption>{caption}</figcaption></figure>')

    html = f"""<!doctype html><html lang="ko"><meta charset="utf-8">
<title>THINK LYNX 사용 안내</title>
<style>
:root{{
  --bg:#0f1216; --card:#171b21; --line:#282e36; --ink:#e9ecef; --dim:#98a1ab;
  --accent:#5ec8dd; --accent2:#a78bfa; --ok:#6fcf97;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",sans-serif;
  line-height:1.8;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:60rem;margin:0 auto;padding:3rem 1.5rem 5rem}}
h1{{font-size:2rem;margin:0 0 .3rem;letter-spacing:-.02em}}
.lead{{color:var(--dim);margin:0 0 2.5rem;font-size:1.05rem}}
h2{{font-size:1.35rem;margin:3rem 0 .6rem;padding-top:1.4rem;border-top:1px solid var(--line)}}
h3{{font-size:1.05rem;margin:2rem 0 .4rem;color:var(--accent)}}
p{{margin:.6rem 0;max-width:62ch}}
.start{{background:linear-gradient(135deg,#15303a,#1a2333);border:1px solid var(--accent);
  padding:1.6rem 1.8rem;border-radius:10px;margin-bottom:1rem}}
.start b{{font-size:1.3rem;color:var(--accent)}}
figure{{margin:1.2rem 0 1.8rem}}
figure img{{width:100%;border:1px solid var(--line);border-radius:8px;display:block}}
figcaption{{color:var(--dim);font-size:.86rem;margin-top:.5rem}}
.ph .phbox{{width:100%;aspect-ratio:11/6;border:1px dashed var(--line);border-radius:8px;
  display:grid;place-items:center;color:var(--dim);background:#12161b}}
.tag{{display:inline-block;background:#1e2530;border:1px solid var(--line);border-radius:5px;
  padding:.1em .5em;font-size:.9em;color:var(--accent)}}
.step{{display:grid;grid-template-columns:auto 1fr;gap:.9rem;align-items:start;margin:.7rem 0}}
.step .n{{background:var(--accent);color:#0f1216;font-weight:700;width:1.6rem;height:1.6rem;
  border-radius:50%;display:grid;place-items:center;font-size:.85rem;margin-top:.25rem}}
table{{width:100%;border-collapse:collapse;margin:1rem 0;font-size:.93rem}}
th,td{{padding:.55rem .8rem;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--dim);font-weight:600;font-size:.85rem;background:#141920}}
.note{{background:#1a1712;border-left:3px solid #d0a24c;padding:.9rem 1.1rem;margin:1.4rem 0;
  color:#e0d6c4;font-size:.94rem}}
.note b{{color:#f0c674}}
ul{{padding-left:1.2rem}} li{{margin:.35rem 0}}
</style>
<div class="wrap">

<h1>THINK LYNX 사용 안내</h1>
<p class="lead">수능·모의평가 수학 문항을 찾고, 해설을 보고, 문제지로 만들어 인쇄하는 프로그램입니다. 인터넷 없이 쓸 수 있습니다.</p>

<div class="start">
  <b>시작하기.html</b> 파일을 두 번 누르세요. 그러면 바로 실행됩니다.
</div>
<p>설치할 것이 없습니다. 이 폴더를 USB 나 다른 컴퓨터로 옮겨도 그대로 쓸 수 있고,
폴더 이름이나 경로에 한글·공백이 있어도 괜찮습니다.
크롬이나 엣지에서 열리며, 창을 닫으면 그대로 종료됩니다.</p>

<h2>첫 화면</h2>
<p>가운데 검색창이 있고, 그 위에 <span class="tag">개념유사도</span>
<span class="tag">기출표현</span> <span class="tag">문항번호</span>
<span class="tag">성취기준</span> 네 가지 찾는 방법이 있습니다.
무엇을 알고 있느냐에 따라 골라 쓰시면 됩니다.</p>
{shot('01-첫화면', '첫 화면. 네 가지 검색 방법 중 하나를 고르고 검색창에 입력합니다.')}

<table>
<tr><th style="width:7rem">검색 방법</th><th>이럴 때 씁니다</th><th style="width:12rem">입력 예시</th></tr>
<tr><td><b>개념유사도</b></td><td>풀이 방법이나 개념이 떠오를 때. 비슷한 접근으로 푸는 문항을 찾아 줍니다.</td><td>코사인법칙 변의 길이</td></tr>
<tr><td><b>기출표현</b></td><td>문제에 실제로 적힌 표현이 기억날 때. 원문을 그대로 뒤집니다.</td><td>외접원</td></tr>
<tr><td><b>문항번호</b></td><td>몇 년도 몇 번인지 알 때.</td><td>2027.9모</td></tr>
<tr><td><b>성취기준</b></td><td>교육과정 단원으로 훑어보고 싶을 때.</td><td>단원을 눌러 선택</td></tr>
</table>

<h2>1. 개념유사도로 찾기</h2>
<p>가장 많이 쓰게 되는 방법입니다. 풀이에 쓰이는 개념이나 방법을 그대로 적으면 됩니다.
문장으로 적어도 되고, 단어만 적어도 됩니다.</p>
{shot('02-개념유사도결과', '"코사인법칙 변의 길이"로 찾은 결과. 왼쪽이 문항번호, 가운데가 해설의 단계별 요약, 오른쪽이 교육과정 성취기준입니다.')}

<h3>해설 보기</h3>
<p>가운데 <b>단계별 요약</b>을 누르면 그 단계의 자세한 해설이 펼쳐집니다.
수식은 교과서처럼 보기 좋게 표시됩니다.</p>
{shot('03-해설펼침', '단계를 누르면 계산 과정을 생략 없이 보여 줍니다.')}

<h3>문제 원문 미리보기</h3>
<p>왼쪽 <b>문항번호</b> 위에 마우스를 올리면 실제 시험지에 실린 그대로의 문제가 나타납니다.
그림이 있는 문항은 그림까지 그대로 보입니다.</p>
{shot('04-썸네일미리보기', '문항번호에 마우스를 올린 모습. 문제 원문과 그림, 선택지까지 보입니다.')}

<h2>2. 기출표현으로 찾기</h2>
<p>문제에 실린 단어나 수식을 그대로 찾습니다. 찾은 낱말이 있는 부분을 함께 보여 줍니다.</p>
<ul>
<li>여러 낱말을 적으면 <b>모두 들어 있는</b> 문항을 찾습니다.</li>
<li>둘 중 하나만 있어도 될 때는 사이에 <span class="tag">OR</span> 를 넣습니다. 예) <code>외접원 OR 내접원</code></li>
<li>빼고 싶은 낱말 앞에는 <span class="tag">-</span> 를 붙입니다. 예) <code>외접원 -삼각형</code></li>
<li>띄어쓰기까지 정확히 맞추려면 따옴표로 묶습니다. 예) <code>"외접원의 넓이"</code></li>
</ul>
{shot('08-기출표현', '"외접원"으로 찾은 결과. 문항마다 그 표현이 나온 대목을 보여 줍니다.')}

<h2>3. 문항번호로 찾기</h2>
<p>연도와 시험, 번호를 적으면 됩니다. <code>2027.9모</code> 처럼 일부만 적어도 되고,
<code>2024수능_30</code> 처럼 끝까지 적어도 됩니다. 띄어쓰기나 '번'은 있어도 없어도 괜찮습니다.</p>
{shot('09-문항번호', '"2027.9모"로 찾은 결과. 해당 시험의 문항이 번호 순서대로 나옵니다.')}

<h2>4. 성취기준으로 훑어보기</h2>
<p>왼쪽에서 과목과 단원을 고르면 그 단원의 성취기준이 나오고,
성취기준을 누르면 해당하는 문항이 모입니다. 단원별로 문제를 뽑을 때 편합니다.</p>
{shot('10-성취기준', '대수 &gt; 지수함수와 로그함수 단원을 펼친 모습.')}

<h2>문제지 만들기</h2>

<h3>담기</h3>
<div class="step"><span class="n">1</span><div>찾은 결과에서 <b>문항번호를 누르면</b> 그 문항이 담깁니다. 다시 누르면 빠집니다.</div></div>
<div class="step"><span class="n">2</span><div>담긴 문항은 오른쪽 목록에 쌓이고, 화면 오른쪽 끝의 숫자로 몇 개인지 알 수 있습니다.</div></div>
{shot('05-장바구니담기', '문항번호를 누르면 오른쪽에 담은 문항 목록이 열립니다.')}

<h3>순서 바꾸기</h3>
<p>목록에서 문항을 <b>끌어 올리거나 내려</b> 순서를 바꿀 수 있습니다.
빼고 싶으면 오른쪽 <b>×</b> 를 누릅니다.</p>
{shot('06-장바구니목록', '두 문항을 담은 모습. 담긴 문항은 목록에 표시가 남습니다.')}

<h3>미리보기와 인쇄</h3>
<p>목록 아래 <b>미리보기 / 인쇄</b> 를 누르면 실제 시험지 모양으로 만들어집니다.
위쪽 단추로 다음을 고를 수 있습니다.</p>
<ul>
<li><b>타이틀 수정</b> — 문제지 제목을 바꿉니다.</li>
<li><b>정답 표기</b> — 정답을 각 문항 옆에 넣을지, 맨 뒤에 모을지, 넣지 않을지 고릅니다.</li>
<li><b>해설</b> — 해설을 함께 넣을지 고릅니다.</li>
<li><b>PDF 저장</b> — 인쇄 창이 열립니다. 프린터 대신 <b>PDF로 저장</b>을 고르면 파일로 남습니다.</li>
</ul>
{shot('07-인쇄미리보기', '두 문항으로 만든 문제지. 왼쪽에서 순서를 바꿀 수 있고, 오른쪽 위에서 PDF로 저장합니다.')}

<h2>알아두실 점</h2>

<h3>담아 둔 문항은 이 컴퓨터의 브라우저에 저장됩니다</h3>
<p>담은 문항과 저장한 문제지는 서버가 아니라 <b>이 컴퓨터의 브라우저 안</b>에 남습니다.
그래서 브라우저에서 <em>인터넷 사용 기록 삭제</em>로 쿠키·사이트 데이터를 지우면 함께 사라집니다.
계속 쓰실 문제지는 <b>PDF로 저장해 두시길</b> 권합니다.</p>

<div class="note"><b>해설이 없는 문항이 있습니다.</b><br>
기하(2022)와 미적분Ⅱ(2022) 과목은 해설과 정답을 제공하지 않습니다.
다만 '기출표현'과 '문항번호' 검색으로 문제를 찾아보는 것은 됩니다.</div>

<h3>내용을 새로 받으려면</h3>
<p>새 폴더를 받아 통째로 바꾸시면 됩니다. 예전 폴더는 지우셔도 됩니다.
담아 둔 문항은 브라우저에 남아 있으므로 폴더를 바꿔도 그대로입니다.</p>

<h3>화면이 이상하게 보인다면</h3>
<p>크롬이나 엣지에서 열어 주세요. 인터넷 익스플로러에서는 동작하지 않습니다.
글자만 나오고 모양이 깨져 보이면, 폴더 안의 파일이 일부 빠진 것이니
받으신 압축 파일을 다시 풀어 주세요.</p>

</div></html>
"""
    open(os.path.join(OUT, '사용안내.html'), 'w', encoding='utf-8').write(html)
    n = sum(1 for k in shots if k.endswith('.webp'))
    print(f'  사용안내.html (화면 캡처 {n}장 포함)')


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
