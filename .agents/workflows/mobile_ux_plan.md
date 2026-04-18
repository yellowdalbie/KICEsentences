# KICE Lynx 모바일 UX 구현계획서

> 작성일: 2026-04-18  
> 기준 파일: `templates/index.html`, `static/style.css`, `templates/landing.html`

---

## 0. 핵심 원칙

**`@media (pointer: coarse)`로 모든 모바일 분기 처리.**  
화면 너비가 아닌 입력 방식(터치 여부)으로 판별 → PC/Mac 기존 경험은 단 한 줄도 변경 없음.

```css
/* 이 블록 밖의 CSS는 절대 터치하지 않는다 */
@media (pointer: coarse) {
  /* 모바일 전용 스타일 */
}
```

JS 분기도 동일:
```js
const isTouchDevice = () => window.matchMedia('(pointer: coarse)').matches;
```

---

## 1. 구현 단계 순서 (의존성 기준)

```
Step A: 앱바 + 헤더 재구성   ← 다른 모든 단계의 기반
Step B: 검색 탭 + 검색창 조정
Step C: 검색결과 Inspector Mode (핵심 기능)
Step D: 장바구니 FAB + 바텀시트
Step E: 성취기준 뷰 탭 전환
Step F: 통계 카드 그리드 조정
Step G: onmouseover hover stuck 방지 (전체 적용)
Step H: iOS 렌더링 버그 패치 (backdrop-filter, dvh)
Step I: landing.html 모바일 대응
```

---

## Step A: 앱바 + 헤더 재구성

### 목표
모바일에서 상단 48px 앱바를 만들고, 기존 `#global-actions-left` / `#auth-app-section` / 브랜드 타이틀을 모바일용으로 재배치.

### 현재 구조 (index.html 16~50행)
```
position: fixed; left: 1.5rem; top: 1.2rem  ← #global-actions-left (활용팁 + 안내텍스트)
position: fixed; right: 1.5rem; top: 1.2rem ← #auth-app-section (로그인/회원가입)
.brand-container 중앙 (KICE LYNX 5rem)
.search-mode-pills
.huge-search-wrapper
```

### 변경 내용

**CSS (style.css `@media (pointer: coarse)` 블록에 추가):**
```css
@media (pointer: coarse) {
  /* 앱바 생성 */
  .mobile-appbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: fixed;
    top: 0; left: 0; right: 0;
    height: 48px;
    padding: 0 1rem;
    background: var(--bg-surface);
    backdrop-filter: none;               /* iOS fixed+blur 버그 방지 */
    -webkit-backdrop-filter: none;
    border-bottom: 1px solid var(--border-color);
    z-index: 10000;
  }

  /* 기존 fixed 요소 숨김 */
  #global-actions-left,
  #auth-app-section {
    display: none !important;
  }

  /* 브랜드 타이틀 축소 */
  .brand-container {
    display: none;
  }

  /* 헤더 상단 여백 (앱바 높이만큼) */
  .top-nav-container {
    padding-top: calc(48px + 1rem);
  }
}
```

**HTML (index.html `<body>` 직후, `.app-container` 앞에 삽입):**
```html
<!-- 모바일 전용 앱바: pointer: coarse에서만 보임 -->
<div class="mobile-appbar" id="mobile-appbar" style="display:none;">
  <!-- 좌: 팁 아이콘 버튼 -->
  <button onclick="openTipModal()" style="background:none; border:none; color:var(--text-muted); cursor:pointer; display:flex; align-items:center; gap:6px; font-size:0.82rem; padding:0.4rem 0.6rem; border-radius:8px;">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"></circle>
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
      <line x1="12" y1="17" x2="12.01" y2="17"></line>
    </svg>
    팁
  </button>

  <!-- 중앙: 소형 로고 -->
  <span style="font-family:'Paperozi',sans-serif; font-size:1.4rem; font-weight:900; letter-spacing:-1px;">LYNX</span>

  <!-- 우: 로그인 버튼 1개만 (회원가입은 로그인 모달 내 링크로) -->
  {% if not offline_mode %}
  <button id="mobile-login-btn" onclick="openAuthModal('login')"
    style="background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12);
           color: var(--text-main); padding: 0.35rem 0.9rem; border-radius: 8px;
           cursor: pointer; font-size: 0.8rem; font-weight: 600;">
    로그인
  </button>
  {% endif %}
</div>
```

**JS (DOMContentLoaded 블록 안):**
```js
// 앱바: pointer: coarse 기기에서만 표시
if (isTouchDevice()) {
  document.getElementById('mobile-appbar').style.display = 'flex';
}
```

**로그인 모달 내 회원가입 링크 추가:**  
기존 로그인 모달(`#auth-modal`)의 하단에 다음 추가:
```html
<p style="text-align:center; margin-top:0.8rem; font-size:0.82rem; color:var(--text-muted);">
  계정이 없으신가요? 
  <a href="#" onclick="openAuthModal('register')" style="color:var(--accent-cyan);">회원가입</a>
</p>
```

### 주의사항
- PC에서 `mobile-appbar`가 보이지 않도록 CSS에서 기본값 `display: none` + JS로만 표시
- `#global-actions-left`의 서비스 안내 텍스트(`기하(2022)와 미적분II...`)는 팁 모달(`openTipModal()`) 안으로 이동. PC에서도 이미 같은 내용이 팁에 있으면 중복 제거.

---

## Step B: 검색 탭 + 검색창 조정

### 현재 구조
- `.search-pill`: `padding: 0.6rem 1.8rem; font-size: 1rem` — 4개 합산 약 430px
- `.huge-search-input`: `padding: 1.5rem 5rem 1.5rem 2rem; font-size: 1.3rem`

### 변경 내용 (CSS)
```css
@media (pointer: coarse) {
  .search-pill {
    padding: 0.5rem 0.75rem;
    font-size: 0.82rem;
  }

  .huge-search-input {
    padding: 1rem 3.5rem 1rem 1.2rem;
    font-size: 1rem;
    border-radius: 14px;
  }

  .search-icon-btn {
    right: 1rem;
  }

  .huge-search-wrapper {
    max-width: 100%;
  }

  .main-content {
    padding: 0.5rem 0.8rem 2rem 0.8rem;
  }
}
```

### 주의사항
- "개념유사도" 텍스트가 가장 길어 `0.75rem` 패딩에서도 한 줄 유지 가능한지 375px 기기에서 확인 필요
- 필요 시 "유사도" 등 2글자 축약 (data-short-label 속성 추가 후 JS로 교체)

---

## Step C: 검색결과 Inspector Mode (핵심)

### 현재 구조
`renderMainTable()` 함수가 `<tr>` 생성 시 `.tooltip-trigger`를 붙이고, `mousemove`/`mouseout` 이벤트로 `globalTooltip`에 해설 표시.

- `data-tooltip`: 해설 HTML (encodeURIComponent)
- `data-tooltip-wide`: 넓은 툴팁 여부
- 문항ID 셀: 섬네일 이미지 팝업
- 스텝 셀: 해설 팝업
- 개념 셀: 성취기준 팝업

### 문제
터치 기기에서 `mousemove`는 발동 안 함 → 해설/섬네일을 전혀 볼 수 없음.

### 대책: Inspector Mode

**개념:** 검색결과 행을 탭하면 하단 고정 패널에 해당 해설이 고정 표시됨. 다른 행 탭하면 교체. 닫기 버튼으로 패널 닫기.

**HTML (index.html `</body>` 직전에 추가):**
```html
<!-- 모바일 Inspector 패널 -->
<div id="inspector-panel" style="display:none;">
  <div id="inspector-panel-inner">
    <div id="inspector-panel-header">
      <span id="inspector-panel-title" style="font-size:0.85rem; color:var(--text-muted);"></span>
      <button id="inspector-close-btn" onclick="closeInspector()">✕</button>
    </div>
    <div id="inspector-panel-body" class="latex-font"></div>
  </div>
</div>
```

**CSS (`@media (pointer: coarse)` 블록):**
```css
@media (pointer: coarse) {
  #inspector-panel {
    position: fixed;
    bottom: 0; left: 0; right: 0;
    max-height: 55dvh;
    background: var(--bg-surface);
    border-top: 1px solid var(--border-color);
    border-radius: 16px 16px 0 0;
    z-index: 9500;
    overflow-y: auto;
    padding: 1rem;
    transform: translateY(100%);
    transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  }

  #inspector-panel.open {
    transform: translateY(0);
  }

  #inspector-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.8rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-color);
  }

  #inspector-close-btn {
    background: none; border: none;
    color: var(--text-muted); cursor: pointer;
    font-size: 1.2rem; line-height: 1;
  }
}
```

**JS (renderMainTable 함수의 `searchTbody.appendChild(tr)` 직후 또는 이벤트 위임으로 추가):**
```js
// Inspector Mode: 터치 기기에서 행 탭 시 하단 패널에 해설 표시
function openInspector(content, title) {
  const panel = document.getElementById('inspector-panel');
  const body  = document.getElementById('inspector-panel-body');
  const titleEl = document.getElementById('inspector-panel-title');
  panel.style.display = 'block';
  body.innerHTML = content;
  titleEl.textContent = title || '';
  // 패널 열림 애니메이션
  requestAnimationFrame(() => panel.classList.add('open'));
  // KaTeX 재렌더링 (수식 포함 가능)
  if (window.renderMathInElement) {
    renderMathInElement(body, {
      delimiters: [
        { left: '$$', right: '$$', display: true },
        { left: '$', right: '$', display: false }
      ]
    });
  }
  // body 스크롤 잠금
  document.body.style.overflow = 'hidden';
}

function closeInspector() {
  const panel = document.getElementById('inspector-panel');
  panel.classList.remove('open');
  document.body.style.overflow = '';
  setTimeout(() => { panel.style.display = 'none'; }, 300);
}

// 이벤트 위임: 검색결과 테이블 탭
document.addEventListener('click', (e) => {
  if (!isTouchDevice()) return;
  const trigger = e.target.closest('.tooltip-trigger');
  if (!trigger) return;
  const content = decodeURIComponent(trigger.getAttribute('data-tooltip') || '');
  if (!content) return;
  e.preventDefault();
  e.stopPropagation();
  // 문항ID 탭 → 섬네일 표시 (이미 onclick="toggleCartItem" 있으므로 섬네일만 Inspector에)
  const probId = trigger.getAttribute('data-prob-id');
  const title  = probId ? `문항 ${probId}` : '';
  openInspector(content, title);
});
```

### 주의사항
- `onclick="toggleCartItem('${pid}')"` 이 이미 문항ID 셀에 붙어있음  
  → 터치 기기에서 탭 시 Inspector 열기 + 장바구니 추가가 동시에 발생할 수 있음  
  → Inspector 이벤트에서 `e.stopPropagation()` 후, 장바구니 추가는 Inspector 패널 안에 별도 버튼으로 제공 (`담기` 버튼)
- 패널 열려있을 때 스크롤: `#inspector-panel`은 자체 `overflow-y: auto`, body는 잠금
- MathJax가 아닌 KaTeX 사용 중이므로 `renderMathInElement` 호출로 충분 (기존 코드와 동일)

---

## Step D: 장바구니 FAB + 바텀시트

### 현재 구조
`#problem-cart`: `position: fixed; right: 0; width: 240px; transform: translateX(100%)`  
`#cart-toggle-btn`: 카트 왼쪽에 붙어있는 토글 탭

### 변경 내용

**CSS (`@media (pointer: coarse)`):**
```css
@media (pointer: coarse) {
  /* 기존 사이드바 형태 비활성화 */
  #problem-cart {
    top: auto;
    bottom: 0; left: 0; right: 0;
    width: 100%;
    height: 70dvh;
    transform: translateY(100%);    /* 숨김 방향 변경 */
    border-left: none;
    border-top: 1px solid var(--border-color);
    border-radius: 20px 20px 0 0;
    padding: 1rem 1rem 2rem 1rem;   /* 하단 safe-area 대비 여백 */
    z-index: 9000;
    backdrop-filter: none;           /* iOS fixed+blur 버그 방지 */
    -webkit-backdrop-filter: none;
  }

  #problem-cart.open {
    transform: translateY(0);
  }

  /* 기존 사이드 토글 버튼 숨김 */
  #cart-toggle-btn {
    display: none;
  }

  /* FAB 버튼 */
  #cart-fab {
    display: flex;
    position: fixed;
    bottom: 1.5rem; right: 1.5rem;
    width: 52px; height: 52px;
    border-radius: 50%;
    background: var(--accent-cyan);
    color: #030712;
    border: none;
    cursor: pointer;
    align-items: center; justify-content: center;
    font-size: 1.4rem;
    box-shadow: 0 4px 16px rgba(6,182,212,0.5);
    z-index: 10000;
    transition: transform 0.2s;
  }
  #cart-fab:active { transform: scale(0.92); }

  /* FAB 뱃지 (담은 문항 수) */
  #cart-fab-badge {
    position: absolute;
    top: -4px; right: -4px;
    background: var(--accent-magenta);
    color: #fff;
    border-radius: 999px;
    font-size: 0.7rem; font-weight: 700;
    min-width: 18px; height: 18px;
    display: flex; align-items: center; justify-content: center;
    padding: 0 4px;
  }
}
```

**HTML (index.html, `#problem-cart` 직전에 추가):**
```html
<!-- 모바일 FAB (pointer: coarse에서만 보임) -->
<button id="cart-fab" style="display:none;" onclick="toggleCart()">
  🛒
  <span id="cart-fab-badge" style="display:none;">0</span>
</button>
```

**JS:**
```js
// 모바일 FAB 표시 및 카트 토글
if (isTouchDevice()) {
  document.getElementById('cart-fab').style.display = 'flex';
}

// 기존 toggleCart() 함수가 있으면 수정, 없으면 신규 추가
// 기존: problem-cart.classList.toggle('open')
// 추가: 바텀시트 열릴 때 body 스크롤 잠금
const origToggleCart = window.toggleCart;
window.toggleCart = function() {
  const cart = document.getElementById('problem-cart');
  const isOpen = cart.classList.contains('open');
  if (isOpen) {
    cart.classList.remove('open');
    document.body.style.overflow = '';
  } else {
    cart.classList.add('open');
    if (isTouchDevice()) document.body.style.overflow = 'hidden';
  }
};

// 장바구니 아이템 수 변경 시 뱃지 업데이트 (기존 cartItems 변경 로직 찾아서 후킹)
function updateCartFabBadge(count) {
  const badge = document.getElementById('cart-fab-badge');
  if (!badge) return;
  if (count > 0) {
    badge.style.display = 'flex';
    badge.textContent = count;
  } else {
    badge.style.display = 'none';
  }
}
```

**뱃지 업데이트 연결:**  
기존 `toggleCartItem()` 또는 카트 목록 렌더 함수(`renderCartList()` 등) 끝에 추가:
```js
updateCartFabBadge(cartItems.length);  // cartItems는 기존 변수명에 맞게 조정
```

### 주의사항
- `transform: translateY(100%)` 전환 시 기존 `translateX(100%)`와 방향이 다름 → CSS transition은 transform만 다루므로 충돌 없음
- Inspector 패널(`z-9500`)보다 FAB(`z-10000`)가 위에 있어야 함
- 바텀시트 열려있을 때 Inspector도 열리면 두 패널이 겹침 → Inspector가 열려있으면 FAB 탭 시 Inspector 먼저 닫기:
  ```js
  window.toggleCart = function() {
    closeInspector();  // Inspector 닫기 먼저
    // ... 기존 로직
  };
  ```

---

## Step E: 성취기준 뷰 탭 전환

### 현재 구조
`view-concepts` 섹션 안의 `.split-pane-layout`:  
`grid-template-columns: 320px 1fr; height: 650px`

### 변경 내용

**CSS (`@media (pointer: coarse)`):**
```css
@media (pointer: coarse) {
  .split-pane-layout.active {
    display: flex;
    flex-direction: column;
    height: auto;
    gap: 0;
  }

  /* 왼쪽 패널(트리): 탭 전환 */
  .split-pane-layout .pane-box:first-child {
    border-radius: 12px 12px 0 0;
    border-bottom: none;
  }

  .split-pane-layout .pane-box:last-child {
    border-radius: 0 0 12px 12px;
    min-height: 400px;
  }

  /* 모바일 탭 헤더 */
  .mobile-split-tabs {
    display: flex;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 1rem;
  }

  .mobile-split-tab {
    flex: 1; padding: 0.6rem;
    text-align: center; font-size: 0.85rem;
    color: var(--text-muted); cursor: pointer;
    border-bottom: 2px solid transparent;
  }

  .mobile-split-tab.active {
    color: var(--accent-cyan);
    border-bottom-color: var(--accent-cyan);
  }

  /* 패널 숨김/표시 */
  .split-pane-layout .pane-box.hidden {
    display: none;
  }
}
```

**JS (기존 `renderConceptTree()` 함수 이후에 추가):**
```js
// 모바일 성취기준 뷰: 탭 전환
function initMobileSplitTabs() {
  if (!isTouchDevice()) return;
  const layout = document.querySelector('.split-pane-layout');
  if (!layout || layout.querySelector('.mobile-split-tabs')) return;

  const panes = layout.querySelectorAll('.pane-box');
  if (panes.length < 2) return;

  // 탭 헤더 삽입
  const tabBar = document.createElement('div');
  tabBar.className = 'mobile-split-tabs';
  tabBar.innerHTML = `
    <div class="mobile-split-tab active" data-pane="0">탐색</div>
    <div class="mobile-split-tab" data-pane="1">결과</div>
  `;
  layout.insertBefore(tabBar, panes[0]);

  // 탭 클릭
  tabBar.addEventListener('click', (e) => {
    const tab = e.target.closest('.mobile-split-tab');
    if (!tab) return;
    const idx = parseInt(tab.dataset.pane);
    tabBar.querySelectorAll('.mobile-split-tab').forEach((t, i) => {
      t.classList.toggle('active', i === idx);
    });
    panes.forEach((p, i) => p.classList.toggle('hidden', i !== idx));
  });

  // 초기: 트리에서 항목 선택 시 자동으로 결과 탭으로 전환
  layout.addEventListener('click', (e) => {
    if (!e.target.closest('.obs-file-leaf')) return;
    // 결과 탭(1번)으로 자동 전환
    tabBar.querySelectorAll('.mobile-split-tab').forEach((t, i) => {
      t.classList.toggle('active', i === 1);
    });
    panes.forEach((p, i) => p.classList.toggle('hidden', i !== 1));
  });
}

// switchView('concepts') 호출 후 initMobileSplitTabs() 호출 추가
```

**기존 `switchView` 함수 내 `concepts` case에 추가:**
```js
case 'concepts':
  // 기존 코드 ...
  initMobileSplitTabs();  // ← 추가
  break;
```

---

## Step F: 통계 카드 그리드 (overview)

### 현재 구조
`grid-template-columns: repeat(4, 1fr)` — index.html 214행 인라인 style

### 변경 내용

인라인 style을 CSS 클래스로 교체한 뒤 미디어쿼리 적용:

**HTML 수정 (214행):**
```html
<!-- before -->
<div style="... grid-template-columns: repeat(4, 1fr); gap: 1rem;">

<!-- after -->
<div class="stats-grid" style="display: grid; gap: 1rem;">
```

**CSS:**
```css
.stats-grid {
  grid-template-columns: repeat(4, 1fr);
}

@media (pointer: coarse) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
```

---

## Step G: onmouseover hover stuck 방지

### 대상 요소 (12개 핸들러)

| 행 | 요소 | 핸들러 내용 |
|----|------|------------|
| 321-322 | 이전 검색 버튼 | background 색상 변경 |
| 338-339 | 다음 검색 버튼 | background 색상 변경 |
| 423-424 | 카트 인쇄 버튼 | gradient 변경 |
| 453-454 | 케밥 메뉴 항목 | background 변경 |
| 463-464 | 케밥 메뉴 항목 | background 변경 |
| 1183 | step-title 링크 | opacity 변경 |
| 1593 | 팁 모달 닫기 | color 변경 |

**수정 방식:** 각 인라인 `onmouseover`/`onmouseout`에 터치 기기 가드 추가.

터치 기기에서는 `:hover` pseudo-class가 탭 후 stuck 상태로 남음. 해결책은 인라인 핸들러 제거 + CSS로 처리.

**CSS에 hover 스타일 이관 (pointer: fine 한정):**
```css
/* pointer: fine = 마우스 기기에서만 hover 효과 */
@media (pointer: fine) {
  #history-back-btn:hover,
  #history-fwd-btn:hover {
    background: rgba(217,70,239,0.25) !important;
  }

  #preview-btn:hover {
    background: linear-gradient(90deg,rgba(217,70,239,0.4),rgba(6,182,212,0.4)) !important;
  }

  .kebab-menu-item:hover {
    background: rgba(6,182,212,0.1) !important;
  }

  .step-title-clickable:hover {
    opacity: 1 !important;
  }
}
```

**HTML 수정:** 대상 요소들의 인라인 `onmouseover`/`onmouseout` 속성 제거.

---

## Step H: iOS 렌더링 버그 패치

### H-1. `position: fixed` + `backdrop-filter` 조합 제거

iOS Safari에서 `position: fixed` 요소에 `backdrop-filter`를 적용하면 스크롤 시 렌더링 깨짐.

**대상 (pointer: coarse에서):**
- `#problem-cart` (Step D에서 이미 `backdrop-filter: none` 처리)
- `#inspector-panel` (Step C에서 이미 없음)
- `mobile-appbar` (Step A에서 이미 `backdrop-filter: none` 처리)
- `.glass` 클래스가 붙은 fixed 요소들 — `.glass`의 `backdrop-filter` 모바일에서 비활성화:

```css
@media (pointer: coarse) {
  .glass {
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
}
```

### H-2. `100vh` → `100dvh` 교체

iOS Safari에서 `100vh`는 주소표시줄 포함 높이로 계산됨 → 하단 요소가 잘림.

**대상:**
```css
@media (pointer: coarse) {
  #problem-cart   { height: 70dvh; }   /* Step D */
  #inspector-panel { max-height: 55dvh; } /* Step C */
  body            { min-height: 100dvh; }
}
```

`dvh`는 iOS 15.4+ 지원. 구형 대응 필요 시 fallback:
```css
height: 70vh;      /* fallback */
height: 70dvh;     /* override */
```

### H-3. 300ms 탭 딜레이

`<meta name="viewport" content="width=device-width, initial-scale=1.0">`가 이미 존재 → 현대 브라우저(iOS 13+, Android Chrome 32+)에서 자동 해소. 추가 조치 불필요.

---

## Step I: landing.html 모바일 대응

### 현재 상태
- `@media (max-width: 768px)` 1개만 존재 (features 섹션)
- 크롬 경고 배너(`.chrome-warning-banner`)가 모바일에서도 표시됨
- 다운로드 버튼이 모바일에 맞지 않음
- Features Mock UI 섬세한 구조 → 모바일에서 너무 작고 복잡

### 변경 내용

#### I-1. 크롬 경고 배너 — 모바일에서 숨김
```css
@media (pointer: coarse) {
  .chrome-warning-banner {
    display: none;
  }
}
```

#### I-2. 다운로드 버튼 — 모바일 텍스트 교체
다운로드 버튼의 텍스트를 모바일에서 "웹에서 바로 사용하기"로 교체하거나 버튼 자체를 숨기고 웹 앱 링크로 대체.
```css
@media (pointer: coarse) {
  .download-btn-group {
    display: none;
  }
  .mobile-webapp-cta {
    display: block;  /* 기본값 none, 모바일에서만 표시 */
  }
}
```

#### I-3. Features Mock UI — 모바일 단순화
복잡한 mock UI 대신 스크린샷 이미지 1장으로 교체 (pointer: coarse 분기):
```css
@media (pointer: coarse) {
  .features-mock-ui {
    display: none;
  }
  .features-mobile-screenshot {
    display: block;
  }
}
```

---

## 공통 리스크 체크리스트

구현 완료 후 아래 항목 검증:

| # | 체크 항목 | 확인 방법 |
|---|-----------|-----------|
| 1 | PC Chrome/Safari에서 기존 기능 동일하게 작동 | 수동 테스트: hover, 카트 사이드바, 툴팁 |
| 2 | iOS Safari 17+에서 앱바 fixed 렌더링 정상 | iPhone 실기기 또는 Safari 시뮬레이터 |
| 3 | Android Chrome에서 Inspector Mode 작동 | 실기기 또는 DevTools 터치 에뮬레이션 |
| 4 | 장바구니 FAB 뱃지 수가 실제 아이템 수와 일치 | 문항 담기/빼기 테스트 |
| 5 | Inspector + 장바구니 바텀시트 동시 열림 방지 | 두 패널 순서대로 탭 테스트 |
| 6 | 성취기준 탭 전환 후 KaTeX 렌더링 정상 | 탭 전환 후 수식 표시 확인 |
| 7 | 인쇄 미리보기 — 모바일에서 진입 불필요 (장바구니 안 미리보기 버튼은 바텀시트 안에 있으므로 그대로 작동) | 바텀시트에서 인쇄 버튼 탭 |
| 8 | `dvh` 미지원 구형 iOS (15.4 미만) 에서 레이아웃 깨짐 없음 | fallback `vh` 확인 |

---

## z-index 맵 (충돌 방지)

| 요소 | z-index |
|------|---------|
| `.glass`, `.pane-box` 등 일반 | 1 ~ 10 |
| `#problem-cart` | 9000 |
| `#inspector-panel` | 9500 |
| `#global-actions-left` (PC only) | 9999 |
| `#auth-app-section` (PC only) | 9999 |
| `#mobile-appbar` | 10000 |
| `#cart-fab` | 10000 |
| 모달 (`#custom-alert-modal` 등) | 10100 |

---

## 파일별 변경 요약

| 파일 | 변경 유형 | 변경 범위 |
|------|-----------|-----------|
| `static/style.css` | CSS 추가 | `@media (pointer: coarse)` 블록 신규 추가, `@media (pointer: fine)` hover 블록 추가 |
| `templates/index.html` | HTML 추가 | `mobile-appbar` div, `cart-fab` button, `inspector-panel` div |
| `templates/index.html` | JS 추가 | `isTouchDevice()`, `openInspector()`, `closeInspector()`, `updateCartFabBadge()`, `initMobileSplitTabs()`, `toggleCart()` 수정 |
| `templates/index.html` | HTML 수정 | 인라인 `onmouseover`/`onmouseout` 12개 제거, stats-grid 클래스 추가 |
| `templates/landing.html` | CSS 추가 | `@media (pointer: coarse)` 블록 추가 |

**index.html JS 수정 없이 기존 PC 로직은 그대로 유지됨.** 모든 터치 분기는 `if (isTouchDevice()) return` 또는 `@media (pointer: coarse)` CSS로 격리.
