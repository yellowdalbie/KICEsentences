/* ══════════════════════════════════════════════════════════
   board.js  —  게시판 프론트엔드 로직
══════════════════════════════════════════════════════════ */

// ── 전역 상태 ──────────────────────────────────────────────
let _boardFilter   = 'all';
let _boardPage     = 1;
let _boardSelectMode = false;
let _boardSelected  = new Set();
let _boardCurrentPost = null;   // 현재 열려 있는 게시글 데이터
let _bwType        = null;      // 글쓰기 모달 타입 ('question'|'error')
let _bwSelectedProbId = null;   // 글쓰기 선택 문항
let _publishCallback = null;    // PDF 인쇄 콜백

// 세션 상태 (index.html의 전역 변수와 동기화)
function _getUser() {
  return window.__boardUser || { loggedIn: false, verified: false, isAdmin: false };
}

// index.html 로그인 상태 변화 시 호출되도록 외부에서 주입
window.boardSetUser = function(info) {
  window.__boardUser = info;
  _renderBoardButtons();
};

// ── 유틸 ──────────────────────────────────────────────────
const TYPE_LABEL = { notice:'공지', edit:'편집', question:'질문', error:'오류' };
const TYPE_CLASS = { notice:'board-type-notice', edit:'board-type-edit', question:'board-type-question', error:'board-type-error' };

function _typeBadge(type) {
  return `<span class="board-type-badge ${TYPE_CLASS[type]||''}">${TYPE_LABEL[type]||type}</span>`;
}

function _shortDate(str) {
  if (!str) return '';
  return str.slice(0, 10);
}

function _escHtml(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── 게시판 바로가기 스크롤 ─────────────────────────────────
window.scrollToBoard = function() {
  // overview view 활성화
  document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
  const ov = document.getElementById('view-overview');
  if (ov) ov.classList.add('active');
  // 검색 pill도 초기화
  document.querySelectorAll('.search-pill').forEach(p => p.classList.remove('active'));
  const kw = document.querySelector('.search-pill[data-tab="tab-keyword"]');
  if (kw) kw.classList.add('active');
  setTimeout(() => {
    const panel = document.getElementById('board-panel');
    if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 50);
};

// ── 필터 ──────────────────────────────────────────────────
window.setBoardFilter = function(btn, filter) {
  document.querySelectorAll('.board-filter-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  _boardFilter = filter;
  _boardPage   = 1;
  _boardSelected.clear();
  if (_boardSelectMode) toggleBoardSelectMode();
  loadBoardList();
};

// ── 목록 불러오기 ──────────────────────────────────────────
async function loadBoardList() {
  const tbody = document.getElementById('board-tbody');
  tbody.innerHTML = `<tr><td colspan="7" style="padding:2rem;text-align:center;color:var(--text-muted);">불러오는 중...</td></tr>`;

  try {
    const res  = await fetch(`/api/board/posts?type=${_boardFilter}&page=${_boardPage}`);
    const data = await res.json();
    _renderBoardTable(data);
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="7" style="padding:1rem;text-align:center;color:#f87171;">불러오기 실패</td></tr>`;
  }
}

function _renderBoardTable(data) {
  const tbody = document.getElementById('board-tbody');
  const pagination = document.getElementById('board-pagination');
  tbody.innerHTML = '';

  const user = _getUser();
  const showCheck = _boardSelectMode && user.isAdmin;
  document.getElementById('board-th-check').style.display = showCheck ? 'table-cell' : 'none';

  // 공지 행
  const notices = data.notices || [];
  notices.forEach(p => {
    tbody.appendChild(_makeRow(p, true, showCheck));
  });

  // 좋아요 모드 특수 처리
  if (data.mode === 'liked') {
    if (data.liked && data.liked.length) {
      const sep = document.createElement('tr');
      sep.innerHTML = `<td colspan="7" style="padding:0.3rem 0.5rem;font-size:0.72rem;color:var(--text-muted);background:rgba(6,182,212,0.04);">─ 내가 좋아요 한 글</td>`;
      tbody.appendChild(sep);
      data.liked.forEach(p => tbody.appendChild(_makeRow(p, false, showCheck)));
    }
    if (data.others && data.others.length) {
      const sep2 = document.createElement('tr');
      sep2.innerHTML = `<td colspan="7" style="padding:0.3rem 0.5rem;font-size:0.72rem;color:var(--text-muted);background:rgba(255,255,255,0.02);">─ 좋아요 많은 순</td>`;
      tbody.appendChild(sep2);
      data.others.forEach(p => tbody.appendChild(_makeRow(p, false, showCheck)));
    }
    pagination.innerHTML = '';
    return;
  }

  const posts = data.posts || [];
  if (!notices.length && !posts.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="padding:2rem;text-align:center;color:var(--text-muted);">게시글이 없습니다.</td></tr>`;
  }
  posts.forEach(p => tbody.appendChild(_makeRow(p, false, showCheck)));

  // 페이지네이션
  pagination.innerHTML = '';
  if (data.total > data.per_page) {
    const totalPages = Math.ceil(data.total / data.per_page);
    for (let i = 1; i <= totalPages; i++) {
      const btn = document.createElement('button');
      btn.className = 'board-page-btn' + (i === _boardPage ? ' active' : '');
      btn.textContent = i;
      btn.onclick = () => { _boardPage = i; loadBoardList(); };
      pagination.appendChild(btn);
    }
  }
}

function _makeRow(post, isNotice, showCheck) {
  const tr = document.createElement('tr');
  if (isNotice) tr.className = 'board-notice-row';
  tr.dataset.postId = post.id;

  const checkCell = showCheck
    ? `<td style="text-align:center;"><input type="checkbox" onchange="togglePostSelect(${post.id},this)" ${_boardSelected.has(post.id)?'checked':''}></td>`
    : `<td style="display:none;"></td>`;

  const pinIcon = post.pinned ? '📌 ' : '';
  tr.innerHTML = `
    ${checkCell}
    <td style="text-align:center;color:var(--text-muted);font-size:0.78rem;">${post.id}</td>
    <td style="text-align:center;">${_typeBadge(post.type)}</td>
    <td style="color:var(--text-color);">${pinIcon}${_escHtml(post.title)}</td>
    <td style="text-align:center;color:var(--text-muted);font-size:0.8rem;">${_escHtml(post.author_name)}</td>
    <td style="text-align:center;color:var(--text-muted);font-size:0.78rem;white-space:nowrap;">${_shortDate(post.created_at)}</td>
    <td style="text-align:center;color:var(--text-muted);font-size:0.78rem;">${post.like_count||0}</td>
  `;

  tr.addEventListener('click', (e) => {
    if (e.target.type === 'checkbox') return;
    if (_boardSelectMode) {
      const cb = tr.querySelector('input[type=checkbox]');
      if (cb) { cb.checked = !cb.checked; togglePostSelect(post.id, cb); }
      return;
    }
    openBoardDetail(post.id, post.type);
  });
  return tr;
}

// ── 선택 모드 (관리자) ────────────────────────────────────
window.toggleBoardSelectMode = function() {
  _boardSelectMode = !_boardSelectMode;
  _boardSelected.clear();
  const selectBtn = document.getElementById('board-select-btn');
  const deleteBtn = document.getElementById('board-delete-btn');
  selectBtn.textContent = _boardSelectMode ? '선택 취소' : '선택';
  if (deleteBtn) deleteBtn.style.display = _boardSelectMode ? 'inline-block' : 'none';
  document.getElementById('board-th-check').style.display = _boardSelectMode ? 'table-cell' : 'none';
  loadBoardList();
};

window.togglePostSelect = function(id, cb) {
  if (cb.checked) _boardSelected.add(id);
  else            _boardSelected.delete(id);
};

window.bulkDeletePosts = async function() {
  if (!_boardSelected.size) return;
  if (!confirm(`선택한 ${_boardSelected.size}개 게시글을 삭제할까요?`)) return;
  await fetch('/api/board/posts/bulk_delete', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ ids: [..._boardSelected] })
  });
  _boardSelected.clear();
  if (_boardSelectMode) toggleBoardSelectMode();
  loadBoardList();
};

// ── 게시글 상세 ──────────────────────────────────────────
window.openBoardDetail = async function(postId, postType) {
  const user = _getUser();

  // 공지 외: 미로그인/미인증 차단
  if (postType !== 'notice') {
    if (!user.loggedIn) {
      showBoardAuthModal('login');
      return;
    }
    if (!user.verified) {
      showBoardAuthModal('verify');
      return;
    }
  }

  const overlay = document.getElementById('board-detail-overlay');
  overlay.style.display = 'block';
  overlay.scrollTop = 0;

  // 로딩 상태
  document.getElementById('bd-title').textContent = '불러오는 중...';
  document.getElementById('bd-content').textContent = '';

  try {
    const res  = await fetch(`/api/board/posts/${postId}`);
    if (res.status === 401) { overlay.style.display = 'none'; showBoardAuthModal('login'); return; }
    if (res.status === 403) { overlay.style.display = 'none'; showBoardAuthModal('verify'); return; }
    const post = await res.json();
    _boardCurrentPost = post;
    _fillDetailView(post, user);
  } catch(e) {
    document.getElementById('bd-title').textContent = '오류가 발생했습니다.';
  }
};

function _fillDetailView(post, user) {
  // 뱃지
  const badge = document.getElementById('bd-type-badge');
  badge.className = `board-type-badge ${TYPE_CLASS[post.type]||''}`;
  badge.textContent = TYPE_LABEL[post.type] || post.type;

  document.getElementById('bd-title').textContent   = post.title;
  document.getElementById('bd-author').textContent  = '작성자: ' + post.author_name;
  document.getElementById('bd-date').textContent    = post.created_at ? post.created_at.slice(0,16) : '';
  document.getElementById('bd-content').textContent = post.content || '';

  // 좋아요
  const likeBtn = document.getElementById('bd-like-btn');
  if (post.type !== 'notice') {
    likeBtn.style.display = 'flex';
    _updateDetailLike(post.user_liked, post.like_count);
  } else {
    likeBtn.style.display = 'none';
  }

  // 편집자 설명 수정 버튼 (본인 편집물만)
  const editDescBtn = document.getElementById('bd-edit-desc-btn');
  editDescBtn.style.display = (post.type === 'edit' && post.is_own) ? 'inline-block' : 'none';

  // 편집물 문항 목록
  const probSection = document.getElementById('bd-problems-section');
  const refSection  = document.getElementById('bd-ref-problem-section');
  probSection.style.display = 'none';
  refSection.style.display  = 'none';

  if (post.type === 'edit' && post.problem_ids && post.problem_ids.length) {
    probSection.style.display = 'block';
    const list = document.getElementById('bd-problems-list');
    list.innerHTML = post.problem_ids.map(pid => `
      <div style="display:flex;align-items:center;gap:0.8rem;padding:0.5rem 0.8rem;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:8px;">
        <span style="font-size:0.85rem;font-weight:600;min-width:130px;">${_escHtml(pid)}</span>
        <img src="/static/thumbnails/${_escHtml(pid)}.png" alt="${_escHtml(pid)}" style="max-height:60px;border-radius:5px;"
          onerror="this.style.display='none'">
      </div>
    `).join('');
  } else if (post.type !== 'edit' && post.problem_ids && post.problem_ids.length) {
    refSection.style.display = 'block';
    const pid = post.problem_ids[0];
    document.getElementById('bd-ref-problem-id').textContent = pid;
    const thumb = document.getElementById('bd-ref-thumbnail');
    thumb.src = `/static/thumbnails/${pid}.png`;
    thumb.alt = pid;
    thumb.style.display = 'block';
    thumb.onerror = () => { thumb.style.display = 'none'; };
  }

  // 댓글
  const commentSection = document.getElementById('bd-comments-section');
  const commentForm    = document.getElementById('bd-comment-form');
  const loginNotice    = document.getElementById('bd-comment-login-notice');

  if (post.type === 'notice') {
    commentSection.style.display = 'none';
  } else {
    commentSection.style.display = 'block';
    _renderComments(post.comments || []);
    if (user.loggedIn && user.verified) {
      commentForm.style.display  = 'block';
      loginNotice.style.display  = 'none';
    } else {
      commentForm.style.display  = 'none';
      loginNotice.style.display  = 'block';
    }
  }
}

function _updateDetailLike(liked, count) {
  document.getElementById('bd-like-heart').textContent = liked ? '♥' : '♡';
  document.getElementById('bd-like-count').textContent = count;
  const btn = document.getElementById('bd-like-btn');
  btn.style.color        = liked ? '#f87171' : 'var(--text-muted)';
  btn.style.borderColor  = liked ? 'rgba(239,68,68,0.4)' : 'rgba(255,255,255,0.12)';
}

window.toggleDetailLike = async function() {
  if (!_boardCurrentPost) return;
  const user = _getUser();
  if (!user.loggedIn || !user.verified) { showBoardAuthModal(user.loggedIn ? 'verify' : 'login'); return; }
  const res  = await fetch(`/api/board/posts/${_boardCurrentPost.id}/like`, { method: 'POST' });
  const data = await res.json();
  _boardCurrentPost.user_liked = data.liked;
  _boardCurrentPost.like_count = data.count;
  _updateDetailLike(data.liked, data.count);
  loadBoardList();
};

window.closeBoardDetail = function() {
  document.getElementById('board-detail-overlay').style.display = 'none';
  _boardCurrentPost = null;
  loadBoardList();
};

// ── 댓글 렌더링 ──────────────────────────────────────────
function _renderComments(comments) {
  const list = document.getElementById('bd-comments-list');
  const user = _getUser();
  const topLevel = comments.filter(c => !c.parent_id);
  const children = {};
  comments.filter(c => c.parent_id).forEach(c => {
    (children[c.parent_id] = children[c.parent_id]||[]).push(c);
  });

  list.innerHTML = '';
  if (!topLevel.length) {
    list.innerHTML = '<div style="font-size:0.82rem;color:var(--text-muted);text-align:center;padding:0.5rem;">아직 댓글이 없습니다.</div>';
    return;
  }
  topLevel.forEach(c => {
    list.appendChild(_makeCommentEl(c, false, user));
    (children[c.id]||[]).forEach(r => list.appendChild(_makeCommentEl(r, true, user)));
    // 답글 입력폼 placeholder
    const replyArea = document.createElement('div');
    replyArea.id = `reply-area-${c.id}`;
    replyArea.style.display = 'none';
    replyArea.style.marginLeft = '1.5rem';
    replyArea.style.marginTop = '0.4rem';
    replyArea.innerHTML = `
      <textarea id="reply-input-${c.id}" rows="2" placeholder="답글을 입력하세요..."
        style="width:100%;box-sizing:border-box;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:7px;padding:0.5rem;color:var(--text-color);font-size:0.82rem;resize:none;font-family:inherit;"></textarea>
      <div style="display:flex;justify-content:flex-end;gap:0.4rem;margin-top:0.3rem;">
        <label style="display:flex;align-items:center;gap:0.3rem;font-size:0.75rem;color:var(--text-muted);cursor:pointer;">
          <input type="checkbox" id="reply-anon-${c.id}"> 익명
        </label>
        <button onclick="submitComment(${c.id})" style="background:var(--accent-cyan);border:none;color:#030712;padding:0.3rem 0.8rem;border-radius:6px;cursor:pointer;font-size:0.78rem;font-weight:700;">등록</button>
        <button onclick="document.getElementById('reply-area-${c.id}').style.display='none'" style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:var(--text-muted);padding:0.3rem 0.7rem;border-radius:6px;cursor:pointer;font-size:0.78rem;">취소</button>
      </div>
    `;
    list.appendChild(replyArea);
  });
}

function _makeCommentEl(c, isReply, user) {
  const div = document.createElement('div');
  div.className = isReply ? 'bd-reply' : 'bd-comment';
  const canDel = c.is_own || (user && user.isAdmin);
  div.innerHTML = `
    <div class="bd-comment-meta">
      <span style="font-weight:600;color:var(--text-color);">${_escHtml(c.author_name)}</span>
      <span>${c.created_at ? c.created_at.slice(0,16) : ''}</span>
      ${!isReply && user.loggedIn && user.verified ? `<button class="bd-reply-btn" onclick="toggleReplyArea(${c.id})">답글</button>` : ''}
      ${canDel ? `<button class="bd-del-btn" onclick="deleteComment(${c.id})">삭제</button>` : ''}
    </div>
    <div class="bd-comment-content">${_escHtml(c.content)}</div>
  `;
  return div;
}

window.toggleReplyArea = function(commentId) {
  const area = document.getElementById(`reply-area-${commentId}`);
  if (area) area.style.display = area.style.display === 'none' ? 'block' : 'none';
};

window.submitComment = async function(parentId) {
  let content, isAnon;
  if (parentId) {
    content = (document.getElementById(`reply-input-${parentId}`)?.value||'').trim();
    isAnon  = document.getElementById(`reply-anon-${parentId}`)?.checked;
  } else {
    content = (document.getElementById('bd-comment-input')?.value||'').trim();
    isAnon  = document.getElementById('bd-comment-anon')?.checked;
  }
  if (!content || !_boardCurrentPost) return;

  const res = await fetch(`/api/board/posts/${_boardCurrentPost.id}/comments`, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ content, parent_id: parentId||null, is_anonymous: isAnon })
  });
  if (!res.ok) return;

  if (!parentId) document.getElementById('bd-comment-input').value = '';
  else if (document.getElementById(`reply-input-${parentId}`)) {
    document.getElementById(`reply-input-${parentId}`).value = '';
    document.getElementById(`reply-area-${parentId}`).style.display = 'none';
  }

  // 댓글 새로고침
  const detail = await fetch(`/api/board/posts/${_boardCurrentPost.id}`);
  const data   = await detail.json();
  _renderComments(data.comments || []);
};

window.deleteComment = async function(commentId) {
  if (!confirm('댓글을 삭제할까요?')) return;
  await fetch(`/api/board/comments/${commentId}`, { method: 'DELETE' });
  const detail = await fetch(`/api/board/posts/${_boardCurrentPost.id}`);
  const data   = await detail.json();
  _renderComments(data.comments || []);
};

// ── 편집자 설명 수정 ──────────────────────────────────────
window.openEditDesc = function() {
  document.getElementById('edit-desc-textarea').value = _boardCurrentPost?.content || '';
  document.getElementById('board-edit-desc-modal').style.display = 'flex';
};

window.submitEditDesc = async function() {
  const content = document.getElementById('edit-desc-textarea').value.trim();
  if (!_boardCurrentPost) return;
  await fetch(`/api/board/posts/${_boardCurrentPost.id}`, {
    method: 'PATCH',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ content })
  });
  document.getElementById('board-edit-desc-modal').style.display = 'none';
  document.getElementById('bd-content').textContent = content;
  _boardCurrentPost.content = content;
};

// ── 게시판에서 PDF 인쇄 ───────────────────────────────────
window.printFromBoard = function() {
  if (!_boardCurrentPost || !_boardCurrentPost.problem_ids) return;
  // cart.js의 openPrintPreviewFromIds 사용 (없으면 fallback)
  if (typeof openPrintPreviewFromIds === 'function') {
    openPrintPreviewFromIds(_boardCurrentPost.problem_ids, _boardCurrentPost.title);
  }
};

// ── 권한 안내 모달 ────────────────────────────────────────
window.showBoardAuthModal = function(type) {
  const modal = document.getElementById('board-auth-modal');
  const title = document.getElementById('bam-title');
  const desc  = document.getElementById('bam-desc');
  const btns  = document.getElementById('bam-btns');

  const btnStyle = (bg, color) =>
    `style="width:100%;padding:0.6rem;border-radius:8px;font-size:0.88rem;font-weight:600;cursor:pointer;background:${bg};border:none;color:${color};"`;

  if (type === 'login') {
    title.textContent = '회원 전용 콘텐츠';
    desc.textContent  = '이 게시글은 회원만 열람할 수 있습니다. 회원가입 후 이메일 인증을 완료하면 모든 게시글을 읽을 수 있습니다.';
    btns.innerHTML = `
      <button ${btnStyle('var(--accent-cyan)','#030712')} onclick="closeBoardAuthModal();openAuthModal('register')">회원가입</button>
      <button ${btnStyle('rgba(255,255,255,0.06)','var(--text-muted)')} onclick="closeBoardAuthModal();openAuthModal('login')">로그인</button>
    `;
  } else {
    title.textContent = '이메일 인증 필요';
    desc.textContent  = '이 게시글은 이메일 인증을 완료한 회원만 열람할 수 있습니다. 가입 시 발송된 인증 메일을 확인해주세요.';
    btns.innerHTML = `
      <button ${btnStyle('var(--accent-cyan)','#030712')} onclick="resendVerifyEmail();closeBoardAuthModal()">인증 메일 재발송</button>
      <button ${btnStyle('rgba(255,255,255,0.06)','var(--text-muted)')} onclick="closeBoardAuthModal()">닫기</button>
    `;
  }

  modal.style.display = 'flex';
};

window.closeBoardAuthModal = function() {
  document.getElementById('board-auth-modal').style.display = 'none';
};

// ── 글쓰기 버튼 렌더링 ────────────────────────────────────
function _renderBoardButtons() {
  const user  = _getUser();
  const wrap  = document.getElementById('board-write-btns');
  const selBtn = document.getElementById('board-select-btn');
  if (!wrap) return;
  wrap.innerHTML = '';
  wrap.style.display = 'flex';

  if (user.isAdmin) {
    if (selBtn) selBtn.style.display = 'inline-block';
    const nb = document.createElement('button');
    nb.className = 'board-write-btn';
    nb.style.cssText = 'background:rgba(6,182,212,0.12);border:1px solid rgba(6,182,212,0.3);color:#67e8f9;';
    nb.textContent = '+ 공지사항 작성';
    nb.onclick = () => {
      document.getElementById('notice-title-input').value = '';
      document.getElementById('notice-content-input').value = '';
      document.getElementById('board-notice-modal').style.display = 'flex';
    };
    wrap.appendChild(nb);
  } else if (user.loggedIn && user.verified) {
    if (selBtn) selBtn.style.display = 'none';
    [['question','질문 작성','rgba(250,204,21,0.1)','rgba(250,204,21,0.3)','#fde047'],
     ['error','오류 신고','rgba(239,68,68,0.08)','rgba(239,68,68,0.25)','#f87171']].forEach(([type,label,bg,bc,color]) => {
      const btn = document.createElement('button');
      btn.className = 'board-write-btn';
      btn.style.cssText = `background:${bg};border:1px solid ${bc};color:${color};`;
      btn.textContent = label;
      btn.onclick = () => openBoardWrite(type);
      wrap.appendChild(btn);
    });
  } else {
    if (selBtn) selBtn.style.display = 'none';
  }
}

// ── 공지사항 등록 ─────────────────────────────────────────
window.submitNotice = async function() {
  const title   = (document.getElementById('notice-title-input')?.value||'').trim();
  const content = (document.getElementById('notice-content-input')?.value||'').trim();
  if (!title) { alert('제목을 입력하세요.'); return; }
  const res = await fetch('/api/board/posts', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ type:'notice', title, content })
  });
  if (res.ok) {
    // 공지는 pinned=1로 업데이트
    const { id } = await res.json();
    await fetch(`/api/board/posts/${id}/pin`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ pinned: true })
    });
    document.getElementById('board-notice-modal').style.display = 'none';
    loadBoardList();
  }
};

// ── 질문/오류신고 작성 모달 ───────────────────────────────
window.openBoardWrite = function(type) {
  _bwType = type;
  _bwSelectedProbId = null;
  document.getElementById('bw-selected-label').textContent = '없음';
  document.getElementById('bw-content-input').value = '';
  document.getElementById('bw-submit-btn').disabled = true;
  document.getElementById('bw-submit-btn').style.opacity = '0.5';

  const title  = document.getElementById('bw-title');
  const banner = document.getElementById('bw-banner');
  if (type === 'question') {
    title.textContent  = '💬 질문 작성';
    banner.textContent = '궁금한 문항을 선택하고 질문 내용을 입력하세요.';
  } else {
    title.textContent  = '🚨 오류 신고';
    banner.textContent = '정답이 없는 문항, 해설이 잘못된 문항 등 문항 번호만 알려주세요. 개선하는 데 큰 도움이 됩니다.';
  }

  // 기존 오류신고 모달의 연도별 버튼 UI 초기화
  _initBwYearButtons();
  document.getElementById('bw-step-grid').style.display = 'none';

  document.getElementById('board-write-overlay').style.display = 'flex';
};

window.closeBoardWrite = function() {
  document.getElementById('board-write-overlay').style.display = 'none';
  _bwType = null;
  _bwSelectedProbId = null;
};

function _initBwYearButtons() {
  if (typeof initBoardWriteYearButtons === 'function') {
    initBoardWriteYearButtons(function(problemId) {
      _bwSelectedProbId = problemId;
      document.getElementById('bw-selected-label').textContent = problemId;
      const btn = document.getElementById('bw-submit-btn');
      btn.disabled = false;
      btn.style.opacity = '1';
    });
  }
}

window.submitBoardWrite = async function() {
  if (!_bwSelectedProbId || !_bwType) return;
  const content = (document.getElementById('bw-content-input')?.value||'').trim();
  const title   = `[${_bwType === 'question' ? '질문' : '오류신고'}] ${_bwSelectedProbId}`;
  const res = await fetch('/api/board/posts', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ type: _bwType, title, content, problem_id: _bwSelectedProbId })
  });
  if (res.ok) {
    closeBoardWrite();
    loadBoardList();
  }
};

// ── PDF 게시 옵션 모달 ────────────────────────────────────
window.openBoardPublishModal = function(titleStr, problemIds, printCallback) {
  document.getElementById('publish-title-input').value  = titleStr || '';
  document.getElementById('publish-desc-input').value   = '';
  document.getElementById('publish-anon-check').checked = false;
  _publishCallback = { ids: problemIds, fn: printCallback };
  document.getElementById('board-publish-modal').style.display = 'flex';
};

window.closeBoardPublish = function() {
  document.getElementById('board-publish-modal').style.display = 'none';
  // 게시 없이 바로 인쇄
  if (_publishCallback?.fn) _publishCallback.fn();
  _publishCallback = null;
};

window.confirmBoardPublish = async function() {
  const title   = (document.getElementById('publish-title-input')?.value||'').trim() || '문항 세트';
  const content = (document.getElementById('publish-desc-input')?.value||'').trim();
  const isAnon  = document.getElementById('publish-anon-check')?.checked ? 1 : 0;
  const ids     = _publishCallback?.ids || [];

  document.getElementById('board-publish-modal').style.display = 'none';

  try {
    await fetch('/api/board/posts', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ type:'edit', title, content: content||null, is_anonymous: isAnon, problem_ids: ids })
    });
    loadBoardList();
  } catch(e) { /* 실패해도 인쇄 진행 */ }

  if (_publishCallback?.fn) _publishCallback.fn();
  _publishCallback = null;
};

// ── 인증 메일 재발송 (index.html의 함수 호출) ─────────────
window.resendVerifyEmail = async function() {
  if (typeof sendVerificationEmail === 'function') {
    sendVerificationEmail();
  }
};

// ── 초기화 ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadBoardList();
  _renderBoardButtons();
});
