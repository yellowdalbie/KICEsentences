# 문항지 세트 기능 구현 지시서

> 작성일: 2026-03-24
> 상태: 확정 설계
> 구현 우선순위: Phase 1(개인 저장·복원) → Phase 2(공개 공유, 별도 일정)

---

## 1. 기능 개요

사용자가 장바구니에 담아 인쇄한 문항 구성을 **세트**로 저장하고, 이후 한 번의 클릭으로 동일한 장바구니 상태를 복원하는 기능이다.

### 저장 종류 (두 가지만 존재)

| 종류 | 트리거 | 개수 제한 | 이름 결정 방식 |
|------|--------|-----------|----------------|
| **임시저장 (temp)** | `[미리보기/인쇄]` 클릭 | 사용자당 최대 1개 | Case3 자동생성 + 날짜시간 (DB 저장명) |
| **완전저장 (final)** | `[PDF저장]` 클릭 또는 명시적 저장 프롬프트 | 무제한 | 미리보기 타이틀 + 날짜시간 (또는 사용자 입력) |

### 핵심 원칙
- **임시저장은 사용자당 1개만 존재한다.** `[미리보기/인쇄]`를 다시 누르면 기존 임시저장을 덮어쓴다.
- **`[PDF저장]` 클릭 시 임시저장 → 완전저장으로 승격되며, 임시저장 레코드는 삭제된다.**
  결과적으로 PDF저장 후 다음 접속 시 장바구니는 비어 있다.
- **`[PDF저장]` 없이 종료하면 임시저장이 유지된다.**
  다음 접속 시 그 상태로 장바구니가 복원된다.

---

## 2. DB 스키마

### 2-1. `users` 테이블 — 컬럼 추가

```sql
ALTER TABLE users ADD COLUMN display_name TEXT;
```

- 기본값: NULL (NULL이면 표시 시 이메일 앞부분 `@` 이전 사용)
- 마이페이지에서 사용자가 직접 편집 가능
- 공개 세트 구현 시 이 값을 제작자 표시에 사용 (Phase 2)

마이그레이션 처리 (`get_db_connection()` 내 기존 migration 블록에 추가):

```python
try:
    cursor = conn.execute("PRAGMA table_info(users)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'display_name' not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
except:
    pass
```

---

### 2-2. `problem_sets` 테이블 — 신규 생성

```sql
CREATE TABLE IF NOT EXISTS problem_sets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'final',
    -- 'temp': 임시저장 / 'final': 완전저장
    title        TEXT    NOT NULL,
    -- 저장명 (날짜시간 포함하지 않음. 목록 1줄에 표시)
    -- 예: "미적분Ⅰ 극값 조건 4문항" 또는 사용자 입력 타이틀
    problem_ids  TEXT    NOT NULL,
    -- JSON 배열 문자열. 순서가 중요함.
    -- 예: '["2024수능_29","2024수능_30","2023.9모_21"]'
    -- ※ cartProblemIds(Set)가 아닌 미리보기 사이드바 순서로 저장할 것
    print_config TEXT,
    -- JSON 문자열. 인쇄 설정 보존용.
    -- 예: '{"showExplanation": false}'
    -- 향후 확장을 위해 컬럼만 만들어두고 Phase 1에서는 NULL 허용
    is_favorite  INTEGER NOT NULL DEFAULT 0,
    -- 0: 일반 / 1: 즐겨찾기
    source_query TEXT,
    -- 세트 구성에 사용된 검색어 (자동명칭 생성용 참고 데이터)
    -- 클라이언트에서 전송. NULL 허용.
    created_at   DATETIME DEFAULT (datetime('now', '+9 hours')),
    updated_at   DATETIME DEFAULT (datetime('now', '+9 hours'))
);

CREATE INDEX IF NOT EXISTS idx_sets_user  ON problem_sets(user_id);
CREATE INDEX IF NOT EXISTS idx_sets_status ON problem_sets(user_id, status);
```

### 2-3. `problem_sets` 제약 조건 (애플리케이션 레벨에서 강제)

SQLite는 조건부 유니크 제약을 직접 지원하지 않으므로, **API에서 반드시 강제한다.**

> **규칙:** `status = 'temp'`인 레코드는 동일 `user_id`에 대해 최대 1개만 존재한다.
> 임시저장 API 호출 시 기존 temp 레코드를 먼저 삭제 후 새로 삽입하거나 UPDATE한다.

---

## 3. 자동 명칭 생성 (Case 3)

`[미리보기/인쇄]` 클릭 시 임시저장 명칭과 인쇄 미리보기 기본 타이틀을 자동 생성한다.

### 3-1. 명칭 구성 알고리즘 (서버 사이드)

입력: `problem_ids` 배열
처리:

1. **주제 분류** — DB에서 각 problem_id에 속한 step들의 `action_concept_id`를 조회.
   가장 많이 등장하는 `action_concept_id`의 `standard_name` 앞 분류를 주제로 사용.
   분류 우선순위 예: `CPT-CA1` → "미적분Ⅰ", `CPT-STA` → "확률과통계", `CPT-ALG` → "대수", `CPT-CM1/CM2` → "공통수학"
   복수 주제가 비슷하면 → "혼합"

2. **난이도 힌트** — 문항 번호 추출 (problem_id 마지막 `_` 이후 숫자).
   전체 문항의 과반이 21번 이상이면 → "고난도" 접미사 추가
   과반이 15번 이하이면 → "기본" 접미사 추가
   그 외 → 접미사 없음

3. **문항 수** — `len(problem_ids)`를 `N문항`으로 표기

4. **조합 예시**
   ```
   "미적분Ⅰ 고난도 4문항"
   "확률과통계 3문항"
   "혼합 기본 6문항"
   "공통수학 5문항"
   ```

### 3-2. 명칭 사용 위치별 처리

| 위치 | 값 |
|------|----|
| DB `title` 필드 (임시저장) | Case3 결과만 (날짜시간 없음) |
| DB `title` 필드 (완전저장-PDF) | 미리보기 타이틀 (날짜시간 없음) |
| 인쇄 미리보기 기본 타이틀 | Case3 결과만 (날짜시간 없음) |
| PDF 파일명 (`document.title` 주입) | `{title}_{YYYYMMDD_HHmm}` |
| 목록 1줄 표시 | `title` 그대로 |
| 목록 2줄 표시 | `created_at` (YYYY-MM-DD HH:mm) |

### 3-3. 자동 명칭 생성 API

`GET /api/sets/auto_title?ids=2024수능_29,2024수능_30,...`

```python
@app.route('/api/sets/auto_title')
def sets_auto_title():
    ids_str = request.args.get('ids', '').strip()
    if not ids_str:
        return jsonify({'title': '문항 세트'})
    problem_ids = [x.strip() for x in ids_str.split(',') if x.strip()]
    title = _generate_set_title(problem_ids)  # 내부 함수
    return jsonify({'title': title})
```

이 API는 클라이언트가 `[미리보기/인쇄]` 클릭 직전에 호출해서 받은 값을:
- 임시저장 payload의 `title`로 사용
- 인쇄 미리보기 타이틀 input의 기본값으로 사용

---

## 4. Backend API 상세

모든 세트 API는 `OFFLINE_MODE`일 경우 `{'status': 'ok'}` 또는 빈 응답을 반환하고 처리하지 않는다.
모든 세트 API는 로그인 세션 필수 (`session['user_id']` 없으면 401).

---

### 4-1. `POST /api/sets/temp` — 임시저장 생성/교체

**호출 시점:** `[미리보기/인쇄]` 버튼 클릭 시 (미리보기 열기 직전)

**Request body (JSON):**
```json
{
  "problem_ids": ["2024수능_29", "2024수능_30"],
  "title": "미적분Ⅰ 고난도 2문항",
  "source_query": "롤의 정리"
}
```

- `problem_ids`: 미리보기에서 표시될 순서 그대로. 클라이언트에서 현재 `cartProblemIds`를 배열로 변환해 전송.
  ※ 이 시점은 아직 미리보기 사이드바 순서 변경 전이므로 카트 순서를 사용해도 무방.
- `title`: 클라이언트가 `/api/sets/auto_title`로 받아온 값
- `source_query`: 클라이언트 세션에서 추적한 마지막 유효 검색어 (없으면 `null`)

**서버 처리:**
```python
# 1. 기존 temp 레코드 삭제
conn.execute("DELETE FROM problem_sets WHERE user_id=? AND status='temp'", (user_id,))

# 2. 새 temp 레코드 삽입
conn.execute("""
    INSERT INTO problem_sets (user_id, status, title, problem_ids, source_query)
    VALUES (?, 'temp', ?, ?, ?)
""", (user_id, title, json.dumps(problem_ids, ensure_ascii=False), source_query))
```

**Response:**
```json
{"status": "ok", "id": 42}
```

---

### 4-2. `POST /api/sets/final` — 완전저장 (PDF저장 경로)

**호출 시점:** `[PDF저장]` 버튼 클릭 후 `window.print()` 호출 직전

**Request body (JSON):**
```json
{
  "problem_ids": ["2024수능_30", "2024수능_29"],
  "title": "사용자가 수정한 타이틀",
  "source_query": "롤의 정리"
}
```

- `problem_ids`: 인쇄 미리보기 사이드바(`#sidebar-order-list`)의 **현재 순서**로 구성. `cartProblemIds`(Set)가 아닌 사이드바 DOM 순서에서 읽어야 한다.
- `title`: 인쇄 미리보기 타이틀 영역(`.exam-title`)의 현재 `textContent`. 비어있으면 임시저장 title 사용.

**서버 처리:**
```python
# 1. 기존 temp 레코드를 final로 승격 (있으면)
existing_temp = conn.execute(
    "SELECT id FROM problem_sets WHERE user_id=? AND status='temp'",
    (user_id,)
).fetchone()

if existing_temp:
    conn.execute("""
        UPDATE problem_sets
        SET status='final', title=?, problem_ids=?, updated_at=datetime('now','+9 hours')
        WHERE id=?
    """, (title, json.dumps(problem_ids, ensure_ascii=False), existing_temp['id']))
else:
    # temp 없이 바로 final 저장하는 경우 (명시적 저장 프롬프트 경로)
    conn.execute("""
        INSERT INTO problem_sets (user_id, status, title, problem_ids, source_query)
        VALUES (?, 'final', ?, ?, ?)
    """, (user_id, title, json.dumps(problem_ids, ensure_ascii=False), source_query))
```

**Response:**
```json
{"status": "ok", "id": 42}
```

---

### 4-3. `GET /api/sets/my` — 내 세트 목록 조회

**호출 시점:** `[작성된 문항지]` 패널 진입 시

**Query params:** 없음

**서버 처리:**
```python
rows = conn.execute("""
    SELECT id, status, title, problem_ids, is_favorite, created_at, updated_at
    FROM problem_sets
    WHERE user_id = ?
    ORDER BY is_favorite DESC, updated_at DESC
""", (user_id,)).fetchall()
```

즐겨찾기 항목을 위로, 그 다음은 최신순.

**Response:**
```json
{
  "sets": [
    {
      "id": 42,
      "status": "final",
      "title": "미적분Ⅰ 고난도 2문항",
      "problem_count": 2,
      "is_favorite": 1,
      "created_at": "2026-03-24 14:30"
    },
    ...
  ]
}
```

`problem_ids`의 raw JSON은 응답에 포함하지 않는다. `problem_count`만 포함.
목록 UI에서는 상세 내용 불필요. 선택 시 별도 로드.

---

### 4-4. `GET /api/sets/restore` — 임시저장 복원

**호출 시점:** 앱 로드 시 (로그인 상태 확인 후)

**서버 처리:**
```python
row = conn.execute("""
    SELECT id, title, problem_ids, created_at
    FROM problem_sets
    WHERE user_id=? AND status='temp'
""", (user_id,)).fetchone()

if not row:
    return jsonify({'has_temp': False})

return jsonify({
    'has_temp': True,
    'id': row['id'],
    'title': row['title'],
    'problem_ids': json.loads(row['problem_ids']),
    'created_at': row['created_at']
})
```

---

### 4-5. `GET /api/sets/:id` — 세트 상세 (선택 시 로드)

**호출 시점:** 목록에서 항목 클릭 시

**서버 처리:** `user_id` 일치 확인 필수 (타인 세트 접근 차단)

**Response:**
```json
{
  "id": 42,
  "status": "final",
  "title": "미적분Ⅰ 고난도 2문항",
  "problem_ids": ["2024수능_30", "2024수능_29"],
  "is_favorite": 0,
  "created_at": "2026-03-24 14:30"
}
```

---

### 4-6. `PATCH /api/sets/:id/favorite` — 즐겨찾기 토글

**Request body:** `{}` (body 불필요, 토글이므로)

**서버 처리:**
```python
conn.execute("""
    UPDATE problem_sets
    SET is_favorite = CASE WHEN is_favorite=1 THEN 0 ELSE 1 END,
        updated_at = datetime('now', '+9 hours')
    WHERE id=? AND user_id=?
""", (set_id, user_id))
```

**Response:**
```json
{"is_favorite": 1}
```

---

### 4-7. `DELETE /api/sets/:id` — 세트 삭제

**서버 처리:** `user_id` 일치 확인 필수.

**Response:** `{"status": "ok"}`

---

### 4-8. `PATCH /api/users/display_name` — 별칭 수정

**Request body:**
```json
{"display_name": "새별칭"}
```

유효성 검사:
- 빈 문자열이면 NULL로 저장 (이메일 앞부분으로 폴백)
- 최대 20자 제한
- 앞뒤 공백 strip 처리

**Response:** `{"status": "ok", "display_name": "새별칭"}`

---

## 5. 클라이언트 상태 관리

### 5-1. 검색어 추적 (`cart.js` 전역 변수)

```javascript
// 세션 내 검색어 추적 (세트 자동명칭 생성용)
const searchQueryLog = [];  // [{query, type, addedCount}]

// 검색어 기록 함수 (각 검색 완료 후 결과 렌더링 시점에 호출)
function recordSearchQuery(query, type, resultCount) {
    if (!query || resultCount === 0) return;
    // type: '개념유사도' | '기출표현' | '문항번호' | '성취기준'
    // 개념유사도, 성취기준만 자동명칭에 유용. 나머지는 낮은 우선순위.
    searchQueryLog.push({ query, type, addedCount: 0, ts: Date.now() });
}

// 담기 완료 시 해당 검색어에 addedCount 증가
function markQueryAsUsed(query) {
    const entry = [...searchQueryLog].reverse().find(e => e.query === query);
    if (entry) entry.addedCount++;
}

// 가장 관련성 높은 검색어 반환
function getBestSearchQuery() {
    if (searchQueryLog.length === 0) return null;
    // addedCount가 가장 많은 것 우선, 동수면 최신
    return searchQueryLog
        .filter(e => e.addedCount > 0)
        .sort((a, b) => b.addedCount - a.addedCount || b.ts - a.ts)[0]?.query
        || searchQueryLog[searchQueryLog.length - 1].query;
}
```

### 5-2. 임시저장 복원 상태 추적

```javascript
// 복원된 임시저장의 problem_ids 스냅샷 (변경 감지용)
let restoredTempIds = null;  // null: 복원 없음 / string[]: 복원된 ID 배열

// 장바구니가 임시저장 상태와 동일한지 체크
function cartMatchesTemp() {
    if (!restoredTempIds) return false;
    const current = Array.from(cartProblemIds);
    if (current.length !== restoredTempIds.length) return false;
    return current.every((id, i) => id === restoredTempIds[i]);
}

// 경고 표시 여부 (세션당 1회)
let cartRestoreWarningShown = false;
```

---

## 6. 장바구니 패널 레이아웃 변경

### 6-1. 새 레이아웃 구조

기존 HTML의 장바구니 패널(`#problem-cart`) 내부를 아래와 같이 재구성한다.

```html
<div id="problem-cart">
  <!-- 헤더: 제목 + 닫기 버튼 (기존 유지) -->
  <div class="cart-header">...</div>

  <!-- [작성된 문항지] 버튼 — 새로 추가, 상단 고정 -->
  <button id="btn-my-sets" class="my-sets-btn">
    <svg><!-- 문서 아이콘 --></svg>
    작성된 문항지
  </button>

  <!-- 복원 배너 — 임시저장 복원 시에만 표시, 기본 hidden -->
  <div id="cart-restore-banner" style="display:none;">
    <span id="cart-restore-msg">이전 작업 복원됨</span>
    <button onclick="dismissRestoreBanner()">×</button>
  </div>

  <!-- 담은 문항 목록 — 스크롤 영역 -->
  <div id="cart-items-container" class="cart-items-scroll">
    <!-- JS로 채워짐 -->
  </div>

  <!-- 하단 고정: 미리보기/인쇄 + 더보기 -->
  <div class="cart-footer">
    <button id="preview-btn">미리보기 / 인쇄</button>
    <button id="cart-more-btn">···</button>
  </div>
</div>
```

### 6-2. [작성된 문항지] 패널 (슬라이드 전환)

동일한 `#problem-cart` 내에서 두 뷰를 토글한다.
CSS transform 또는 단순 display 전환으로 구현.

```html
<!-- 장바구니 뷰 (기본) -->
<div id="cart-view">
  <!-- 위 레이아웃 -->
</div>

<!-- 문항지 목록 뷰 (숨김 상태로 시작) -->
<div id="sets-view" style="display:none;">
  <div class="sets-view-header">
    <button onclick="showCartView()">← 돌아가기</button>
    <span>작성된 문항지</span>
  </div>
  <div id="sets-list-container">
    <!-- JS로 채워짐 -->
  </div>
</div>
```

전환 함수:
```javascript
function showSetsView() {
    document.getElementById('cart-view').style.display = 'none';
    document.getElementById('sets-view').style.display = 'flex';
    loadMySets();  // API 호출
}

function showCartView() {
    document.getElementById('sets-view').style.display = 'none';
    document.getElementById('cart-view').style.display = 'flex';
}
```

---

## 7. UX 흐름 상세

### 7-1. 앱 로드 시 복원 흐름

`runAuthInit()` → `initAuth()` 완료 후 로그인 확인 → 로그인 상태이면:

```javascript
async function restoreTempOnLogin() {
    const res = await fetch('/api/sets/restore');
    const data = await res.json();
    if (!data.has_temp) return;

    // 장바구니에 복원
    data.problem_ids.forEach(id => cartProblemIds.add(id));
    restoredTempIds = [...data.problem_ids];
    updateCartUI();

    // 복원 배너 표시
    const banner = document.getElementById('cart-restore-banner');
    const msg = document.getElementById('cart-restore-msg');
    msg.textContent = `이전 작업 복원됨 · ${data.problem_ids.length}문항`;
    banner.style.display = 'flex';
}
```

배너는 사용자가 `×`를 누르기 전까지 유지. 배너 클릭 시 "지우고 새로 시작" 옵션 제공:

```javascript
function dismissRestoreBanner() {
    document.getElementById('cart-restore-banner').style.display = 'none';
}

// 배너 텍스트 클릭 시 선택 옵션 표시
function onRestoreBannerClick() {
    if (!confirm('현재 복원된 문항을 지우고 새로 시작하시겠습니까?')) return;
    cartProblemIds.clear();
    restoredTempIds = null;
    updateCartUI();
    dismissRestoreBanner();
    // 서버의 temp 레코드 삭제
    fetch('/api/sets/restore', { method: 'DELETE' });
}
```

---

### 7-2. 문항 담기 시 경고 (세션 1회)

기존 `toggleCart(id)` 함수 내 담기 처리 직전에 삽입:

```javascript
function toggleCart(id) {
    const strId = String(id);

    // 추가하려는 상황 (이미 담겨있지 않은 경우)
    if (!cartProblemIds.has(strId)) {

        // 복원된 장바구니가 있고, 아직 경고를 안 보여줬을 때
        if (restoredTempIds && restoredTempIds.length > 0 && !cartRestoreWarningShown) {
            cartRestoreWarningShown = true;
            const choice = confirm(
                `이전에 담아두셨던 ${restoredTempIds.length}문항이 있습니다.\n\n` +
                `[확인] 이어서 추가하기\n[취소] 장바구니 비우고 새로 담기`
            );
            if (!choice) {
                // 비우고 담기
                cartProblemIds.clear();
                restoredTempIds = null;
                dismissRestoreBanner();
                fetch('/api/sets/restore', { method: 'DELETE' });
            }
            // 확인이면 그냥 이어서 추가
        }

        // 20문항 초과 경고 (한 번만)
        if (cartProblemIds.size === 20) {
            alert('21번째 문항부터는 인쇄 미리보기 로딩이 다소 느릴 수 있습니다.');
        }
    }

    // 기존 담기/제거 로직 계속
    if (cartProblemIds.has(strId)) {
        cartProblemIds.delete(strId);
    } else {
        cartProblemIds.add(strId);
    }
    updateCartUI();
}
```

---

### 7-3. `[미리보기/인쇄]` 클릭 흐름

```javascript
document.getElementById('preview-btn').addEventListener('click', async () => {
    if (cartProblemIds.size === 0) {
        showCustomAlert('장바구니가 비어 있습니다.');
        return;
    }
    if (!checkAuthForPreview()) return;

    const ids = Array.from(cartProblemIds);

    // 1. 자동 명칭 생성 요청
    const titleRes = await fetch(`/api/sets/auto_title?ids=${ids.join(',')}`);
    const { title } = await titleRes.json();

    // 2. 임시저장 (기존 temp 교체)
    await fetch('/api/sets/temp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            problem_ids: ids,
            title: title,
            source_query: getBestSearchQuery()
        })
    });

    // 3. 복원 배너 숨기기 (새로운 임시저장이 생겼으므로)
    restoredTempIds = [...ids];
    dismissRestoreBanner();

    // 4. 인쇄 미리보기 열기 (기존 openPrintPreview 로직)
    //    미리보기 기본 타이틀에 title 값 주입 (날짜시간 없음)
    currentAutoTitle = title;
    openPrintPreview();
});
```

`openPrintPreview()` 내에서 타이틀 주입:

```javascript
// 기존 코드에서 examTitle 초기화 부분
const examTitles = printModalBody.querySelectorAll('.exam-title');
examTitles.forEach(t => {
    t.textContent = currentAutoTitle || '2026학년도 수학';
});
```

---

### 7-4. `[PDF저장]` 클릭 흐름

기존 `logAndPrint()` 함수를 아래로 교체:

```javascript
async function logAndPrint() {
    // 1. 사이드바 현재 순서에서 problem_ids 추출
    const sidebarItems = document.querySelectorAll('#sidebar-order-list li');
    const orderedIds = Array.from(sidebarItems).map(li => li.dataset.problemId);
    // ※ 사이드바 <li> 요소에 data-problem-id 속성이 없으면 추가 필요

    // 2. 현재 미리보기 타이틀 추출
    const examTitle = document.querySelector('.exam-title');
    const title = (examTitle?.textContent || '').trim() || currentAutoTitle || '문항 세트';

    // 3. 완전저장 API 호출
    await fetch('/api/sets/final', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            problem_ids: orderedIds,
            title: title,
            source_query: getBestSearchQuery()
        })
    });

    // 4. PDF 파일명 설정 (document.title 트릭)
    const now = new Date();
    const datetime = `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}_${String(now.getHours()).padStart(2,'0')}${String(now.getMinutes()).padStart(2,'0')}`;
    const pdfFilename = `${title}_${datetime}`;
    const originalTitle = document.title;
    document.title = pdfFilename;

    // 5. 인쇄
    window.print();

    // 6. document.title 복원
    window.addEventListener('afterprint', () => {
        document.title = originalTitle;
    }, { once: true });

    // 7. 완전저장 완료 피드백 (토스트)
    showToast('저장 완료');

    // 8. 이벤트 로그
    logCartEvent('save_pdf', orderedIds);
}
```

**주의:** 사이드바 `<li>` 요소에 `data-problem-id` 속성을 부여해야 한다. 사이드바 렌더링 코드에서 각 항목 생성 시 추가할 것.

---

### 7-5. `[작성된 문항지]` 버튼 클릭 흐름

```javascript
document.getElementById('btn-my-sets').addEventListener('click', async () => {
    const hasCartItems = cartProblemIds.size > 0;
    const cartMatchesTemp_ = cartMatchesTemp();

    if (hasCartItems && !cartMatchesTemp_) {
        // 저장 안 된 상태 → 저장 여부 묻기
        const wantSave = confirm('현재 담은 문항을 저장하시겠습니까?');
        if (wantSave) {
            // 이름 입력 받기
            const ids = Array.from(cartProblemIds);
            const titleRes = await fetch(`/api/sets/auto_title?ids=${ids.join(',')}`);
            const { title: autoTitle } = await titleRes.json();
            const inputTitle = prompt('저장할 이름을 입력하세요:', autoTitle);
            if (inputTitle === null) return;  // 취소 → 진행 중단

            await fetch('/api/sets/final', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    problem_ids: ids,
                    title: inputTitle.trim() || autoTitle,
                    source_query: getBestSearchQuery()
                })
            });
            restoredTempIds = [...ids];
        }
    }

    // 목록 뷰로 전환
    showSetsView();
});
```

---

### 7-6. 문항지 목록 렌더링

```javascript
async function loadMySets() {
    const res = await fetch('/api/sets/my');
    const { sets } = await res.json();
    const container = document.getElementById('sets-list-container');
    container.innerHTML = '';

    if (sets.length === 0) {
        container.innerHTML = '<p class="sets-empty">저장된 문항지가 없습니다.</p>';
        return;
    }

    sets.forEach(set => {
        const item = document.createElement('div');
        item.className = 'set-item';
        item.dataset.setId = set.id;
        item.innerHTML = `
            <div class="set-item-main" onclick="loadSetToCart(${set.id})">
                <div class="set-item-title">
                    ${set.status === 'temp' ? '<span class="badge-temp">임시</span>' : ''}
                    ${escapeHtml(set.title)}
                </div>
                <div class="set-item-meta">${set.created_at}</div>
            </div>
            <button class="set-fav-btn ${set.is_favorite ? 'active' : ''}"
                    onclick="toggleFavorite(event, ${set.id})"
                    title="즐겨찾기">★</button>
            <button class="set-del-btn"
                    onclick="deleteSet(event, ${set.id})"
                    title="삭제">×</button>
        `;
        // 마우스 오버: 문항 수 툴팁
        item.querySelector('.set-item-main').title = `${set.problem_count}문항`;
        container.appendChild(item);
    });
}
```

---

### 7-7. 목록에서 세트 선택 (장바구니 교체)

```javascript
async function loadSetToCart(setId) {
    // 현재 장바구니에 내용이 있고, 저장된 상태가 아니면 경고
    if (cartProblemIds.size > 0 && !cartMatchesTemp()) {
        if (!confirm(`현재 담긴 ${cartProblemIds.size}문항이 사라집니다. 교체하시겠습니까?`)) return;
    }

    const res = await fetch(`/api/sets/${setId}`);
    const set = await res.json();

    // 장바구니 교체
    cartProblemIds.clear();
    set.problem_ids.forEach(id => cartProblemIds.add(id));
    restoredTempIds = [...set.problem_ids];
    cartRestoreWarningShown = true;  // 방금 로드했으니 경고 불필요

    updateCartUI();
    showCartView();  // 목록 → 장바구니 뷰로 복귀
}
```

---

### 7-8. 즐겨찾기 토글

```javascript
async function toggleFavorite(event, setId) {
    event.stopPropagation();
    const res = await fetch(`/api/sets/${setId}/favorite`, { method: 'PATCH' });
    const { is_favorite } = await res.json();
    // 버튼 클래스 토글
    event.target.classList.toggle('active', is_favorite === 1);
    // 목록 재정렬 (즐겨찾기가 위로 올라오도록 목록 새로고침)
    loadMySets();
}
```

---

### 7-9. 세트 삭제

```javascript
async function deleteSet(event, setId) {
    event.stopPropagation();
    if (!confirm('이 문항지를 삭제하시겠습니까?')) return;
    await fetch(`/api/sets/${setId}`, { method: 'DELETE' });
    document.querySelector(`.set-item[data-set-id="${setId}"]`).remove();
}
```

---

## 8. 마이페이지 변경

기존 마이페이지 모달(`#change-pw-modal`)은 유지하고, 새로운 마이페이지 모달을 별도로 구성한다.

### 8-1. 진입점

`#auth-app-section` 내 사용자 이메일/별칭 표시 영역 (현재 로그인 후 상태 표시 부분)을 클릭 가능하게 변경:

```javascript
// updateAuthNavUI() 함수 내 로그인 상태 렌더링 부분
const displayName = data.displayName || data.email.split('@')[0];
// 기존 이메일/이름 표시 span을 버튼으로 교체
const userBtn = document.createElement('button');
userBtn.textContent = displayName;
userBtn.onclick = openMyPage;
```

### 8-2. 마이페이지 모달 메뉴 구조

```
마이페이지
├── [내 문항지]        ← 클릭 시 장바구니 패널의 [작성된 문항지]와 동일한 목록 표시
├── [내 정보]          ← 별칭 수정
│     · 별칭: [input] [저장]
│     · 현재 이메일: user@example.com
├── [비밀번호 변경]    ← 기존 기능
└── [회원 탈퇴]        ← 기존 기능
```

### 8-3. [내 문항지] 동작

마이페이지의 [내 문항지]를 클릭하면:
- 마이페이지 모달 내에 목록 렌더링 (`loadMySets()`와 동일 데이터)
- 항목 클릭 시 마이페이지 모달 닫기 → 장바구니 교체 → 장바구니 패널 열기

### 8-4. 별칭 수정

```javascript
async function saveDisplayName(newName) {
    const res = await fetch('/api/users/display_name', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: newName.trim() })
    });
    if (res.ok) {
        showToast('저장되었습니다.');
        // 우상단 표시 이름 업데이트
        updateAuthNavUI();
    }
}
```

---

## 9. `/api/auth/me` 응답 확장

별칭을 클라이언트에 전달하기 위해 응답에 `displayName` 추가:

```python
@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    if 'user_id' in session:
        conn = get_db_connection()
        user = conn.execute(
            'SELECT is_paid, display_name FROM users WHERE id=?',
            (session['user_id'],)
        ).fetchone()
        conn.close()
        if user:
            email = session['email']
            display_name = user['display_name'] or email.split('@')[0]
            return jsonify({
                'isLoggedIn': True,
                'email': email,
                'isPaid': bool(user['is_paid']),
                'displayName': display_name
            }), 200
    return jsonify({'isLoggedIn': False, 'isPaid': False}), 200
```

---

## 10. 오프라인 모드 처리

아래 API들은 `OFFLINE_MODE = True`이면 즉시 빈 응답 반환:

```python
SETS_APIS = [
    '/api/sets/temp', '/api/sets/final', '/api/sets/my',
    '/api/sets/restore', '/api/sets/<id>', '/api/users/display_name'
]
```

각 라우트 핸들러 상단에:
```python
if OFFLINE_MODE:
    return jsonify({'status': 'ok', 'sets': [], 'has_temp': False}), 200
```

클라이언트에서는 `KICE_OFFLINE`이 `true`이면 `[작성된 문항지]` 버튼 자체를 숨김 처리.

---

## 11. 구현 순서 (권장)

```
1. DB 마이그레이션
   - users.display_name 컬럼 추가
   - problem_sets 테이블 생성

2. Backend API
   - /api/sets/auto_title
   - /api/sets/temp (POST)
   - /api/sets/restore (GET, DELETE)
   - /api/sets/final (POST)
   - /api/sets/my (GET)
   - /api/sets/:id (GET, DELETE)
   - /api/sets/:id/favorite (PATCH)
   - /api/users/display_name (PATCH)
   - /api/auth/me 응답에 displayName 추가

3. Frontend — cart.js
   - searchQueryLog, restoredTempIds 등 전역 변수 추가
   - recordSearchQuery(), getBestSearchQuery() 추가
   - toggleCart() — 경고 로직 삽입
   - preview-btn 클릭 핸들러 교체
   - logAndPrint() 교체 (사이드바 순서 캡처 + document.title)
   - btn-my-sets 클릭 핸들러
   - showSetsView(), showCartView()
   - loadMySets(), loadSetToCart()
   - toggleFavorite(), deleteSet()
   - restoreTempOnLogin() — initAuth 완료 후 호출

4. Frontend — index.html
   - 장바구니 패널 HTML 구조 재편
   - sets-view HTML 추가
   - 마이페이지 모달 HTML 추가/개편
   - 사이드바 <li>에 data-problem-id 속성 추가

5. CSS (style.css)
   - .my-sets-btn
   - #cart-restore-banner
   - .cart-footer
   - #sets-view, .set-item, .set-item-title, .set-item-meta
   - .badge-temp
   - .set-fav-btn, .set-del-btn

6. 검증 항목
   - 임시저장 1개 제한: 두 번 preview 클릭 시 DB에 temp 1개인지 확인
   - PDF저장 후 temp 삭제: 다음 /api/sets/restore 응답이 has_temp: false인지
   - 사이드바 순서 반영: 순서 바꾸고 PDF저장 후 목록에서 불러왔을 때 바뀐 순서인지
   - 오프라인 모드: [작성된 문항지] 버튼 숨김 확인
```

---

## 12. 미구현 (Phase 2 이후)

- 공개 세트 탐색 페이지 (`/sets`)
- 세트 공개/비공개 전환
- 커뮤니티 평가 (좋아요, 별점)
- 타인 세트 가져오기
- `print_config` 저장 및 복원 (해설 표시 여부 등)

---

*이 지시서는 설계 확정 후 작성된 것으로, 구현 중 발견된 예외사항은 문서를 업데이트 후 반영할 것.*
