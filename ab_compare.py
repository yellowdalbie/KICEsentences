"""
ab_compare.py
=============
A/B 실험 로컬 대시보드 — 3-tier vs 1-tier 임베딩 비교
실행: python3 ab_compare.py
접속: http://localhost:5050
"""

import os, json, random, sqlite3
import numpy as np
from flask import Flask, jsonify, request, send_from_directory, Response

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
DB_FILE         = os.path.join(BASE_DIR, 'kice_database.sqlite')
VEC_3TIER       = os.path.join(BASE_DIR, 'kice_step_vectors.npz')
VEC_1TIER       = os.path.join(BASE_DIR, 'kice_step_vectors_1tier.npz')
THUMB_DIR       = os.path.join(BASE_DIR, 'static', 'thumbnails')
OPINIONS_FILE   = os.path.join(BASE_DIR, 'ab_opinions.json')
TOP_K           = 10

app = Flask(__name__, static_folder='static')

# ── 벡터 로드 ─────────────────────────────────────────────────────────────────
print("벡터 파일 로드 중...")
_a = np.load(VEC_3TIER, allow_pickle=True)
_b = np.load(VEC_1TIER, allow_pickle=True)

A = {k: _a[k] for k in _a.files}
B = {k: _b[k] for k in _b.files}
print(f"  3-tier: {len(A['step_ids'])}개 / 1-tier: {len(B['step_ids'])}개 로드 완료")

# step_id → index 사전 (빠른 검색)
A_IDX = {int(sid): i for i, sid in enumerate(A['step_ids'])}
B_IDX = {int(sid): i for i, sid in enumerate(B['step_ids'])}


# ── DB 헬퍼 ──────────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def cosine_search(vec_data, idx_map, q_step_id, top_k):
    q_idx = idx_map.get(q_step_id)
    if q_idx is None:
        return []
    q_vec = vec_data['vectors'][q_idx]
    sims  = np.dot(vec_data['vectors'], q_vec)
    sims[q_idx] = -1.0
    top   = np.argsort(sims)[::-1][:top_k]
    return [
        {
            'step_id':    int(vec_data['step_ids'][i]),
            'problem_id': str(vec_data['problem_ids'][i]),
            'step_number':int(vec_data['step_numbers'][i]),
            'concept_id': str(vec_data['concept_ids'][i]),
            'sim':        round(float(sims[i]), 4),
        }
        for i in top
    ]


def enrich_results(results, conn, query_concept):
    """step 결과에 step_title + 해당 문항의 전체 스텝 목록 추가"""
    enriched = []
    for r in results:
        pid = r['problem_id']
        # 해당 문항의 모든 스텝 타이틀 (순서대로)
        rows = conn.execute(
            "SELECT step_id, step_number, step_title FROM steps "
            "WHERE problem_id=? ORDER BY step_number", (pid,)
        ).fetchall()
        all_steps = [
            {'step_id': row['step_id'],
             'step_number': row['step_number'],
             'step_title': row['step_title'] or ''}
            for row in rows
        ]
        # 결과 step의 타이틀
        title_row = conn.execute(
            "SELECT step_title FROM steps WHERE step_id=?", (r['step_id'],)
        ).fetchone()
        step_title = title_row['step_title'] if title_row else ''

        enriched.append({
            **r,
            'step_title':  step_title,
            'all_steps':   all_steps,
            'same_concept': r['concept_id'] == query_concept,
        })
    return enriched


# ── 의견 저장/로드 ────────────────────────────────────────────────────────────
def load_opinions():
    if os.path.exists(OPINIONS_FILE):
        with open(OPINIONS_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_opinion(step_id, text):
    data = load_opinions()
    data[str(step_id)] = {'opinion': text, 'step_id': step_id}
    with open(OPINIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── API ───────────────────────────────────────────────────────────────────────
@app.route('/api/random_steps')
def api_random_steps():
    n = int(request.args.get('n', 30))
    conn = get_conn()
    rows = conn.execute(
        "SELECT step_id, problem_id, step_number, action_concept_id, step_title "
        "FROM steps WHERE step_title IS NOT NULL AND step_title != '' "
        "ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return jsonify([
        {'step_id':    r['step_id'],
         'problem_id': r['problem_id'],
         'step_number':r['step_number'],
         'concept_id': r['action_concept_id'] or '',
         'step_title': r['step_title'] or ''}
        for r in rows
    ])


@app.route('/api/compare')
def api_compare():
    step_id = int(request.args.get('step_id', 0))
    conn    = get_conn()

    # 쿼리 스텝 정보
    qrow = conn.execute(
        "SELECT step_id, problem_id, step_number, action_concept_id, step_title "
        "FROM steps WHERE step_id=?", (step_id,)
    ).fetchone()
    if not qrow:
        conn.close()
        return jsonify({'error': f'step_id {step_id} 없음'}), 404

    q_concept = qrow['action_concept_id'] or ''

    a_raw = cosine_search(A, A_IDX, step_id, TOP_K)
    b_raw = cosine_search(B, B_IDX, step_id, TOP_K)

    a_results = enrich_results(a_raw, conn, q_concept)
    b_results = enrich_results(b_raw, conn, q_concept)

    # 쿼리 문항의 전체 스텝 목록
    q_all_steps = [
        {'step_id': r['step_id'], 'step_number': r['step_number'], 'step_title': r['step_title'] or ''}
        for r in conn.execute(
            "SELECT step_id, step_number, step_title FROM steps "
            "WHERE problem_id=? ORDER BY step_number", (qrow['problem_id'],)
        ).fetchall()
    ]

    # 저장된 의견
    opinions = load_opinions()
    opinion  = opinions.get(str(step_id), {}).get('opinion', '')

    conn.close()
    return jsonify({
        'query': {
            'step_id':    step_id,
            'problem_id': qrow['problem_id'],
            'step_number':qrow['step_number'],
            'concept_id': q_concept,
            'step_title': qrow['step_title'] or '',
            'all_steps':  q_all_steps,
        },
        'a_results': a_results,
        'b_results': b_results,
        'opinion':   opinion,
    })


@app.route('/api/save_opinion', methods=['POST'])
def api_save_opinion():
    data    = request.json
    step_id = data.get('step_id')
    text    = data.get('opinion', '')
    save_opinion(step_id, text)
    return jsonify({'ok': True})


@app.route('/api/opinions')
def api_opinions():
    return jsonify(load_opinions())


@app.route('/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    return send_from_directory(THUMB_DIR, filename)


# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>A/B 비교 대시보드</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0f1318; color: #cdd6f4; font-family: 'Segoe UI', sans-serif; font-size: 13px; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }

/* ── 레이아웃 ── */
#top-bar { background: #1e2530; border-bottom: 1px solid #2a3040; padding: 8px 14px; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
#top-bar h1 { font-size: 15px; color: #89b4fa; font-weight: 600; }
#main { display: flex; flex: 1; overflow: hidden; }

/* ── 왼쪽 스텝 목록 ── */
#step-list-panel { width: 280px; background: #161b22; border-right: 1px solid #2a3040; display: flex; flex-direction: column; flex-shrink: 0; }
#step-list-header { padding: 8px 10px; background: #1e2530; border-bottom: 1px solid #2a3040; display: flex; align-items: center; gap: 8px; }
#step-list-header span { font-size: 12px; color: #a6adc8; flex: 1; }
#step-list { overflow-y: auto; flex: 1; }
.step-item { padding: 8px 10px; border-bottom: 1px solid #1e2530; cursor: pointer; transition: background .15s; }
.step-item:hover { background: #1e2530; }
.step-item.active { background: #1e3a5f; border-left: 3px solid #89b4fa; }
.step-item .pid { font-size: 11px; color: #89b4fa; font-weight: 600; }
.step-item .sno { font-size: 10px; color: #6c7086; margin-left: 4px; }
.step-item .stitle { font-size: 11px; color: #a6adc8; margin-top: 2px; line-height: 1.4; }
.step-item .cpt { font-size: 10px; color: #585b70; margin-top: 2px; }
.has-opinion { border-right: 3px solid #a6e3a1; }

/* ── 중앙 비교 영역 ── */
#compare-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* 쿼리 바 */
#query-bar { background: #1e2530; border-bottom: 1px solid #2a3040; padding: 0; flex-shrink: 0; display: flex; }
#query-thumb-wrap { flex-shrink: 0; padding: 10px 12px; border-right: 1px solid #2a3040; display: flex; align-items: flex-start; }
#query-thumb-wrap img { max-width: 180px; max-height: 220px; border-radius: 4px; border: 1px solid #2a3040; display: block; }
#query-thumb-wrap .no-thumb { width: 180px; height: 100px; background: #161b22; border: 1px dashed #2a3040; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #585b70; font-size: 11px; }
#query-info { flex: 1; padding: 10px 14px; overflow-y: auto; max-height: 240px; }
#query-info .label { font-size: 10px; color: #6c7086; text-transform: uppercase; letter-spacing: .05em; }
#query-info .qpid { font-size: 13px; color: #89b4fa; font-weight: 700; }
#query-info .qcpt { font-size: 11px; color: #6c7086; margin-bottom: 8px; }
#query-steps .qs-row { display: flex; gap: 6px; padding: 3px 6px; border-radius: 4px; margin-bottom: 2px; }
#query-steps .qs-row.qs-matched { background: #1e3a5f; border: 1px solid #89b4fa; }
#query-steps .qs-sno { font-size: 10px; color: #585b70; width: 22px; flex-shrink: 0; margin-top: 1px; }
#query-steps .qs-title { font-size: 12px; line-height: 1.5; }
#query-steps .qs-row.qs-matched .qs-title { color: #cdd6f4; font-weight: 600; }
#query-steps .qs-row:not(.qs-matched) .qs-title { color: #7f849c; }

/* AB 패널 */
#ab-panels { flex: 1; display: flex; overflow: hidden; }
.ab-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; border-right: 1px solid #2a3040; }
.ab-panel:last-child { border-right: none; }
.ab-header { padding: 6px 12px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .08em; flex-shrink: 0; }
#panel-a .ab-header { background: #1a2a3a; color: #89b4fa; border-bottom: 2px solid #89b4fa; }
#panel-b .ab-header { background: #1a2a1a; color: #a6e3a1; border-bottom: 2px solid #a6e3a1; }

/* 랭크 목록 */
.rank-list { overflow-y: auto; flex-shrink: 0; max-height: 160px; border-bottom: 1px solid #2a3040; }
.rank-item { display: flex; align-items: center; gap: 8px; padding: 5px 10px; cursor: pointer; border-bottom: 1px solid #1a1f2a; transition: background .1s; }
.rank-item:hover { background: #1e2530; }
.rank-item.active { background: #252d3a; }
#panel-a .rank-item.active { border-left: 3px solid #89b4fa; }
#panel-b .rank-item.active { border-left: 3px solid #a6e3a1; }
.rank-no { font-size: 11px; color: #585b70; width: 18px; text-align: right; flex-shrink: 0; }
.rank-sim { font-size: 11px; color: #f38ba8; width: 44px; text-align: right; flex-shrink: 0; }
.rank-pid { font-size: 11px; font-weight: 600; width: 130px; flex-shrink: 0; }
#panel-a .rank-pid { color: #89b4fa; }
#panel-b .rank-pid { color: #a6e3a1; }
.rank-cpt-match { font-size: 10px; color: #a6e3a1; width: 14px; }
.rank-stitle { font-size: 11px; color: #a6adc8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 상세 패널 */
.detail-panel { flex: 1; overflow-y: auto; padding: 10px 12px; display: flex; gap: 12px; }
.detail-thumb { flex-shrink: 0; }
.detail-thumb img { max-width: 220px; max-height: 300px; border-radius: 4px; border: 1px solid #2a3040; display: block; }
.detail-thumb .no-thumb { width: 220px; height: 120px; background: #1e2530; border: 1px dashed #2a3040; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #585b70; font-size: 11px; }
.detail-steps { flex: 1; }
.detail-steps .ds-header { font-size: 11px; color: #6c7086; margin-bottom: 6px; }
.step-row { display: flex; gap: 6px; align-items: flex-start; padding: 4px 6px; border-radius: 4px; margin-bottom: 2px; }
.step-row.matched { background: #1e3a1e; border: 1px solid #a6e3a1; }
#panel-a .step-row.matched { background: #1a2a3a; border: 1px solid #89b4fa; }
.step-sno { font-size: 10px; color: #585b70; width: 22px; flex-shrink: 0; margin-top: 1px; }
.step-title-text { font-size: 12px; line-height: 1.5; }
.step-row.matched .step-title-text { color: #cdd6f4; font-weight: 600; }
.step-row:not(.matched) .step-title-text { color: #7f849c; }

/* 의견 영역 */
#opinion-bar { background: #161b22; border-top: 1px solid #2a3040; padding: 8px 14px; display: flex; gap: 10px; align-items: center; flex-shrink: 0; }
#opinion-bar label { font-size: 11px; color: #6c7086; white-space: nowrap; }
#opinion-input { flex: 1; background: #1e2530; border: 1px solid #2a3040; border-radius: 4px; color: #cdd6f4; font-size: 12px; padding: 6px 10px; resize: none; height: 42px; font-family: inherit; }
#opinion-input:focus { outline: none; border-color: #89b4fa; }
#save-btn { background: #1e3a5f; color: #89b4fa; border: 1px solid #89b4fa; border-radius: 4px; padding: 6px 14px; cursor: pointer; font-size: 12px; white-space: nowrap; }
#save-btn:hover { background: #89b4fa; color: #0f1318; }
#save-ok { font-size: 11px; color: #a6e3a1; display: none; }

/* 버튼 */
button.icon-btn { background: #2a3040; border: 1px solid #3a4050; color: #a6adc8; border-radius: 4px; padding: 4px 10px; cursor: pointer; font-size: 12px; }
button.icon-btn:hover { background: #3a4050; }

/* 키 힌트 */
#key-hint { font-size: 10px; color: #585b70; margin-left: auto; }

/* 빈 상태 */
#empty-state { flex: 1; display: flex; align-items: center; justify-content: center; color: #585b70; font-size: 14px; }
</style>
</head>
<body>

<div id="top-bar">
  <h1>🔬 A/B 임베딩 비교 대시보드</h1>
  <span style="font-size:11px;color:#6c7086;">A = 3-tier (step+trigger+concept) &nbsp;|&nbsp; B = 1-tier (step_title 단독)</span>
  <span id="key-hint">↑↓ 순위 이동 &nbsp;|&nbsp; 클릭으로 스텝 선택</span>
</div>

<div id="main">
  <!-- 왼쪽 스텝 목록 -->
  <div id="step-list-panel">
    <div id="step-list-header">
      <span id="list-count">스텝 목록</span>
      <button class="icon-btn" onclick="loadRandomSteps()">🔀 새 목록</button>
    </div>
    <div id="step-list"></div>
  </div>

  <!-- 비교 영역 -->
  <div id="compare-area">
    <div id="query-bar" style="display:none;">
      <div id="query-thumb-wrap">
        <img id="query-thumb" src="" alt="">
      </div>
      <div id="query-info">
        <div class="label">쿼리 문항</div>
        <div class="qpid" id="q-pid"></div>
        <div class="qcpt" id="q-cpt"></div>
        <div id="query-steps"></div>
      </div>
    </div>

    <div id="ab-panels">
      <div class="ab-panel" id="panel-a">
        <div class="ab-header">A — 3-tier 임베딩</div>
        <div class="rank-list" id="rank-a"></div>
        <div class="detail-panel" id="detail-a"></div>
      </div>
      <div class="ab-panel" id="panel-b">
        <div class="ab-header">B — 1-tier 임베딩</div>
        <div class="rank-list" id="rank-b"></div>
        <div class="detail-panel" id="detail-b"></div>
      </div>
    </div>

    <div id="empty-state">← 왼쪽에서 스텝을 선택하세요</div>

    <div id="opinion-bar" style="display:none;">
      <label>종합 의견</label>
      <textarea id="opinion-input" placeholder="A가 나음 / B가 나음 / 비슷 — 이유를 자유롭게 입력..."></textarea>
      <button id="save-btn" onclick="saveOpinion()">저장</button>
      <span id="save-ok">✓ 저장됨</span>
    </div>
  </div>
</div>

<script>
let currentStepId = null;
let currentRank   = 0;   // 0-based
let aResults      = [];
let bResults      = [];
let opinions      = {};

// ── 초기화 ───────────────────────────────────────────────────────────────────
async function init() {
  await loadOpinions();
  await loadRandomSteps();
}

async function loadRandomSteps() {
  const res  = await fetch('/api/random_steps?n=30');
  const list = await res.json();
  const el   = document.getElementById('step-list');
  document.getElementById('list-count').textContent = `${list.length}개 스텝`;
  el.innerHTML = list.map(s => `
    <div class="step-item ${opinions[s.step_id] ? 'has-opinion' : ''}"
         id="si-${s.step_id}" onclick="loadCompare(${s.step_id})">
      <span class="pid">${s.problem_id}</span>
      <span class="sno">Step ${s.step_number}</span>
      <div class="stitle">${s.step_title}</div>
      <div class="cpt">${s.concept_id}</div>
    </div>
  `).join('');
}

async function loadOpinions() {
  const res = await fetch('/api/opinions');
  opinions  = await res.json();
}

// ── 비교 로드 ─────────────────────────────────────────────────────────────────
async function loadCompare(stepId) {
  currentStepId = stepId;
  currentRank   = 0;

  // 목록 활성화
  document.querySelectorAll('.step-item').forEach(el => el.classList.remove('active'));
  const si = document.getElementById(`si-${stepId}`);
  if (si) si.classList.add('active');

  const res  = await fetch(`/api/compare?step_id=${stepId}`);
  const data = await res.json();
  if (data.error) { alert(data.error); return; }

  aResults = data.a_results;
  bResults = data.b_results;

  // 쿼리 바
  document.getElementById('query-bar').style.display = '';

  // 쿼리 문항 썸네일
  const qthumb = document.getElementById('query-thumb');
  qthumb.src = `/thumbnails/${data.query.problem_id}.png`;
  qthumb.onerror = () => {
    qthumb.parentNode.innerHTML = '<div class="no-thumb">썸네일 없음</div>';
  };

  document.getElementById('q-pid').textContent  = `${data.query.problem_id}`;
  document.getElementById('q-cpt').textContent  = `CPT: ${data.query.concept_id}`;

  // 쿼리 문항의 모든 스텝 목록 (선택된 스텝 강조)
  document.getElementById('query-steps').innerHTML = data.query.all_steps.map(s => {
    const matched = s.step_id === data.query.step_id;
    return `<div class="qs-row ${matched ? 'qs-matched' : ''}">
      <span class="qs-sno">S${s.step_number}</span>
      <span class="qs-title">${s.step_title || '(제목 없음)'}</span>
    </div>`;
  }).join('');

  // 빈 상태 숨김
  document.getElementById('empty-state').style.display = 'none';
  document.getElementById('ab-panels').style.display   = '';
  document.getElementById('opinion-bar').style.display = '';

  // 의견 복원
  document.getElementById('opinion-input').value = data.opinion || '';
  document.getElementById('save-ok').style.display = 'none';

  renderRankList('a', aResults);
  renderRankList('b', bResults);
  selectRank(0);
}

// ── 랭크 목록 렌더 ────────────────────────────────────────────────────────────
function renderRankList(side, results) {
  const el = document.getElementById(`rank-${side}`);
  el.innerHTML = results.map((r, i) => `
    <div class="rank-item" id="ri-${side}-${i}" onclick="selectRank(${i})">
      <span class="rank-no">${i+1}</span>
      <span class="rank-sim">${r.sim.toFixed(4)}</span>
      <span class="rank-pid">${r.problem_id} S${r.step_number}</span>
      <span class="rank-cpt-match">${r.same_concept ? '✓' : ''}</span>
      <span class="rank-stitle">${r.step_title}</span>
    </div>
  `).join('');
}

// ── 랭크 선택 & 상세 렌더 ─────────────────────────────────────────────────────
function selectRank(rank) {
  currentRank = rank;

  ['a','b'].forEach(side => {
    document.querySelectorAll(`#rank-${side} .rank-item`).forEach((el,i) => {
      el.classList.toggle('active', i === rank);
    });
    // 스크롤 보이기
    const active = document.querySelector(`#rank-${side} .rank-item.active`);
    if (active) active.scrollIntoView({ block: 'nearest' });
  });

  renderDetail('a', aResults[rank]);
  renderDetail('b', bResults[rank]);
}

function renderDetail(side, result) {
  if (!result) return;
  const el       = document.getElementById(`detail-${side}`);
  const thumbSrc = `/thumbnails/${result.problem_id}.png`;
  const isA      = side === 'a';

  const stepsHtml = result.all_steps.map(s => {
    const matched = s.step_id === result.step_id;
    return `
      <div class="step-row ${matched ? 'matched' : ''}">
        <span class="step-sno">S${s.step_number}</span>
        <span class="step-title-text">${s.step_title || '(제목 없음)'}</span>
      </div>`;
  }).join('');

  el.innerHTML = `
    <div class="detail-thumb">
      <img src="${thumbSrc}" onerror="this.parentNode.innerHTML='<div class=\\'no-thumb\\'>썸네일 없음</div>'" alt="${result.problem_id}">
    </div>
    <div class="detail-steps">
      <div class="ds-header">
        <b>${result.problem_id}</b> &nbsp; Step ${result.step_number}
        &nbsp;<span style="color:#585b70">${result.concept_id}</span>
        &nbsp;<span style="color:${isA?'#89b4fa':'#a6e3a1'};font-weight:600">${result.sim.toFixed(4)}</span>
      </div>
      ${stepsHtml}
    </div>`;
}

// ── 의견 저장 ─────────────────────────────────────────────────────────────────
async function saveOpinion() {
  const text = document.getElementById('opinion-input').value.trim();
  await fetch('/api/save_opinion', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ step_id: currentStepId, opinion: text }),
  });
  opinions[currentStepId] = { opinion: text };
  // 목록 아이템에 표시
  const si = document.getElementById(`si-${currentStepId}`);
  if (si) si.classList.add('has-opinion');
  document.getElementById('save-ok').style.display = '';
  setTimeout(() => document.getElementById('save-ok').style.display = 'none', 2000);
}

// ── 키보드 ────────────────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'TEXTAREA') return;
  if (!currentStepId) return;
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (currentRank > 0) selectRank(currentRank - 1);
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (currentRank < Math.min(aResults.length, bResults.length) - 1)
      selectRank(currentRank + 1);
  }
});

// ── 시작 ─────────────────────────────────────────────────────────────────────
init();
</script>
</body>
</html>"""


@app.route('/')
def index():
    return Response(HTML, mimetype='text/html')


# ── 실행 ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("\n" + "="*50)
    print("  A/B 비교 대시보드 시작")
    print("  접속: http://localhost:5050")
    print("  종료: Ctrl+C")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=5050, debug=False)
