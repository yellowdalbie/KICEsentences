/* THINK LYNX 오프라인 판 — 브라우저 안에서 도는 API 계층.
 *
 * 화면 코드는 그대로 두고 window.fetch 만 가로챈다. '/api/...' 호출이 오면
 * 서버에 가지 않고 여기서 같은 모양의 JSON 을 만들어 돌려준다.
 * 그래서 index.html 과 cart.js 를 거의 손대지 않아도 된다.
 *
 * 필요한 데이터는 data/*.js 가 <script> 로 먼저 실어 둔다.
 * (file:// 에서는 fetch 로 로컬 파일을 읽지 못하므로 이 방식이어야 한다)
 */
(function () {
  'use strict';

  const DB = window.KL_DB, V = window.KL_VOCAB, SIM = window.KL_SIMILAR, MD = window.KL_MDREF;
  if (!DB || !V) { console.error('[KL] 데이터 파일이 로드되지 않았습니다.'); return; }

  /* ── base64 → 타입 배열 ───────────────────────────────── */
  function u16(b64) {
    const bin = atob(b64), n = bin.length, bytes = new Uint8Array(n);
    for (let i = 0; i < n; i++) bytes[i] = bin.charCodeAt(i);
    return new Uint16Array(bytes.buffer);
  }
  function dequant(q, lo, hi) {
    const out = new Float32Array(q.length), s = (hi - lo) / 65535;
    for (let i = 0; i < q.length; i++) out[i] = lo + q[i] * s;
    return out;
  }

  const VOCAB_IDX = u16(V.idx);
  const VOCAB_SCR = dequant(u16(V.scr), V.lo, V.hi);
  const N_STEPS = V.stepIds.length, K = V.K;

  /* ── 색인 ─────────────────────────────────────────────── */
  const stepsByProblem = new Map();
  const stepById = new Map();
  for (const s of DB.steps) {
    if (!stepsByProblem.has(s.p)) stepsByProblem.set(s.p, []);
    stepsByProblem.get(s.p).push(s);
    stepById.set(s.i, s);
  }
  for (const arr of stepsByProblem.values()) arr.sort((a, b) => a.n - b.n);
  const conceptById = new Map(DB.concepts.map(c => [c.id, c]));
  const problemById = new Map(DB.problems.map(p => [p.p, p]));

  /* ── 토크나이저 (search_engine.py 의 _tokenize 와 동일) ── */
  const PARTICLES = window.KL_PARTICLES || [];
  const LATEX_STRIP = /\$[^$]*\$|[\[\]\\${}^_]/g;
  function tokenize(text) {
    if (!text) return [];
    let clean = String(text).replace(LATEX_STRIP, ' ').replace(/\s+/g, ' ').trim();
    const out = [];
    for (let tok of clean.split(' ')) {
      for (const p of PARTICLES) {
        if (tok.endsWith(p) && tok.length > p.length + 1) { tok = tok.slice(0, -p.length); break; }
      }
      if (tok.length >= 2) out.push(tok);
    }
    return out;
  }

  /* ── 개념유사도: 어휘 룩업 (OfflineQueryEngine 이식) ───── */
  function getCosSims(query) {
    const scores = new Float32Array(N_STEPS);
    const tokens = tokenize(query);
    if (!tokens.length) return scores;

    const df = new Map(tokens.map(t => [t, 0]));
    const hitsByTerm = new Map();
    for (let i = 0; i < V.terms.length; i++) {
      const term = V.terms[i];
      let hits = null;
      for (const t of tokens) {
        if (term.indexOf(t) !== -1) { (hits || (hits = [])).push(t); df.set(t, df.get(t) + 1); }
      }
      if (hits) hitsByTerm.set(i, hits);
    }
    if (!hitsByTerm.size) return scores;

    const nVocab = V.terms.length, idf = new Map();
    for (const [t, d] of df) if (d > 0) idf.set(t, Math.log(nVocab / d));

    const weights = new Map();
    let total = 0;
    for (const [i, hits] of hitsByTerm) {
      let w = 0;
      for (const t of hits) w += idf.get(t) || 0;
      if (w > 0) { weights.set(i, w); total += w; }
    }
    if (!weights.size) return scores;

    for (const [vi, w] of weights) {
      const nw = w / total, base = vi * K;
      for (let k = 0; k < K; k++) scores[VOCAB_IDX[base + k]] += nw * VOCAB_SCR[base + k];
    }
    return scores;
  }

  /* ── 응답 행 만들기 (서버 SELECT 결과와 같은 모양) ────── */
  function stepRow(s, extra) {
    const c = conceptById.get(s.c);
    return Object.assign({
      step_id: s.i, problem_id: s.p, step_number: s.n,
      step_title: s.t, action_concept_id: s.c,
      explanation_text: s.x, explanation_html: s.h,
      standard_name: c ? c.n : null, ref_code: c ? c.id : null,
      total_steps: (stepsByProblem.get(s.p) || []).length,
      trigger_text: s.t || ''
    }, extra || {});
  }

  /* ── /api/search ──────────────────────────────────────── */
  function apiSearch(q) {
    if (!q) return { results: [] };
    const isCode = /^\d{1,2}[가-힣ⅠⅡ]/.test(q) ||
      (q.length > 3 && /\d/.test(q[0]) && (q.includes('모') || q.includes('수능')));

    if (isCode) {                      // 문항·개념 코드 → 부분일치
      const needle = q.toLowerCase();
      const probs = new Set();
      for (const s of DB.steps) {
        const c = conceptById.get(s.c);
        const tr = DB.triggers[String(s.i)] || ['', ''];
        const hay = [s.p, s.t, s.c, tr[0], tr[1], c ? c.n : '', c ? c.id : ''].join('\n').toLowerCase();
        if (hay.includes(needle)) probs.add(s.p);
      }
      const out = [];
      for (const pid of [...probs].sort().reverse())
        for (const s of stepsByProblem.get(pid) || []) out.push(stepRow(s, { normalized_text: '' }));
      return { results: out };
    }

    const sims = getCosSims(q);
    const order = Array.from(sims.keys()).sort((a, b) => sims[b] - sims[a]);
    const seen = new Set(), picked = [], meta = {};
    for (const idx of order) {
      const score = sims[idx];
      if (score < 0.15) break;                       // 서버와 동일한 하한
      const pid = V.problemIds[idx];
      if (!seen.has(pid)) {
        seen.add(pid); picked.push(pid);
        meta[pid] = { cos_similarity: Math.round(score * 1e4) / 1e4, match_step_id: V.stepIds[idx] };
      }
      if (picked.length >= 100) break;
    }
    // 서버는 뽑은 문항들을 SQL 로 한 번에 가져온 뒤
    //   results.sort(key=(-반올림유사도, step_number))
    // 로 정렬한다. IN (...) 은 순서를 보장하지 않고 steps(problem_id) 인덱스를 타므로
    // 실제 행 순서는 problem_id 오름차순이며, 파이썬 정렬이 안정적이라 동점은 그 순서를
    // 유지한다. 그래서 여기서도 problem_id 오름차순으로 만든 뒤 안정 정렬한다.
    const out = [];
    for (const pid of [...picked].sort())
      for (const s of stepsByProblem.get(pid) || [])
        out.push(stepRow(s, {
          cos_similarity: meta[pid].cos_similarity,
          match_step_id: meta[pid].match_step_id,
          hybrid_score: meta[pid].cos_similarity,
          same_concept: false
        }));
    out.sort((a, b) => (b.cos_similarity - a.cos_similarity) || (a.step_number - b.step_number));
    return { results: out };
  }

  /* ── /api/search_probid ───────────────────────────────── */
  function normProbId(s) {
    s = String(s).replace(/[\s,번]/g, '').replace(/학년도/g, '').replace(/년/g, '');
    s = s.replace(/9월/g, '9모').replace(/6월/g, '6모');
    s = s.replace(/확률과통계/g, '확').replace(/확통/g, '확');
    s = s.replace(/미적분/g, '미').replace(/미적/g, '미');
    s = s.replace(/기하/g, '기').replace(/공통/g, '공');
    return s;
  }
  function isSubsequence(sub, str) {          // 순서를 지키는 부분열 매칭
    let i = 0;
    for (const ch of str) if (ch === sub[i]) { if (++i === sub.length) return true; }
    return sub.length === 0;
  }
  function apiSearchProbid(q) {
    if (!q) return { results: [] };
    const nq = normProbId(q);
    const pureNum = /^\d{1,2}$/.test(nq);
    const hit = pid => {
      const np = normProbId(pid);
      if (pureNum) {                          // '30' 이 '2023.수능_10' 에 걸리는 것 방지
        const last = np.split('_').pop();
        const m = last.match(/(\d+)$/);
        return !!(m && m[1] === nq);
      }
      return isSubsequence(nq, np);
    };
    const out = [], matched = new Set();
    const pids = [...stepsByProblem.keys()].sort().reverse();
    for (const pid of pids) {
      if (!hit(pid)) continue;
      matched.add(pid);
      for (const s of stepsByProblem.get(pid)) out.push(stepRow(s, { normalized_text: '' }));
    }
    if (MD) {                                 // DB 에 없는 범위 밖 문항도 안내와 함께 노출
      for (const pid in MD) {
        if (matched.has(pid) || !hit(pid)) continue;
        matched.add(pid);
        out.push({
          step_id: null, problem_id: pid, step_number: '', explanation_text: '',
          explanation_html: '', total_steps: 1, step_title: '', action_concept_id: '',
          standard_name: '', ref_code: '', normalized_text: '',
          trigger_text: '2028 수능 수학의 출제범위가 아닌 문항에 대해서는 해설과 정답을 제공하지 않습니다.'
        });
      }
    }
    return { results: out };
  }

  /* ── /api/concepts_tree ───────────────────────────────── */
  function apiConceptsTree() {
    const tree = {};
    for (const c of DB.concepts) {
      if (!c.id) continue;
      const full = c.u || '';
      let rawSubj, unitName;
      if (full.includes(' - ')) {
        const parts = full.split(' - ');
        rawSubj = parts[0].trim();
        unitName = parts[parts.length - 1].trim();   // 마지막 조각만 쓴다
      } else { rawSubj = '기타'; unitName = full; }

      let subject;                                    // 서버와 같은 표시명 매핑
      if (rawSubj.startsWith('중학교 수학')) subject = '중학교 수학';
      else if (rawSubj.startsWith('공통수학')) subject = '공통수학';
      else if (rawSubj === '미적분\u2160') subject = '미적분I';
      else subject = rawSubj;

      const m = c.id.match(/(\d{2})-\d{2}/);         // 코드에서 단원 번호 추출
      const unit = `${m ? m[1] : '00'}. ${unitName}`;

      if (!tree[subject]) tree[subject] = {};
      if (!tree[subject][unit]) tree[subject][unit] = [];
      tree[subject][unit].push({ id: c.id, ref_code: c.id, standard_name: c.n });
    }
    return tree;
  }

  /* ── /api/steps_by_concept ────────────────────────────── */
  function apiStepsByConcept(cid) {
    const out = [];
    for (const s of DB.steps) if (s.c === cid) out.push(stepRow(s));
    out.sort((a, b) => a.problem_id < b.problem_id ? 1 : a.problem_id > b.problem_id ? -1 : a.step_number - b.step_number);
    return { results: out };
  }

  /* ── /api/similar_steps/<id> ──────────────────────────── */
  let SIM_IDX = null, SIM_SCR = null, SIM_POS = null;
  function apiSimilarSteps(stepId, topN) {
    if (!SIM) return { error: '유사 스텝 데이터 없음' };
    if (!SIM_IDX) {
      SIM_IDX = u16(SIM.idx); SIM_SCR = dequant(u16(SIM.scr), SIM.lo, SIM.hi);
      SIM_POS = new Map(SIM.stepIds.map((s, i) => [s, i]));
    }
    const row = SIM_POS.get(stepId);
    if (row === undefined) return { error: `step_id ${stepId} 없음` };
    const qs = stepById.get(stepId);
    const qc = conceptById.get(qs ? qs.c : '');
    const n = Math.min(topN || 20, SIM.N), base = row * SIM.N, results = [];
    for (let k = 0; k < n; k++) {
      const sid = SIM.stepIds[SIM_IDX[base + k]], s = stepById.get(sid);
      if (!s) continue;
      const c = conceptById.get(s.c);
      const score = Math.round(SIM_SCR[base + k] * 1e4) / 1e4;
      results.push({
        step_id: s.i, problem_id: s.p, step_number: s.n, step_title: s.t,
        action_concept_id: s.c, standard_name: c ? c.n : null, ref_code: c ? c.id : null,
        hybrid_score: score, cos_similarity: score, bm25_score: 0, cpt_score: 0, vec_score: score,
        same_concept: !!(qs && qs.c && s.c === qs.c)
      });
    }
    return {
      query: qs ? {
        step_id: qs.i, problem_id: qs.p, step_number: qs.n,
        step_title: qs.t, action_concept_id: qs.c,
        standard_name: qc ? qc.n : null
      } : {},
      results: results
    };
  }

  /* ── /api/steps_by_problems, problem_steps(_bulk), answers ── */
  function apiStepsByProblems(idsCsv) {
    const ids = (idsCsv || '').split(',').map(s => s.trim()).filter(Boolean);
    const out = [];
    for (const pid of ids) for (const s of stepsByProblem.get(pid) || []) out.push(stepRow(s));
    return { results: out };
  }
  function apiProblemSteps(pid) {
    return { problem_id: pid, steps: (stepsByProblem.get(pid) || []).map(s => stepRow(s)) };
  }
  function apiProblemStepsBulk(ids) {
    const steps = {};
    for (const pid of ids || []) {
      steps[pid] = (stepsByProblem.get(pid) || [])
        .map(s => ({ step_number: s.n, step_title: s.t, explanation_html: s.h }));
    }
    return { steps: steps };
  }
  function apiProblemAnswers(ids) {
    const answers = {};
    for (const pid of ids || []) {
      const p = problemById.get(pid);
      if (p && p.a) answers[pid] = p.a;
    }
    return { answers: answers };
  }

  /* ── /api/sets/auto_title ─────────────────────────────── */
  function apiAutoTitle(idsCsv) {
    const ids = (idsCsv || '').split(',').map(s => s.trim()).filter(Boolean);
    if (!ids.length) return { title: '문항 세트' };
    const counts = new Map();
    for (const pid of ids) {
      for (const s of stepsByProblem.get(pid) || []) {
        if (!s.c) continue;
        const c = conceptById.get(s.c);
        const subject = c && c.u ? c.u.split(' - ')[0] : '기타';
        counts.set(subject, (counts.get(subject) || 0) + 1);
      }
    }
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
    const label = top ? top[0] : '혼합';
    return { title: `${label} ${ids.length}문항` };
  }

  /* ── 기출표현 검색 (compile_query 이식) ────────────────── */
  function splitTokens(s) {                      // shlex.split 의 축약판 (따옴표 지원)
    const out = []; let cur = '', q = null;
    for (const ch of s) {
      if (q) { if (ch === q) q = null; else cur += ch; }
      else if (ch === '"' || ch === "'") q = ch;
      else if (/\s/.test(ch)) { if (cur) { out.push(cur); cur = ''; } }
      else cur += ch;
    }
    if (cur) out.push(cur);
    return out;
  }
  function compileQuery(query) {
    let pathFilter = null;
    const m = query.match(/path:(\S+)/);
    if (m) { pathFilter = m[1]; query = query.replace(m[0], ''); }
    const rawGroups = query.replace(/ \| /g, ' OR ').split(' OR ');
    const groups = [];
    for (const g of rawGroups) {
      const terms = [];
      for (let tok of splitTokens(g)) {
        const isNot = tok.startsWith('-');
        if (isNot) tok = tok.slice(1);
        let re = null;
        if (tok.startsWith('/') && tok.endsWith('/') && tok.length > 2) {
          try { re = new RegExp(tok.slice(1, -1), 'i'); } catch (e) { re = null; }
        }
        if (tok) terms.push({ term: tok, not: isNot, re: re });
      }
      if (terms.length) groups.push(terms);
    }
    return { pathFilter: pathFilter, groups: groups, hasTokens: groups.length > 0 };
  }
  function evalQuery(cq, content, relPath) {
    if (cq.pathFilter && !relPath.includes(cq.pathFilter)) return null;
    if (!cq.hasTokens) return cq.pathFilter ? [] : null;
    for (const group of cq.groups) {
      const hl = []; let ok = true;
      for (const t of group) {
        const found = t.re ? t.re.test(content) : content.includes(t.term);
        if (t.not) { if (found) { ok = false; break; } }
        else if (found) hl.push(t.term);
        else { ok = false; break; }
      }
      if (ok) return hl;
    }
    return null;
  }
  function snippet(content, highlights) {
    let pos = -1;
    for (const h of highlights) { const i = content.indexOf(h); if (i !== -1) { pos = i; break; } }
    if (pos === -1) return content.slice(0, 200).replace(/\s+/g, ' ').trim();
    const s = Math.max(0, pos - 80), e = Math.min(content.length, pos + 160);
    return (s > 0 ? '…' : '') + content.slice(s, e).replace(/\s+/g, ' ').trim() + (e < content.length ? '…' : '');
  }
  function apiSearchExpression(q) {
    if (!q || !MD) return { count: 0, results: [] };
    const cq = compileQuery(q), out = [];
    for (const pid in MD) {
      const [rel, content] = MD[pid];
      const hl = evalQuery(cq, content, rel);
      if (hl !== null) out.push({ problem_id: pid, file_path: rel, title: pid, snippet: snippet(content, hl), highlights: hl });
    }
    return { count: out.length, results: out };   // 서버와 같은 순회 순서 유지
  }

  /* ── 세트 저장 (서버 DB → localStorage) ────────────────── */
  const LS = 'kl_sets_v1', LS_TEMP = 'kl_temp_v1';
  const readSets = () => { try { return JSON.parse(localStorage.getItem(LS) || '[]'); } catch (e) { return []; } };
  const writeSets = v => { try { localStorage.setItem(LS, JSON.stringify(v)); } catch (e) { console.warn('[KL] 저장 실패', e); } };

  /* ── 라우팅 ───────────────────────────────────────────── */
  function route(path, method, body) {
    const [p, qs] = path.split('?');
    const g = new URLSearchParams(qs || '');
    const route_ = p.replace(/^https?:\/\/[^/]+/, '');

    if (route_ === '/api/search') return apiSearch((g.get('q') || '').trim());
    if (route_ === '/api/search_probid') return apiSearchProbid((g.get('q') || '').trim());
    if (route_ === '/api/search_expression') return apiSearchExpression((g.get('q') || '').trim());
    if (route_ === '/api/concepts_tree') return apiConceptsTree();
    if (route_ === '/api/steps_by_concept') return apiStepsByConcept(g.get('concept_id') || '');
    if (route_ === '/api/steps_by_problems') return apiStepsByProblems(g.get('ids') || '');
    if (route_ === '/api/problem_steps') return apiProblemSteps(g.get('pid') || '');
    if (route_ === '/api/problem_steps_bulk') return apiProblemStepsBulk((body || {}).problem_ids);
    if (route_ === '/api/problem_answers') return apiProblemAnswers((body || {}).problem_ids);
    if (route_ === '/api/sets/auto_title') return apiAutoTitle(g.get('ids') || '');
    const sim = route_.match(/^\/api\/similar_steps\/(\d+)$/);
    if (sim) return apiSimilarSteps(parseInt(sim[1], 10), parseInt(g.get('top_n') || '20', 10));

    /* 세트 저장 — 브라우저에 보관 */
    if (route_ === '/api/sets/temp' && method === 'POST') {
      try { localStorage.setItem(LS_TEMP, JSON.stringify(body || {})); } catch (e) {}
      return { status: 'ok' };
    }
    if (route_ === '/api/sets/restore') {
      if (method === 'DELETE') { localStorage.removeItem(LS_TEMP); return { status: 'ok' }; }
      try { const t = localStorage.getItem(LS_TEMP); return t ? JSON.parse(t) : {}; } catch (e) { return {}; }
    }
    if (route_ === '/api/sets/final' && method === 'POST') {
      const sets = readSets();
      const item = Object.assign({ id: Date.now(), created_at: new Date().toISOString(), is_favorite: 0 }, body || {});
      sets.unshift(item); writeSets(sets);
      return { status: 'ok', set_id: item.id };
    }
    if (route_ === '/api/sets/my') return { sets: readSets() };
    const one = route_.match(/^\/api\/sets\/(\d+)(\/favorite)?$/);
    if (one) {
      const id = parseInt(one[1], 10); const sets = readSets();
      const i = sets.findIndex(s => s.id === id);
      if (one[2]) { if (i >= 0) { sets[i].is_favorite = sets[i].is_favorite ? 0 : 1; writeSets(sets); } return { status: 'ok' }; }
      if (method === 'DELETE') { if (i >= 0) { sets.splice(i, 1); writeSets(sets); } return { status: 'ok' }; }
      return i >= 0 ? sets[i] : { error: 'not found' };
    }

    /* 오프라인에서 없는 기능 — 화면이 조용히 넘어가도록 빈 응답 */
    if (route_.startsWith('/api/auth/')) return { isLoggedIn: false, isPaid: false, isVerified: false, offline: true };
    if (route_.startsWith('/api/board/')) return { posts: [], notices: [], total: 0, page: 1, per_page: 30 };
    if (route_ === '/api/errors' || route_ === '/api/log_event' || route_ === '/api/double_cart') return { status: 'ok' };
    if (route_ === '/api/users/display_name') return { status: 'ok' };

    return { error: 'offline: 지원하지 않는 요청', path: route_ };
  }

  /* ── fetch 가로채기 ───────────────────────────────────── */
  const origFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (url.indexOf('/api/') === -1) {
      return origFetch ? origFetch(input, init) : Promise.reject(new Error('offline'));
    }
    const method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
    let body = null;
    if (init && init.body) { try { body = JSON.parse(init.body); } catch (e) { body = null; } }
    let data;
    try { data = route(url, method, body); }
    catch (e) { console.error('[KL] 처리 실패', url, e); data = { error: String(e) }; }
    return Promise.resolve(new Response(JSON.stringify(data), {
      status: 200, headers: { 'Content-Type': 'application/json' }
    }));
  };

  window.KL = { route: route, tokenize: tokenize, getCosSims: getCosSims, DB: DB };
  console.log(`[KL] 오프라인 모드 준비 완료 — 문항 ${DB.problems.length}개 / 스텝 ${DB.steps.length}개`);
})();
