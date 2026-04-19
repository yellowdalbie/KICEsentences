// cart.js
// Handles Problem Cart and Print Preview Modal logic

const cartProblemIds = new Set();
const cartItemsContainer = document.getElementById('cart-items-container');
const cartBadge = document.getElementById('cart-badge');
const cartEmptyMsg = document.getElementById('cart-empty-msg');
const cartToggleBtn = document.getElementById('cart-toggle-btn');
const problemCart = document.getElementById('problem-cart');

// Print Modal elements
const printModal = document.getElementById('print-preview-modal');
const printModalBody = document.getElementById('print-preview-body');
const sidebarOrderList = document.getElementById('sidebar-order-list');

// Module-level preview state
let _previewLoadedItems = [];
let _previewAnswerOpt = 'none';
let _previewExpOpt = 'none';
let _selectedSidebarIdx = null;

// ── 문항지 세트 기능 ──────────────────────────────────────────
const searchQueryLog = [];
let restoredTempIds = null;
let cartRestoreWarningShown = false;
let currentAutoTitle = '';

// ── 전역 썸네일 tooltip (document.body에 직접 붙여 transform 영향 차단) ──
let _cartThumbTooltipEl = null;

function getCartThumbTooltip() {
    if (!_cartThumbTooltipEl) {
        _cartThumbTooltipEl = document.createElement('div');
        _cartThumbTooltipEl.className = 'cart-thumb-tooltip';
        _cartThumbTooltipEl.innerHTML = '<img alt="" />';
        document.body.appendChild(_cartThumbTooltipEl);
    }
    return _cartThumbTooltipEl;
}

function showCartThumbTooltip(pid, anchorEl) {
    const tooltip = getCartThumbTooltip();
    tooltip.querySelector('img').src = `/thumbnail/${pid}`;
    tooltip.style.display = 'block';
    requestAnimationFrame(() => {
        const rect = anchorEl.getBoundingClientRect();
        let top = rect.bottom + 6;
        let left = rect.left;
        if (top + tooltip.offsetHeight > window.innerHeight) {
            top = rect.top - tooltip.offsetHeight - 6;
        }
        if (left + tooltip.offsetWidth > window.innerWidth) {
            left = window.innerWidth - tooltip.offsetWidth - 8;
        }
        tooltip.style.top = Math.max(4, top) + 'px';
        tooltip.style.left = Math.max(4, left) + 'px';
    });
}

function hideCartThumbTooltip() {
    if (_cartThumbTooltipEl) _cartThumbTooltipEl.style.display = 'none';
}

// Toggle cart slide (PC: 기존 사이드 토글 / 모바일: FAB가 대신 처리)
if (cartToggleBtn) {
    cartToggleBtn.addEventListener('click', () => {
        problemCart.classList.toggle('open');
        if (!problemCart.classList.contains('open')) hideCartThumbTooltip();
    });
}

function updateCartUI() {
    // Update badge number
    cartBadge.innerText = cartProblemIds.size;

    if (cartProblemIds.size === 0) {
        cartEmptyMsg.style.display = 'block';
        cartItemsContainer.innerHTML = '';
        cartItemsContainer.appendChild(cartEmptyMsg);
    } else {
        cartEmptyMsg.style.display = 'none';
        cartItemsContainer.innerHTML = ''; // clear current tags

        // Re-render tags
        Array.from(cartProblemIds).forEach(pid => {
            const tag = document.createElement('div');
            tag.className = 'cart-item-tag';
            const pidSpan = document.createElement('span');
            pidSpan.textContent = pid;
            const rmSpan = document.createElement('span');
            rmSpan.className = 'cart-item-remove';
            rmSpan.title = '제거';
            rmSpan.textContent = '×';
            tag.appendChild(pidSpan);
            tag.appendChild(rmSpan);

            // ── 기능 1: 썸네일 tooltip (body-level 전역 tooltip 사용) ──
            tag.addEventListener('mouseenter', () => showCartThumbTooltip(pid, tag));
            tag.addEventListener('mouseleave', hideCartThumbTooltip);

            // Remove from cart on click
            tag.querySelector('.cart-item-remove').addEventListener('click', (e) => {
                e.stopPropagation();
                hideCartThumbTooltip(); // × 클릭 시 DOM 제거 전에 툴팁 먼저 숨김
                toggleCartItem(pid);
            });

            cartItemsContainer.appendChild(tag);
        });
    }

    // Refresh visually in tables if they are stamped
    refreshTableCartVisuals();

    // 모바일 FAB 뱃지 동기화
    if (typeof updateCartFabBadge === 'function') {
        updateCartFabBadge(cartProblemIds.size);
    }
}

function _doAddItem(strId) {
    if (cartProblemIds.size === 20) {
        showCustomAlert('21번째 문항부터는 인쇄 미리보기 로딩이 다소 느릴 수 있습니다.');
    }
    cartProblemIds.add(strId);
    if (cartProblemIds.size === 1 && !problemCart.classList.contains('open')) {
        problemCart.classList.add('open');
        // 모바일 바텀시트 열릴 때 스크롤 잠금
        if (window.matchMedia && window.matchMedia('(pointer: coarse)').matches) {
            document.body.style.overflow = 'hidden';
        }
    }
    updateCartUI();
}

function toggleCartItem(problemId) {
    if (!problemId) return;
    const strId = String(problemId);

    if (cartProblemIds.has(strId)) {
        cartProblemIds.delete(strId);
        updateCartUI();
    } else {
        if (restoredTempIds && restoredTempIds.length > 0 && !cartRestoreWarningShown) {
            cartRestoreWarningShown = true;
            showCustomConfirm(
                `이전에 담아두셨던 ${restoredTempIds.length}문항이 있습니다.\n이어서 추가하시겠습니까?`,
                () => _doAddItem(strId),
                {
                    confirmText: '유지 및 추가',
                    confirmStyle: 'safe',
                    cancelText: '삭제 및 추가',
                    cancelStyle: 'danger',
                    onCancel: () => {
                        cartProblemIds.clear();
                        restoredTempIds = null;
                        dismissRestoreBanner();
                        fetch('/api/sets/restore', { method: 'DELETE' });
                        _doAddItem(strId);
                    }
                }
            );
        } else {
            _doAddItem(strId);
        }
    }
}

function refreshTableCartVisuals() {
    // Find all problem ID tags in tables and apply styling if they are in cart
    document.querySelectorAll('.prob-id-trigger').forEach(el => {
        const pid = String(el.dataset.probId);
        if (cartProblemIds.has(pid)) {
            el.classList.add('in-cart');
        } else {
            el.classList.remove('in-cart');
        }
    });

    // Also update detail table if visible
    document.querySelectorAll('#exp-detail-tbody tr td:first-child .prob-id-trigger').forEach(el => {
        const pid = String(el.dataset.probId);
        if (cartProblemIds.has(pid)) {
            el.classList.add('in-cart');
        } else {
            el.classList.remove('in-cart');
        }
    });
}

// Clear cart
function clearCart() {
    closeKebabMenu();
    cartProblemIds.clear();
    updateCartUI();
}

// Kebab menu toggle
function toggleKebabMenu(e) {
    e.stopPropagation();
    const menu = document.getElementById('cart-kebab-menu');
    const isOpen = menu.style.display === 'block';
    if (!isOpen) {
        const btn = document.getElementById('cart-more-btn');
        const rect = btn.getBoundingClientRect();
        menu.style.position = 'fixed';
        menu.style.right = (window.innerWidth - rect.right) + 'px';
        menu.style.bottom = (window.innerHeight - rect.top + 4) + 'px';
        menu.style.top = 'auto';
    }
    menu.style.display = isOpen ? 'none' : 'block';
}

function closeKebabMenu() {
    const menu = document.getElementById('cart-kebab-menu');
    if (menu) menu.style.display = 'none';
}

// Close kebab menu on outside click
document.addEventListener('click', (e) => {
    if (!e.target.closest('#cart-kebab-btn') && !e.target.closest('#cart-kebab-menu')) {
        closeKebabMenu();
    }
});

// "더블" 기능: 각 카트 문항에 대해 가장 유사한 쌍둥이 문항 자동 추가
async function doubleCart() {
    closeKebabMenu();
    if (cartProblemIds.size === 0) {
        showCustomAlert('장바구니가 비어 있습니다.');
        return;
    }

    const ids = Array.from(cartProblemIds);
    const kebabBtn = document.getElementById('cart-kebab-btn');
    if (kebabBtn) { kebabBtn.textContent = '⏳'; kebabBtn.disabled = true; }

    try {
        const res = await fetch('/api/double_cart', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ problem_ids: ids })
        });
        const data = await res.json();

        if (data.error) {
            showCustomAlert('더블 오류: ' + data.error);
            return;
        }

        // 매칭된 문항들 카트에 추가
        const newlyAdded = [];
        (data.added || []).forEach(({ match }) => {
            if (!cartProblemIds.has(match)) {
                cartProblemIds.add(match);
                newlyAdded.push(match);
            }
        });

        updateCartUI();

        // 새로 추가된 항목 잠깐 강조
        setTimeout(() => {
            newlyAdded.forEach(pid => {
                document.querySelectorAll('.cart-item-tag').forEach(tag => {
                    if (tag.querySelector('span')?.textContent === pid) {
                        tag.style.transition = 'background 0s';
                        tag.style.background = 'rgba(6,182,212,0.25)';
                        setTimeout(() => {
                            tag.style.transition = 'background 1.5s';
                            tag.style.background = '';
                        }, 800);
                    }
                });
            });
        }, 100);

        const unmatchedCount = (data.unmatched || []).length;
        if (unmatchedCount > 0) {
            showCustomAlert(`${newlyAdded.length}개 유사 문항을 추가했습니다.\n(${unmatchedCount}개는 유사 문항을 찾지 못했습니다.)`);
        }

    } catch (e) {
        showCustomAlert('더블 기능 오류: ' + e.message);
    } finally {
        if (kebabBtn) { kebabBtn.textContent = '⋮'; kebabBtn.disabled = false; }
    }
}

// Expose globally
window.clearCart = clearCart;
window.toggleKebabMenu = toggleKebabMenu;
window.doubleCart = doubleCart;


// Print Preview Logic
document.addEventListener('DOMContentLoaded', () => {
    const previewBtn = document.getElementById('preview-btn');
    if (previewBtn) {
        previewBtn.addEventListener('click', async () => {
            if (cartProblemIds.size === 0) {
                showCustomAlert('장바구니가 비어 있습니다.');
                return;
            }
            if (!checkAuthForPreview()) return;

            const ids = Array.from(cartProblemIds);

            if (!(typeof KICE_OFFLINE !== 'undefined' && KICE_OFFLINE)) {
                // 자동 명칭 생성
                try {
                    const titleRes = await fetch(`/api/sets/auto_title?ids=${encodeURIComponent(ids.join(','))}`);
                    const titleData = await titleRes.json();
                    currentAutoTitle = titleData.title || '문항 세트';
                } catch(e) {
                    currentAutoTitle = '문항 세트';
                }
                // 임시저장
                try {
                    await fetch('/api/sets/temp', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            problem_ids: ids,
                            title: currentAutoTitle,
                            source_query: getBestSearchQuery()
                        })
                    });
                    restoredTempIds = [...ids];
                    dismissRestoreBanner();
                } catch(e) { /* 실패해도 미리보기는 열기 */ }
            }

            openPrintPreview();
        });
    }
});

function logCartEvent(eventType, problemIds) {
    if (typeof KICE_OFFLINE !== 'undefined' && KICE_OFFLINE) return;
    fetch('/api/log_event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_type: eventType, problem_ids: problemIds })
    }).catch(() => {});
}

async function openPrintPreview() {
    printModalBody.innerHTML = '<div style="display:flex; justify-content:center; padding:3rem;"><div class="loader">이미지 및 정답을 불러오는 중...</div></div>';
    printModal.style.display = 'flex';
    document.body.style.overflow = 'hidden'; // Prevent background scrolling

    // Hide floating UI elements to avoid overlap with print preview
    document.body.classList.add('preview-open');
    const authSection = document.getElementById('auth-app-section');
    if (authSection) authSection.style.display = 'none';

    // Slide down the cart to avoid overlapping
    problemCart.classList.remove('open');

    const ids = Array.from(cartProblemIds);
    logCartEvent('open_preview', ids);
    // 장바구니에 담은 순서 그대로 유지 (정렬하지 않음)


    _previewAnswerOpt = document.getElementById('answer-display-opt').value;
    _previewExpOpt = document.getElementById('explanation-display-opt').value;

    try {
        // 1. Fetch Answers
        const res = await fetch('/api/problem_answers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ problem_ids: ids })
        });
        const ansData = await res.json();
        const answers = ansData.answers || {};

        // 2. Fetch explanation steps (separate 옵션일 때만)
        let stepsData = {};
        if (_previewExpOpt === 'separate') {
            const expRes = await fetch('/api/problem_steps_bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ problem_ids: ids })
            });
            const expData = await expRes.json();
            stepsData = expData.steps || {};
        }

        // 3. Measure Images
        const loadedItems = [];
        for (const pid of ids) {
            const imgInfo = await loadAndMeasureImage(`/thumbnail/${pid}`);
            // Determine if long: If aspect ratio (height/width) > 1.0
            const isLong = (imgInfo.height / imgInfo.width) > 1.0;
            loadedItems.push({
                pid,
                src: `/thumbnail/${pid}`,
                isLong,
                answer: answers[pid] || '',
                steps: stepsData[pid] || []
            });
        }

        // 모듈 변수에 저장 (드래그앤드롭 재사용)
        _previewLoadedItems = loadedItems;

        // 사이드바 렌더링
        renderSidebar();

        // 페이지 렌더링
        await renderPreviewPages();

    } catch (e) {
        console.error(e);
        const errP = document.createElement('p');
        errP.className = 'placeholder-text';
        errP.style.color = 'red';
        errP.textContent = `오류가 발생했습니다: ${e.message}`;
        printModalBody.innerHTML = '';
        printModalBody.appendChild(errP);
    }
}

// ── 사이드바 렌더링 (클릭 선택 → 위아래 버튼 표시) ──
function renderSidebar() {
    sidebarOrderList.innerHTML = '';
    const total = _previewLoadedItems.length;

    _previewLoadedItems.forEach((item, idx) => {
        const isSelected = _selectedSidebarIdx === idx;
        const li = document.createElement('li');
        li.className = 'sidebar-item' + (isSelected ? ' selected' : '');
        li.draggable = true;
        li.dataset.idx = idx;
        li.dataset.problemId = item.pid;
        li.innerHTML = `
            <div class="sidebar-item-row" style="flex:1; width:100%;">
                <div class="sidebar-drag-handle" title="드래그하여 순서 변경">⠿</div>
                <span class="sidebar-item-num">${idx + 1}</span>
                <span class="sidebar-item-pid">${item.pid}</span>
                <button class="sidebar-item-remove" title="제거">×</button>
            </div>
        `;

        li.addEventListener('click', (e) => {
            if (e.target.closest('.sidebar-item-remove')) return;
            _selectedSidebarIdx = idx;
            renderSidebar();
        });

        li.addEventListener('dragstart', (e) => {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', idx);
            li.classList.add('dragging');
        });

        li.addEventListener('dragend', () => {
            li.classList.remove('dragging');
            document.querySelectorAll('.sidebar-item').forEach(el => {
                el.classList.remove('drag-insert-before', 'drag-insert-after');
            });
        });

        li.querySelector('.sidebar-item-remove').addEventListener('click', (e) => {
            e.stopPropagation();
            _previewLoadedItems.splice(idx, 1);
            if (_selectedSidebarIdx !== null) {
                if (_selectedSidebarIdx === idx) _selectedSidebarIdx = null;
                else if (_selectedSidebarIdx > idx) _selectedSidebarIdx--;
            }
            renderSidebar();
            renderPreviewPages();
        });

        sidebarOrderList.appendChild(li);
    });

    if (!sidebarOrderList.dataset.dragbound) {
        sidebarOrderList.dataset.dragbound = "true";
        sidebarOrderList.style.paddingBottom = "40px"; // 여유 바닥 공간 제공
        
        sidebarOrderList.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            const y = e.clientY;
            const items = [...sidebarOrderList.querySelectorAll('.sidebar-item:not(.dragging)')];
            if (items.length === 0) return;
            
            let targetItem = null;
            for (let i = 0; i < items.length; i++) {
                const rect = items[i].getBoundingClientRect();
                const center = rect.top + rect.height / 2;
                if (y < center) {
                    targetItem = items[i];
                    break;
                }
            }
            
            sidebarOrderList.querySelectorAll('.sidebar-item').forEach(el => {
                el.classList.remove('drag-insert-before', 'drag-insert-after');
            });
            
            if (targetItem) {
                targetItem.classList.add('drag-insert-before');
            } else {
                items[items.length - 1].classList.add('drag-insert-after');
            }
        });

        sidebarOrderList.addEventListener('dragleave', (e) => {
            if (!sidebarOrderList.contains(e.relatedTarget)) {
                sidebarOrderList.querySelectorAll('.sidebar-item').forEach(el => {
                    el.classList.remove('drag-insert-before', 'drag-insert-after');
                });
            }
        });

        sidebarOrderList.addEventListener('drop', (e) => {
            e.preventDefault();
            const fromIdxStr = e.dataTransfer.getData('text/plain');
            if (!fromIdxStr) return;
            const fromIdx = parseInt(fromIdxStr, 10);
            
            let toIdx = -1;
            let isBefore = true;
            const items = [...sidebarOrderList.querySelectorAll('.sidebar-item')];
            for (let i = 0; i < items.length; i++) {
                if (items[i].classList.contains('drag-insert-before')) {
                    toIdx = parseInt(items[i].dataset.idx, 10);
                    isBefore = true;
                    break;
                } else if (items[i].classList.contains('drag-insert-after')) {
                    toIdx = parseInt(items[i].dataset.idx, 10);
                    isBefore = false;
                    break;
                }
            }
            
            sidebarOrderList.querySelectorAll('.sidebar-item').forEach(el => {
                el.classList.remove('drag-insert-before', 'drag-insert-after');
            });
            
            if (toIdx === -1 || fromIdx === toIdx) return;
            
            const movedItem = _previewLoadedItems.splice(fromIdx, 1)[0];
            
            if (fromIdx < toIdx) toIdx--;
            if (!isBefore) toIdx++;
            
            _previewLoadedItems.splice(toIdx, 0, movedItem);
            
            if (_selectedSidebarIdx !== null) {
                if (_selectedSidebarIdx === fromIdx) _selectedSidebarIdx = toIdx;
                else if (_selectedSidebarIdx > fromIdx && _selectedSidebarIdx <= toIdx) _selectedSidebarIdx--;
                else if (_selectedSidebarIdx < fromIdx && _selectedSidebarIdx >= toIdx) _selectedSidebarIdx++;
            }
            
            renderSidebar();
            renderPreviewPages();
        });
    }
}

// ── 페이지 렌더링 (순서 변경 시 재호출) ──
async function renderPreviewPages() {
    // 재렌더 전에 사용자가 수정한 타이틀이 있으면 currentAutoTitle에 보존
    const existingTitle = printModalBody.querySelector('.exam-title');
    if (existingTitle) {
        const t = existingTitle.textContent.trim();
        if (t) currentAutoTitle = t;
    }

    const items = _previewLoadedItems;
    const answerOpt = _previewAnswerOpt;
    const expOpt = _previewExpOpt;

    // examNumber 재할당 (순서 기반)
    items.forEach((item, index) => {
        item.examNumber = index + 1;
    });

    // 배치 알고리즘
    const pages = [];
    let currentPage = { cols: [[], []] };
    pages.push(currentPage);
    let activeColIdx = 0;

    items.forEach(item => {
        if (item.isLong) {
            if (currentPage.cols[activeColIdx].length > 0) {
                activeColIdx++;
                if (activeColIdx > 1) {
                    currentPage = { cols: [[], []] };
                    pages.push(currentPage);
                    activeColIdx = 0;
                }
            }
            currentPage.cols[activeColIdx].push(item);
            activeColIdx++;
            if (activeColIdx > 1) {
                currentPage = { cols: [[], []] };
                pages.push(currentPage);
                activeColIdx = 0;
            }
        } else {
            if (currentPage.cols[activeColIdx].length >= 2) {
                activeColIdx++;
                if (activeColIdx > 1) {
                    currentPage = { cols: [[], []] };
                    pages.push(currentPage);
                    activeColIdx = 0;
                }
            }
            currentPage.cols[activeColIdx].push(item);
        }
    });

    // 빈 페이지 정리
    if (pages.length > 0 && pages[pages.length - 1].cols[0].length === 0 && pages[pages.length - 1].cols[1].length === 0) {
        pages.pop();
    }

    // 정답표 (end 옵션)
    if (answerOpt === 'end') {
        let tableHtml = `<div style="text-align:center; font-size:1.1rem; font-weight:bold; margin-bottom:10px; border:2px solid #111; padding:4px; color:#111; background:#fff;">정답표</div>`;
        const colsPerBlock = 5;
        for (let i = 0; i < items.length; i += colsPerBlock) {
            const chunk = items.slice(i, i + colsPerBlock);
            let numRow = `<tr><th class="csat-ans-header">문항</th>`;
            let ansRow = `<tr><th class="csat-ans-header">정답</th>`;
            for (let j = 0; j < colsPerBlock; j++) {
                if (j < chunk.length) {
                    numRow += `<td>${chunk[j].examNumber}</td>`;
                    ansRow += `<td class="csat-ans-val">${chunk[j].answer || '-'}</td>`;
                } else {
                    numRow += `<td></td>`;
                    ansRow += `<td></td>`;
                }
            }
            numRow += `</tr>`;
            ansRow += `</tr>`;
            tableHtml += `<table class="csat-ans-table-end" style="width:100%; margin-bottom:10px; border-collapse:collapse; text-align:center; font-size:0.85rem;">
                <tbody>${numRow}${ansRow}</tbody>
            </table>`;
        }

        const tableItem = {
            isTable: true,
            html: `<div class="csat-item-container" style="height:100%; display:flex; flex-direction:column; justify-content:flex-end; padding-bottom:15px;">${tableHtml}</div>`
        };

        let lastPage = pages[pages.length - 1];
        if (!lastPage.cols[1]) lastPage.cols[1] = [];

        if (lastPage.cols[1].length === 2) {
            const newPage = { cols: [[], []] };
            newPage.cols[1].push({ isEmptyPlaceholder: true });
            newPage.cols[1].push(tableItem);
            pages.push(newPage);
        } else {
            if (lastPage.cols[1].length === 0) {
                lastPage.cols[1].push({ isEmptyPlaceholder: true });
            }
            if (lastPage.cols[1].length === 1 && (lastPage.cols[1][0] && lastPage.cols[1][0].isLong)) {
                const newPage = { cols: [[], []] };
                newPage.cols[1].push({ isEmptyPlaceholder: true });
                newPage.cols[1].push(tableItem);
                pages.push(newPage);
            } else {
                lastPage.cols[1].push(tableItem);
            }
        }
    }

    // 해설지 페이지 생성
    let expPages = [];
    if (expOpt === 'separate') {
        const expItems = items
            .filter(item => item.steps && item.steps.length > 0)
            .map(item => ({ pid: item.pid, examNumber: item.examNumber, steps: item.steps, answer: item.answer }));
        if (expItems.length > 0) {
            expPages = await buildExplanationPages(expItems, pages.length);
        }
    }
    const totalPageCount = pages.length + expPages.length;

    // HTML 렌더링
    printModalBody.innerHTML = '';
    pages.forEach((page, pIdx) => {
        const pageDiv = document.createElement('div');
        pageDiv.className = 'csat-page';

        // Header
        if (pIdx === 0) {
            pageDiv.innerHTML += `
                <div class="csat-header-page1">
                    <div class="h1-top">
                        <span class="exam-title" contenteditable="false">2028학년도 대학수학능력시험 대비 문제지</span>
                    </div>
                    <div class="h1-main-wrapper" style="position:relative; margin-bottom: 10px;">
                        <span class="exam-period">제 2 교시</span>
                        <div class="h1-main">수학 영역</div>
                        <span class="exam-type">홀수형</span>
                    </div>
                    <div class="h1-divider"></div>
                </div>
            `;
        } else {
            pageDiv.innerHTML += `
                <div class="csat-header-normal">
                    <span class="page-num">${pIdx + 1}</span>
                    <span class="h-main">수학 영역</span>
                    <span class="h-type">홀수형</span>
                </div>
            `;
        }

        // Columns Container
        const colsDiv = document.createElement('div');
        colsDiv.className = 'csat-columns';

        page.cols.forEach((colItems, cIdx) => {
            const colDiv = document.createElement('div');
            colDiv.className = 'csat-col';

            colItems.forEach(item => {
                if (item.isEmptyPlaceholder) {
                    colDiv.innerHTML += `<div class="csat-item-container"></div>`;
                    return;
                }
                if (item.isTable) {
                    colDiv.innerHTML += item.html;
                    return;
                }

                let ansHtml = '';
                if (answerOpt === 'inline' && item.answer) {
                    ansHtml = `<span class="csat-inline-answer">${item.answer}</span>`;
                }
                let extraClass = item.isLong ? ' is-long' : '';
                colDiv.innerHTML += `
                    <div class="csat-item-container${extraClass}">
                        <div class="csat-meta-row">
                            <div class="csat-meta-left">
                                <span class="csat-seq-num">${item.examNumber}.</span>
                                <span class="csat-db-id-tag">${item.pid}</span>
                            </div>
                            ${ansHtml}
                        </div>
                        <div class="csat-img-area">
                            <img src="${item.src}" class="csat-prob-img" alt="${item.pid}" />
                        </div>
                    </div>
                `;
            });
            colsDiv.appendChild(colDiv);

            // Vertical divider after first column
            if (cIdx === 0) {
                const vLine = document.createElement('div');
                vLine.className = 'csat-vline';
                colsDiv.appendChild(vLine);
            }
        });

        pageDiv.appendChild(colsDiv);

        // Footer
        const footerDiv = document.createElement('div');
        footerDiv.className = 'csat-footer';
        footerDiv.innerHTML = `
            <div class="footer-page-box">
                <span class="footer-page-current">${pIdx + 1}</span>
                <span class="footer-page-total">${totalPageCount}</span>
            </div>
            <div class="footer-copyright">* 이 문제지에 관한 저작권은 한국교육과정평가원에 있습니다.</div>
        `;
        pageDiv.appendChild(footerDiv);

        printModalBody.appendChild(pageDiv);
    });

    // 해설지 페이지 append
    for (const expPageDiv of expPages) {
        printModalBody.appendChild(expPageDiv);
    }

    // 전체 KaTeX 렌더링
    if (window.renderMathInElement) {
        renderMathInElement(printModalBody, {
            delimiters: [
                { left: '$$', right: '$$', display: true },
                { left: '$', right: '$', display: false }
            ]
        });
    }

    // currentAutoTitle로 인쇄 레이아웃 기본 타이틀 교체
    if (currentAutoTitle) {
        const examTitles = printModalBody.querySelectorAll('.exam-title');
        if (examTitles.length >= 1) {
            examTitles[0].textContent = currentAutoTitle;
        }
        if (examTitles.length >= 2) {
            examTitles[1].textContent = currentAutoTitle + ' 해설지';
        }
    }

    // 문제지 타이틀 수정 시 해설지 타이틀 동기화
    const examTitles = printModalBody.querySelectorAll('.exam-title');
    if (examTitles.length > 1) {
        examTitles[0].addEventListener('input', (e) => {
            let text = e.target.textContent.trim();
            if (text.endsWith('문제지')) {
                text = text.slice(0, -3) + '해설지';
            } else if (text.endsWith('문제')) {
                text = text.slice(0, -2) + '해설';
            } else if (!text.endsWith('해설지') && !text.endsWith('해설')) {
                text = text + ' 해설지';
            }
            examTitles[1].textContent = text;
        });
    }
}

// ── 해설 아이템 전체 HTML (csat-exp-item 래퍼 포함) ──
function buildExpItemHtml(item) {
    const stepsHtml = item.steps.map(step => `
        <div class="csat-exp-step">
            <div class="csat-exp-step-title">Step ${step.step_number}${step.step_title ? ' — ' + step.step_title : ''}</div>
            <div class="csat-exp-step-body">${step.explanation_html}</div>
        </div>
    `).join('');
    const ansHtml = item.answer ? `<span class="csat-exp-answer">${item.answer}</span>` : '';
    return `
        <div class="csat-exp-item">
            <div class="csat-exp-item-header">
                <div class="csat-exp-item-header-left">
                    <span class="csat-num-box">${item.examNumber}</span>
                    <span class="csat-db-id-tag">${item.pid}</span>
                </div>
                ${ansHtml}
            </div>
            <div class="csat-exp-item-steps">${stepsHtml}</div>
        </div>
    `;
}

// ── step 분할 청크 HTML (긴 해설을 step 단위로 쪼갤 때 사용) ──
function buildExpChunkHtml(item, stepIndices, isFirstChunk) {
    const stepsHtml = stepIndices.map(sIdx => {
        const step = item.steps[sIdx];
        return `
            <div class="csat-exp-step">
                <div class="csat-exp-step-title">Step ${step.step_number}${step.step_title ? ' — ' + step.step_title : ''}</div>
                <div class="csat-exp-step-body">${step.explanation_html}</div>
            </div>
        `;
    }).join('');

    if (isFirstChunk) {
        const ansHtml = item.answer ? `<span class="csat-exp-answer">${item.answer}</span>` : '';
        return `
            <div class="csat-exp-item">
                <div class="csat-exp-item-header">
                    <div class="csat-exp-item-header-left">
                        <span class="csat-num-box">${item.examNumber}</span>
                        <span class="csat-db-id-tag">${item.pid}</span>
                    </div>
                    ${ansHtml}
                </div>
                <div class="csat-exp-item-steps">${stepsHtml}</div>
            </div>
        `;
    } else {
        return `
            <div class="csat-exp-item csat-exp-item-cont">
                <div class="csat-exp-item-steps">${stepsHtml}</div>
            </div>
        `;
    }
}

// ── 해설지 페이지 배열 생성 (정밀 DOM 측정 기반) ──
async function buildExplanationPages(expItems, problemPageCount) {

    // ── 1단계: 실제 csat-page/csat-col 치수를 DOM으로 직접 측정 ──
    // 레퍼런스 페이지를 실제 DOM에 삽입해 브라우저가 mm→px 변환을 정확히 처리하게 함
    const refPage = document.createElement('div');
    refPage.className = 'csat-page';
    refPage.style.cssText = 'position:absolute;left:-9999px;top:0;visibility:hidden;pointer-events:none;';
    refPage.innerHTML = `
        <div class="csat-header-normal">
            <span class="page-num">2</span>
            <span class="h-main">수학 영역</span>
            <span class="h-type">홀수형</span>
        </div>
        <div class="csat-columns">
            <div class="csat-col csat-exp-col"><div id="__probe__"></div></div>
            <div class="csat-vline"></div>
            <div class="csat-col csat-exp-col"></div>
        </div>
        <div class="csat-footer"><div class="footer-page-box"></div></div>
    `;
    document.body.appendChild(refPage);

    // 첫 페이지용 헤더 높이 측정 (별도 요소)
    const refHdr1 = document.createElement('div');
    refHdr1.className = 'csat-header-page1';
    refHdr1.style.cssText = `position:absolute;left:-9999px;top:0;visibility:hidden;width:${refPage.offsetWidth}px;`;
    refHdr1.innerHTML = `
        <div class="h1-top"><span class="exam-title">해설지</span></div>
        <div class="h1-main-wrapper"><div class="h1-main">수학 영역</div></div>
        <div class="h1-divider"></div>
    `;
    document.body.appendChild(refHdr1);

    // 레이아웃 2회 확정 대기 (KaTeX 등 비동기 요소 안정화)
    await new Promise(r => requestAnimationFrame(r));
    await new Promise(r => requestAnimationFrame(r));

    const pageH      = refPage.offsetHeight;
    const hdrNormalH = refPage.querySelector('.csat-header-normal').offsetHeight;
    const hdrFirstH  = refHdr1.offsetHeight;
    const footerH    = refPage.querySelector('.csat-footer').offsetHeight;
    // 프로브 div의 offsetWidth = csat-col 내부 콘텐츠 실제 너비 (padding 제외)
    const innerColW  = refPage.querySelector('#__probe__').offsetWidth;

    refPage.remove();
    refHdr1.remove();

    // 안전 마진: 소수점 반올림 + KaTeX 렌더링 편차 흡수
    const SAFETY = 80;
    const usableFirst  = pageH - hdrFirstH  - footerH - SAFETY;
    const usableNormal = pageH - hdrNormalH - footerH - SAFETY;

    // ── 2단계: 아이템 높이 측정 (정확한 내부 너비로) ──
    const measureCol = document.createElement('div');
    // csat-exp-col과 동일한 너비·구조로 설정
    measureCol.style.cssText = `
        position:absolute;left:-9999px;top:0;visibility:hidden;
        width:${innerColW}px;overflow:visible;
    `;
    document.body.appendChild(measureCol);

    const itemEls = [];
    for (const item of expItems) {
        const wrapper = document.createElement('div');
        wrapper.innerHTML = buildExpItemHtml(item);
        const el = wrapper.firstElementChild; // .csat-exp-item
        measureCol.appendChild(el);
        if (window.renderMathInElement) {
            renderMathInElement(el, {
                delimiters: [
                    { left: '$$', right: '$$', display: true },
                    { left: '$', right: '$', display: false }
                ]
            });
        }
        itemEls.push(el);
    }

    // 레이아웃 확정 대기
    await new Promise(r => requestAnimationFrame(r));
    await new Promise(r => requestAnimationFrame(r));

    // ── 3단계: 배치 단위(unit) 결정 ──
    // csat-exp-col의 gap:12px 를 각 아이템 높이에 더함
    const COL_GAP    = 12;
    const HDR_MB     = 6;  // .csat-exp-item-header margin-bottom
    const ITEM_PB    = 10; // .csat-exp-item padding-bottom
    const STEP_MB    = 7;  // .csat-exp-step margin-bottom

    // ── 3+4단계 통합: 인라인 분할 + bin-packing ──
    // 각 문항을 현재 단의 남은 공간에 맞춰 분할하고 이어서 배치
    const expPagesList = [];
    let curPage = { isFirst: true, cols: [{ units: [], usedH: 0 }, { units: [], usedH: 0 }] };
    expPagesList.push(curPage);
    let colIdx = 0;

    const colLimit    = () => curPage.isFirst ? usableFirst : usableNormal;
    const colUsed     = () => curPage.cols[colIdx].usedH;
    const colRemaining= () => colLimit() - colUsed();
    const addUnit     = (html, h) => {
        curPage.cols[colIdx].units.push({ html, height: h });
        curPage.cols[colIdx].usedH += h;
    };
    const nextCol = () => {
        colIdx++;
        if (colIdx > 1) {
            curPage = { isFirst: false, cols: [{ units: [], usedH: 0 }, { units: [], usedH: 0 }] };
            expPagesList.push(curPage);
            colIdx = 0;
        }
    };

    for (let i = 0; i < expItems.length; i++) {
        const item  = expItems[i];
        const el    = itemEls[i];
        const fullH = el.offsetHeight + COL_GAP;

        // 전체가 현재 단의 남은 공간에 들어가면 단일 유닛으로 배치
        if (colUsed() + fullH <= colLimit()) {
            addUnit(buildExpItemHtml(item), fullH);
            continue;
        }

        // 현재 단 남은 공간에 통째로 안 들어가면 step 단위로 분할 배치
        // (헤더+Step1이 남은 공간에 들어가면 현재 단에, 아니면 step-splitting이 nextCol 처리)
        const headerEl = el.querySelector('.csat-exp-item-header');
        const headerH  = (headerEl ? headerEl.offsetHeight : 0) + HDR_MB;
        const stepEls  = Array.from(el.querySelectorAll('.csat-exp-step'));
        const stepHs   = stepEls.map(se => se.offsetHeight + STEP_MB);

        let isFirstChunk  = true;
        let chunkStepIdxs = [];
        let chunkH        = 0;

        for (let s = 0; s < stepEls.length; s++) {
            const stepH    = stepHs[s];
            const overhead = isFirstChunk ? headerH + ITEM_PB + COL_GAP : ITEM_PB + COL_GAP;

            if (chunkStepIdxs.length === 0) {
                // 새 청크 시작: overhead + stepH가 현재 단에 들어가는지 확인
                // isFirstChunk=true이면 overhead에 문항번호 헤더가 포함되어 있으므로
                // 남은 공간이 부족하면 문항번호와 함께 다음 단으로 이동
                if (overhead + stepH > colRemaining() && colUsed() > 0) {
                    nextCol();
                }
                chunkStepIdxs = [s];
                chunkH = overhead + stepH;
            } else {
                if (chunkH + stepH > colRemaining()) {
                    // 현재 청크 flush 후 다음 단으로 이어서
                    addUnit(buildExpChunkHtml(item, chunkStepIdxs, isFirstChunk), chunkH);
                    isFirstChunk  = false;
                    nextCol();
                    chunkStepIdxs = [s];
                    chunkH        = ITEM_PB + COL_GAP + stepH;
                } else {
                    chunkStepIdxs.push(s);
                    chunkH += stepH;
                }
            }
        }

        // 마지막 청크 flush
        if (chunkStepIdxs.length > 0) {
            addUnit(buildExpChunkHtml(item, chunkStepIdxs, isFirstChunk), chunkH);
        }
    }

    measureCol.remove();

    // ── 5단계: 해설지 DOM 렌더링 ──
    const result = [];
    const totalPages = problemPageCount + expPagesList.length;

    expPagesList.forEach((expPage, epIdx) => {
        const globalPageNum = problemPageCount + epIdx + 1;
        const pageDiv = document.createElement('div');
        pageDiv.className = 'csat-page';

        if (expPage.isFirst) {
            pageDiv.innerHTML = `
                <div class="csat-header-page1">
                    <div class="h1-top">
                        <span class="exam-title" contenteditable="false">2028학년도 대학수학능력시험 대비 해설지</span>
                    </div>
                    <div class="h1-main-wrapper" style="position:relative; margin-bottom:10px;">
                        <span class="exam-period">제 2 교시</span>
                        <div class="h1-main">수학 영역</div>
                        <span class="exam-type">홀수형</span>
                    </div>
                    <div class="h1-divider"></div>
                </div>
            `;
        } else {
            pageDiv.innerHTML = `
                <div class="csat-header-normal">
                    <span class="page-num">${globalPageNum}</span>
                    <span class="h-main">수학 영역</span>
                    <span class="h-type">홀수형</span>
                </div>
            `;
        }

        const colsDiv = document.createElement('div');
        colsDiv.className = 'csat-columns';

        expPage.cols.forEach((col, cIdx) => {
            const colDiv = document.createElement('div');
            colDiv.className = 'csat-col csat-exp-col';

            col.units.forEach(unit => {
                const wrapper = document.createElement('div');
                wrapper.innerHTML = unit.html;
                // unit.html의 최상위 요소(csat-exp-item)를 직접 삽입
                while (wrapper.firstChild) colDiv.appendChild(wrapper.firstChild);
            });

            colsDiv.appendChild(colDiv);
            if (cIdx === 0) {
                const vLine = document.createElement('div');
                vLine.className = 'csat-vline';
                colsDiv.appendChild(vLine);
            }
        });

        pageDiv.appendChild(colsDiv);

        const footerDiv = document.createElement('div');
        footerDiv.className = 'csat-footer';
        footerDiv.innerHTML = `
            <div class="footer-page-box">
                <span class="footer-page-current">${globalPageNum}</span>
                <span class="footer-page-total">${totalPages}</span>
            </div>
            <div class="footer-copyright">* 이 문제지에 관한 저작권은 한국교육과정평가원에 있습니다.</div>
        `;
        pageDiv.appendChild(footerDiv);

        result.push(pageDiv);
    });

    return result;
}

// Helper to measure image size
function loadAndMeasureImage(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve({ width: img.naturalWidth, height: img.naturalHeight });
        img.onerror = () => resolve({ width: 1, height: 1 }); // fallback
        img.src = src;
    });
}

function setPrintPill(btn) {
    const target = btn.dataset.target;
    const val = btn.dataset.value;


    document.querySelectorAll(`.print-pill[data-target="${target}"]`).forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(target).value = val;
    openPrintPreview();
}

async function logAndPrint() {
    // 사이드바 현재 순서에서 problem_ids 추출
    const sidebarItems = document.querySelectorAll('#sidebar-order-list li');
    const orderedIds = Array.from(sidebarItems)
        .map(li => li.dataset.problemId)
        .filter(Boolean);
    // fallback: 사이드바에 data-problem-id 없으면 cartProblemIds 사용
    const finalIds = orderedIds.length > 0 ? orderedIds : Array.from(cartProblemIds);

    // 현재 타이틀 추출 (사용자가 직접 수정했을 경우 우선, 아니면 자동 생성 타이틀)
    const examTitleEl = printModalBody?.querySelector('.exam-title');
    const editedTitle = (examTitleEl?.textContent || '').trim();
    const title = editedTitle || currentAutoTitle || '문항 세트';

    if (!(typeof KICE_OFFLINE !== 'undefined' && KICE_OFFLINE)) {
        // 완전저장
        try {
            await fetch('/api/sets/final', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    problem_ids: finalIds,
                    title: title,
                    source_query: getBestSearchQuery()
                })
            });
        } catch(e) { /* 저장 실패해도 인쇄는 진행 */ }
    }

    // PDF 파일명 설정 (document.title 트릭)
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    const datetime = `${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}`;
    const pdfFilename = `${title}_${datetime}`;
    const originalTitle = document.title;
    document.title = pdfFilename;

    window.print();

    window.addEventListener('afterprint', () => {
        document.title = originalTitle;
    }, { once: true });

    logCartEvent('save_pdf', finalIds);
}

function closePrintPreview() {
    printModal.style.display = 'none';
    document.body.style.overflow = ''; // Restore background scrolling
    printModalBody.innerHTML = ''; // clear memory

    // Restore floating UI elements
    document.body.classList.remove('preview-open');
    const authSection = document.getElementById('auth-app-section');
    if (authSection) authSection.style.display = '';

    // 모듈 변수 초기화
    _previewLoadedItems = [];
    _selectedSidebarIdx = null;
}

// Custom Alert Functions
let _customAlertCallback = null;

function showCustomAlert(message, onConfirm) {
    const modal = document.getElementById('custom-alert-modal');
    const msgEl = document.getElementById('custom-alert-message');
    if (!modal || !msgEl) return;

    _customAlertCallback = onConfirm || null;
    msgEl.innerText = message;
    modal.style.display = 'flex';

    // Trigger animation
    setTimeout(() => {
        modal.classList.add('show');
    }, 10);
}

function closeCustomAlert() {
    const modal = document.getElementById('custom-alert-modal');
    if (!modal) return;

    modal.classList.remove('show');
    setTimeout(() => {
        modal.style.display = 'none';
        if (typeof _customAlertCallback === 'function') {
            _customAlertCallback();
            _customAlertCallback = null;
        }
    }, 300);
}

// Global exposure for index.html calls
window.showCustomAlert = showCustomAlert;
window.closeCustomAlert = closeCustomAlert;

// Custom Confirm Functions
let _customConfirmCallback = null;
let _customConfirmCancelCallback = null;

function showCustomConfirm(message, onConfirm, options = {}) {
    const modal = document.getElementById('custom-confirm-modal');
    const msgEl = document.getElementById('custom-confirm-message');
    const okBtn = document.getElementById('custom-confirm-ok-btn');
    const cancelBtn = document.getElementById('custom-confirm-cancel-btn');
    const iconEl = document.getElementById('custom-confirm-icon');
    if (!modal || !msgEl) return;

    _customConfirmCallback = onConfirm || null;
    _customConfirmCancelCallback = options.onCancel || null;
    msgEl.innerHTML = escapeHtmlStr(message).replace(/\n/g, '<br>');

    const allStyles = ['cmodal-btn-primary', 'cmodal-btn-safe', 'cmodal-btn-danger', 'cmodal-btn-neutral'];

    if (okBtn) {
        okBtn.textContent = options.confirmText || '확인';
        okBtn.style.background = '';
        okBtn.style.boxShadow = '';
        okBtn.classList.remove(...allStyles);
        const confirmStyle = options.confirmStyle || (options.dangerous ? 'danger' : 'primary');
        okBtn.classList.add(`cmodal-btn-${confirmStyle}`);
    }
    if (cancelBtn) {
        cancelBtn.textContent = options.cancelText || '취소';
        cancelBtn.classList.remove(...allStyles);
        const cancelStyle = options.cancelStyle || 'neutral';
        cancelBtn.classList.add(`cmodal-btn-${cancelStyle}`);
    }
    if (iconEl) {
        const isDanger = options.dangerous || options.confirmStyle === 'danger';
        iconEl.style.background = isDanger ? 'rgba(239,68,68,0.2)' : 'rgba(139,92,246,0.2)';
        iconEl.style.color = isDanger ? '#f87171' : '#a78bfa';
    }

    modal.style.display = 'flex';
    setTimeout(() => modal.classList.add('show'), 10);
}

function closeCustomConfirm(isConfirmed) {
    const modal = document.getElementById('custom-confirm-modal');
    if (!modal) return;

    modal.classList.remove('show');
    setTimeout(() => {
        modal.style.display = 'none';
        if (isConfirmed && typeof _customConfirmCallback === 'function') {
            _customConfirmCallback();
        } else if (!isConfirmed && typeof _customConfirmCancelCallback === 'function') {
            _customConfirmCancelCallback();
        }
        _customConfirmCallback = null;
        _customConfirmCancelCallback = null;
    }, 300);
}

window.showCustomConfirm = showCustomConfirm;
window.closeCustomConfirm = closeCustomConfirm;

// Custom Prompt Functions
let _customPromptCallback = null;

function showCustomPrompt(message, defaultValue, onResult) {
    const modal = document.getElementById('custom-prompt-modal');
    const msgEl = document.getElementById('custom-prompt-message');
    const input = document.getElementById('custom-prompt-input');
    if (!modal || !msgEl || !input) return;

    _customPromptCallback = onResult || null;
    msgEl.innerHTML = escapeHtmlStr(message).replace(/\n/g, '<br>');
    input.value = defaultValue || '';
    modal.style.display = 'flex';
    setTimeout(() => {
        modal.classList.add('show');
        input.focus();
        input.select();
    }, 50);
}

function closeCustomPrompt(isConfirmed) {
    const modal = document.getElementById('custom-prompt-modal');
    const input = document.getElementById('custom-prompt-input');
    if (!modal) return;

    modal.classList.remove('show');
    const value = isConfirmed ? (input ? input.value : '') : null;
    setTimeout(() => {
        modal.style.display = 'none';
        if (typeof _customPromptCallback === 'function') {
            _customPromptCallback(value);
        }
        _customPromptCallback = null;
    }, 300);
}

window.showCustomPrompt = showCustomPrompt;
window.closeCustomPrompt = closeCustomPrompt;

// Initial UI setup
updateCartUI();

// --- Auth & Paywall Logic (Real Backend Integration) ---
window.AUTH_STATE = { isLoggedIn: false, email: '', isPaid: false };

const AUTH_MODAL_HTML = `
<div id="auth-modal" class="modal-overlay" style="display: none;">
  <div class="modal-content" style="max-width: 380px; padding: 2.5rem 2.5rem 2rem;">

    <!-- Close Button -->
    <button class="modal-close" onclick="closeAuthModal()" style="font-size: 1.4rem;">&times;</button>

    <!-- Icon + Title -->
    <div style="text-align: center; margin-bottom: 1.8rem;">
      <div style="width: 48px; height: 48px; background: rgba(6,182,212,0.12); border: 1px solid rgba(6,182,212,0.3); border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#06b6d4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg></div>
      <h3 id="auth-modal-title" style="margin: 0; font-size: 1.3rem; font-weight: 700; color: #f1f5f9; letter-spacing: -0.01em;">\ub85c\uadf8\uc778</h3>
      <p style="margin: 0.4rem 0 0; font-size: 0.82rem; color: #64748b;">미리보기/인쇄 기능을 이용하려면 로그인이 필요합니다</p>
    </div>

    <!-- Error Message -->
    <div id="auth-error-msg" style="display: none; color: #f87171; font-size: 0.82rem; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1.2rem;"></div>

    <!-- Email Field -->
    <div style="margin-bottom: 1rem;">
      <label style="display: block; margin-bottom: 0.4rem; font-size: 0.78rem; font-weight: 600; color: #94a3b8; letter-spacing: 0.06em; text-transform: uppercase;">이메일</label>
      <input type="email" id="auth-email"
        style="width: 100%; box-sizing: border-box; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 0.75rem 1rem; font-size: 0.92rem; color: #f1f5f9; outline: none; transition: border-color 0.2s, box-shadow 0.2s;"
        placeholder="you@example.com"
        onfocus="this.style.borderColor='rgba(6,182,212,0.5)';this.style.boxShadow='0 0 0 3px rgba(6,182,212,0.08)'"
        onblur="this.style.borderColor='rgba(255,255,255,0.1)';this.style.boxShadow='none'"
      >
    </div>

    <!-- Password Field -->
    <div style="margin-bottom: 1.6rem;">
      <label style="display: block; margin-bottom: 0.4rem; font-size: 0.78rem; font-weight: 600; color: #94a3b8; letter-spacing: 0.06em; text-transform: uppercase;">비밀번호</label>
      <input type="password" id="auth-password"
        style="width: 100%; box-sizing: border-box; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 0.75rem 1rem; font-size: 0.92rem; color: #f1f5f9; outline: none; transition: border-color 0.2s, box-shadow 0.2s;"
        placeholder="6자리 이상"
        onfocus="this.style.borderColor='rgba(6,182,212,0.5)';this.style.boxShadow='0 0 0 3px rgba(6,182,212,0.08)'"
        onblur="this.style.borderColor='rgba(255,255,255,0.1)';this.style.boxShadow='none'"
      >
    </div>

    <!-- Submit Button -->
    <button id="auth-submit-btn" onclick="submitAuth()"
      style="width: 100%; background: linear-gradient(135deg, #06b6d4, #0891b2); border: none; border-radius: 10px; padding: 0.85rem 1rem; font-size: 0.95rem; font-weight: 700; color: #030712; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 16px rgba(6,182,212,0.3); margin-bottom: 0.7rem;"
      onmouseover="this.style.transform='translateY(-1px)';this.style.boxShadow='0 6px 24px rgba(6,182,212,0.45)'"
      onmouseout="this.style.transform='translateY(0)';this.style.boxShadow='0 4px 16px rgba(6,182,212,0.3)'"
    >\ub85c\uadf8\uc778</button>

    <!-- Forgot Password Link (로그인 모드에서만 표시) -->
    <div id="auth-forgot-wrap" style="text-align:right; margin-bottom:0.8rem;">
      <a href="javascript:void(0)" onclick="openForgotPasswordModal()"
        style="font-size:0.76rem;color:#64748b;text-decoration:none;transition:color 0.2s;"
        onmouseover="this.style.color='#06b6d4'" onmouseout="this.style.color='#64748b'"
      >비밀번호를 잊으셨나요?</a>
    </div>

    <!-- Toggle Mode -->
    <div style="text-align: center; font-size: 0.85rem; color: #64748b;">
      <span id="auth-toggle-text">\uacc4\uc815\uc774 \uc5c6\uc73c\uc2e0\uac00\uc694?</span>
      <a href="javascript:void(0)" onclick="toggleAuthMode()" id="auth-toggle-link"
        style="color: #06b6d4; margin-left: 6px; font-weight: 700; text-decoration: none; transition: color 0.2s;"
        onmouseover="this.style.color='#67e8f9'"
        onmouseout="this.style.color='#06b6d4'"
      >\ud68c\uc6d0\uac00\uc785</a>
    </div>
  </div>
</div>
`;

let authMode = 'login';

function injectAuthModal() {
    if (!document.getElementById('auth-modal')) {
        document.body.insertAdjacentHTML('beforeend', AUTH_MODAL_HTML);
        
        // Enter key support
        document.getElementById('auth-password').addEventListener('keyup', (e) => {
            if (e.key === 'Enter') submitAuth();
        });
    }
}

window.openAuthModal = function(mode = 'login') {
    authMode = mode;
    injectAuthModal();
    document.getElementById('auth-error-msg').style.display = 'none';
    document.getElementById('auth-email').value = '';
    document.getElementById('auth-password').value = '';

    const forgotWrap = document.getElementById('auth-forgot-wrap');

    if (mode === 'login') {
        document.getElementById('auth-modal-title').innerText = '로그인';
        document.getElementById('auth-submit-btn').innerText = '로그인';
        document.getElementById('auth-toggle-text').innerText = '계정이 없으신가요?';
        document.getElementById('auth-toggle-link').innerText = '회원가입';
        if (forgotWrap) forgotWrap.style.display = 'block';
    } else {
        document.getElementById('auth-modal-title').innerText = '회원가입';
        document.getElementById('auth-submit-btn').innerText = '가입하기';
        document.getElementById('auth-toggle-text').innerText = '이미 계정이 있으신가요?';
        document.getElementById('auth-toggle-link').innerText = '로그인';
        if (forgotWrap) forgotWrap.style.display = 'none';
    }
    
    const modal = document.getElementById('auth-modal');
    modal.style.display = 'flex';
    setTimeout(() => modal.classList.add('show'), 10);
};

window.closeAuthModal = function() {
    const modal = document.getElementById('auth-modal');
    if (modal) {
        modal.classList.remove('show');
        setTimeout(() => modal.style.display = 'none', 300);
    }
};

window.toggleAuthMode = function() {
    openAuthModal(authMode === 'login' ? 'register' : 'login');
};

async function submitAuth() {
    const email = document.getElementById('auth-email').value;
    const password = document.getElementById('auth-password').value;
    const errorMsg = document.getElementById('auth-error-msg');
    
    errorMsg.style.display = 'none';
    
    if (!email || !password) {
        errorMsg.innerText = '이메일과 비밀번호를 입력해주세요.';
        errorMsg.style.display = 'block';
        return;
    }
    
    const endpoint = authMode === 'login' ? '/api/auth/login' : '/api/auth/register';
    
    try {
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        
        const data = await res.json();
        
        if (!res.ok) {
            errorMsg.innerText = data.error || '오류가 발생했습니다.';
            errorMsg.style.display = 'block';
        } else {
            closeAuthModal();
            await initAuth();
            showCustomAlert(authMode === 'register' ? '가입이 완료되었습니다.' : '로그인되었습니다.');
        }
    } catch (e) {
        errorMsg.innerText = '서버 통신 실패';
        errorMsg.style.display = 'block';
    }
}

window.logout = async function() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
        await initAuth();
        showCustomAlert('로그아웃되었습니다.');
    } catch (e) {
        console.error(e);
    }
};

async function initAuth() {
    try {
        const res = await fetch('/api/auth/me');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        window.AUTH_STATE = {
            isLoggedIn: data.isLoggedIn || false,
            email: data.email || '',
            isPaid: data.isPaid || false,
            isVerified: data.isVerified || false,
            isAdmin: data.isAdmin || false,
            displayName: data.displayName || ''
        };
        if (data.isLoggedIn) {
            restoreTempOnLogin();
        }
    } catch (e) {
        console.error('Auth state fetch failed:', e);
        window.AUTH_STATE = { isLoggedIn: false, email: '', isPaid: false, displayName: '' };
    }
    updateAuthNavUI();
    updateVerifyBanner();
}

window.closeVerifyBanner = function() {
    const banner = document.getElementById('verify-banner');
    if (banner) banner.remove();
};

function updateVerifyBanner() {
    const existing = document.getElementById('verify-banner');
    if (existing) existing.remove();
    if (window.AUTH_STATE.isAdmin) return;

    const banner = document.createElement('div');
    banner.id = 'verify-banner';

    if (!window.AUTH_STATE.isLoggedIn) {
        banner.innerHTML = `
          <span class="verify-banner-msg">이메일 주소로 간편하게 무료 회원가입이 가능합니다. 회원이 되시고 원하는 문항을 모아서 출력해보세요.</span>
          <a href="javascript:void(0)" class="verify-banner-link" onclick="window.openAuthModal('register')">무료 회원가입</a>
          <button class="verify-banner-close" onclick="closeVerifyBanner()" title="닫기">✕</button>
        `;
    } else if (!window.AUTH_STATE.isVerified) {
        const email = window.AUTH_STATE.email;
        banner.innerHTML = `
          <span class="verify-banner-msg">이메일 인증을 완료하면 모든 기능을 사용할 수 있습니다. 메일이 오지 않았다면 스팸함을 확인해주세요.</span>
          <a href="javascript:void(0)" class="verify-banner-link" onclick="resendVerifyEmail('${email.replace(/'/g, "\\'")}')">인증 메일 재발송</a>
          <button class="verify-banner-close" onclick="closeVerifyBanner()" title="닫기">✕</button>
        `;
    } else {
        return;
    }

    const stickyBars = document.getElementById('sticky-bars') || document.body;
    stickyBars.prepend(banner);
}

function updateAuthNavUI() {
    const appSection = document.getElementById('auth-app-section');
    if (!appSection) return;

    // Clear existing contents
    appSection.innerHTML = '';

    // 모바일 앱바 로그인 버튼 동기화
    const mobileLoginBtn = document.getElementById('mobile-login-btn');
    if (mobileLoginBtn) {
        if (window.AUTH_STATE && window.AUTH_STATE.isLoggedIn) {
            const name = window.AUTH_STATE.displayName || (window.AUTH_STATE.email || '').split('@')[0];
            mobileLoginBtn.textContent = name;
            mobileLoginBtn.onclick = () => openMyPage();
        } else {
            mobileLoginBtn.textContent = '로그인';
            mobileLoginBtn.onclick = () => openAuthModal('login');
        }
    }

    if (window.AUTH_STATE.isLoggedIn) {
        const email = window.AUTH_STATE.email || '';
        const displayName = window.AUTH_STATE.displayName || email.split('@')[0];

        const nameSpan = document.createElement('span');
        nameSpan.id = 'auth-display-name';
        nameSpan.textContent = displayName;
        nameSpan.title = '마이페이지';
        nameSpan.style.cssText = 'color: var(--text-muted); font-size: 0.76rem; font-weight: 500; cursor: pointer; text-decoration-line: underline; text-underline-offset: 3px; text-decoration-style: dotted; transition: color 0.2s;';
        nameSpan.addEventListener('mouseenter', () => nameSpan.style.color = 'var(--accent-cyan)');
        nameSpan.addEventListener('mouseleave', () => nameSpan.style.color = '');
        nameSpan.addEventListener('click', () => openMyPage());

        if (window.AUTH_STATE.isAdmin) {
            const adminBtn = document.createElement('button');
            adminBtn.textContent = '관리자';
            adminBtn.title = '관리자 대시보드';
            adminBtn.style.cssText = 'background: rgba(217,70,239,0.15); border: 1px solid rgba(217,70,239,0.35); color: #e879f9; padding: 0.4rem 0.9rem; border-radius: 8px; cursor: pointer; font-size: 0.78rem; font-weight: 700; backdrop-filter: blur(4px); transition: all 0.2s;';
            adminBtn.addEventListener('mouseenter', () => { adminBtn.style.background = 'rgba(217,70,239,0.28)'; });
            adminBtn.addEventListener('mouseleave', () => { adminBtn.style.background = 'rgba(217,70,239,0.15)'; });
            adminBtn.addEventListener('click', () => { window.location.href = '/admin'; });
            appSection.appendChild(nameSpan);
            appSection.appendChild(adminBtn);
        } else {
            const logoutBtn = document.createElement('button');
            logoutBtn.textContent = '\ub85c\uadf8\uc544\uc6c3';
            logoutBtn.style.cssText = 'background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: var(--text-color); padding: 0.4rem 0.7rem; border-radius: 8px; cursor: pointer; font-size: 0.78rem; font-weight: 600; backdrop-filter: blur(4px);';
            logoutBtn.addEventListener('click', () => window.logout());
            appSection.appendChild(nameSpan);
            appSection.appendChild(logoutBtn);
        }
    } else {
        const loginBtn = document.createElement('button');
        loginBtn.textContent = '\ub85c\uadf8\uc778';
        loginBtn.style.cssText = 'background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: var(--text-color); padding: 0.5rem 1.2rem; border-radius: 8px; cursor: pointer; font-size: 0.82rem; font-weight: 600; backdrop-filter: blur(4px);';
        loginBtn.addEventListener('click', () => window.openAuthModal('login'));

        const registerBtn = document.createElement('button');
        registerBtn.textContent = '\ud68c\uc6d0\uac00\uc785';
        registerBtn.style.cssText = 'background: var(--accent-cyan); border: none; color: #030712; padding: 0.5rem 1.2rem; border-radius: 8px; cursor: pointer; font-size: 0.82rem; font-weight: 700; box-shadow: 0 4px 12px rgba(6,182,212,0.3);';
        registerBtn.addEventListener('click', () => window.openAuthModal('register'));

        appSection.appendChild(loginBtn);
        appSection.appendChild(registerBtn);
    }
}

// ── 이메일 인증 재발송 ────────────────────────────────────────
window.resendVerifyEmail = async function(email) {
    try {
        const res = await fetch('/api/auth/resend_verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        showCustomAlert(res.ok ? '인증 메일을 재발송했습니다. 메일함을 확인해주세요.' : (data.error || '재발송 실패'));
    } catch(e) {
        showCustomAlert('서버 통신 실패');
    }
};

// ── 비밀번호 찾기 모달 ────────────────────────────────────────
const FORGOT_PW_MODAL_HTML = `
<div id="forgot-pw-modal" class="modal-overlay" style="display:none;">
  <div class="modal-content" style="max-width:360px;padding:2.2rem 2.2rem 1.8rem;">
    <button class="modal-close" onclick="closeForgotPasswordModal()" style="font-size:1.4rem;">&times;</button>
    <div style="text-align:center;margin-bottom:1.6rem;">
      <div style="width:44px;height:44px;background:rgba(6,182,212,0.12);border:1px solid rgba(6,182,212,0.3);border-radius:12px;display:flex;align-items:center;justify-content:center;margin:0 auto 0.9rem;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#06b6d4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
      </div>
      <h3 style="margin:0;font-size:1.1rem;font-weight:700;color:#f1f5f9;">\ube44\ubc00\ubc88\ud638 \uc7ac\uc124\uc815</h3>
    </div>
    <div id="forgot-pw-error" style="display:none;color:#f87171;font-size:0.82rem;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);padding:0.75rem 1rem;border-radius:8px;margin-bottom:1rem;"></div>
    <div id="forgot-pw-success" style="display:none;color:#10b981;font-size:0.85rem;background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25);padding:0.75rem 1rem;border-radius:8px;margin-bottom:1rem;"></div>
    <div id="forgot-pw-form">
      <div style="margin-bottom:1.2rem;">
        <label style="display:block;margin-bottom:0.4rem;font-size:0.78rem;font-weight:600;color:#94a3b8;letter-spacing:0.06em;text-transform:uppercase;">\uac00\uc785\ud55c \uc774\uba54\uc77c</label>
        <input type="email" id="forgot-pw-email"
          style="width:100%;box-sizing:border-box;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:0.75rem 1rem;font-size:0.92rem;color:#f1f5f9;outline:none;transition:border-color 0.2s;"
          placeholder="you@example.com"
          onfocus="this.style.borderColor='rgba(6,182,212,0.5)'"
          onblur="this.style.borderColor='rgba(255,255,255,0.1)'">
      </div>
      <button onclick="submitForgotPassword()"
        style="width:100%;background:linear-gradient(135deg,#06b6d4,#0891b2);border:none;border-radius:10px;padding:0.85rem;font-size:0.95rem;font-weight:700;color:#030712;cursor:pointer;box-shadow:0 4px 16px rgba(6,182,212,0.3);"
        onmouseover="this.style.transform='translateY(-1px)'" onmouseout="this.style.transform=''"
      >\uc7ac\uc124\uc815 \ub9c1\ud06c \ubc1c\uc1a1</button>
    </div>
  </div>
</div>`;

window.openForgotPasswordModal = function() {
    if (!document.getElementById('forgot-pw-modal')) {
        document.body.insertAdjacentHTML('beforeend', FORGOT_PW_MODAL_HTML);
        document.getElementById('forgot-pw-email').addEventListener('keyup', e => {
            if (e.key === 'Enter') submitForgotPassword();
        });
    }
    document.getElementById('forgot-pw-email').value = '';
    document.getElementById('forgot-pw-error').style.display = 'none';
    document.getElementById('forgot-pw-success').style.display = 'none';
    document.getElementById('forgot-pw-form').style.display = 'block';
    const modal = document.getElementById('forgot-pw-modal');
    modal.style.display = 'flex';
    setTimeout(() => modal.classList.add('show'), 10);
};

window.closeForgotPasswordModal = function() {
    const modal = document.getElementById('forgot-pw-modal');
    if (!modal) return;
    modal.classList.remove('show');
    setTimeout(() => modal.style.display = 'none', 300);
};

window.submitForgotPassword = async function() {
    const email = document.getElementById('forgot-pw-email').value.trim();
    const errorEl = document.getElementById('forgot-pw-error');
    const successEl = document.getElementById('forgot-pw-success');
    errorEl.style.display = 'none';
    successEl.style.display = 'none';
    if (!email) {
        errorEl.textContent = '\uc774\uba54\uc77c\uc744 \uc785\ub825\ud574\uc8fc\uc138\uc694.';
        errorEl.style.display = 'block';
        return;
    }
    try {
        const res = await fetch('/api/auth/forgot_password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });
        const data = await res.json();
        if (!res.ok) {
            errorEl.textContent = data.error || '\uc624\ub958\uac00 \ubc1c\uc0dd\ud588\uc2b5\ub2c8\ub2e4.';
            errorEl.style.display = 'block';
        } else {
            document.getElementById('forgot-pw-form').style.display = 'none';
            successEl.textContent = `${email}\ub85c \uc7ac\uc124\uc815 \ub9c1\ud06c\ub97c \ubc1c\uc1a1\ud588\uc2b5\ub2c8\ub2e4. \uba54\uc77c\ud568\uc744 \ud655\uc778\ud574\uc8fc\uc138\uc694. (1\uc2dc\uac04 \uc774\ub0b4 \uc720\ud6a8)`;
            successEl.style.display = 'block';
        }
    } catch(e) {
        errorEl.textContent = '\uc11c\ubc84 \ud1b5\uc2e0 \uc2e4\ud328';
        errorEl.style.display = 'block';
    }
};

// ── URL 파라미터 처리 (이메일 인증 결과) ────────────────────
function handleVerifyParams() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('verified') === '1') {
        history.replaceState(null, '', '/app');
        initAuth().then(() => showCustomAlert('이메일 인증이 완료되었습니다.'));
    } else if (params.get('verify_error') === 'invalid') {
        history.replaceState(null, '', '/app');
        showCustomAlert('유효하지 않은 인증 링크입니다.');
    } else if (params.get('verify_error') === 'expired') {
        history.replaceState(null, '', '/app');
        showCustomAlert('인증 링크가 만료되었습니다. 마이페이지에서 재발송해주세요.');
    }
}

function runAuthInit() {
    if (typeof KICE_OFFLINE !== 'undefined' && KICE_OFFLINE) return;
    injectAuthModal();
    initAuth();
    handleVerifyParams();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', runAuthInit);
} else {
    runAuthInit();
}

// ── Change Password Modal ─────────────────────────────────────
const CHANGE_PW_MODAL_HTML = `
<div id="change-pw-modal" class="modal-overlay" style="display: none;">
  <div class="modal-content" style="max-width: 360px; padding: 2.2rem 2.2rem 1.8rem;">
    <button class="modal-close" onclick="closeChangePasswordModal()" style="font-size: 1.4rem;">&times;</button>
    <div style="text-align: center; margin-bottom: 1.6rem;">
      <div style="width: 44px; height: 44px; background: rgba(6,182,212,0.12); border: 1px solid rgba(6,182,212,0.3); border-radius: 12px; display: flex; align-items: center; justify-content: center; margin: 0 auto 0.9rem;"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#06b6d4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></div>
      <h3 style="margin: 0; font-size: 1.15rem; font-weight: 700; color: #f1f5f9;">\ube44\ubc00\ubc88\ud638 \ubcc0\uacbd</h3>
    </div>
    <div id="change-pw-error" style="display: none; color: #f87171; font-size: 0.82rem; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25); padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1rem;"></div>
    <div style="margin-bottom: 1rem;">
      <label style="display: block; margin-bottom: 0.4rem; font-size: 0.78rem; font-weight: 600; color: #94a3b8; letter-spacing: 0.06em; text-transform: uppercase;">\ud604\uc7ac \ube44\ubc00\ubc88\ud638</label>
      <input type="password" id="change-pw-current"
        style="width: 100%; box-sizing: border-box; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 0.75rem 1rem; font-size: 0.92rem; color: #f1f5f9; outline: none; transition: border-color 0.2s, box-shadow 0.2s;"
        placeholder="\ud604\uc7ac \ube44\ubc00\ubc88\ud638 \uc785\ub825"
        onfocus="this.style.borderColor='rgba(6,182,212,0.5)';this.style.boxShadow='0 0 0 3px rgba(6,182,212,0.08)'"
        onblur="this.style.borderColor='rgba(255,255,255,0.1)';this.style.boxShadow='none'">
    </div>
    <div style="text-align:right;margin:-0.5rem 0 1rem;">
      <a href="javascript:void(0)" onclick="closeChangePasswordModal();openForgotPasswordModal();"
        style="font-size:0.76rem;color:#64748b;text-decoration:none;transition:color 0.2s;"
        onmouseover="this.style.color='#06b6d4'" onmouseout="this.style.color='#64748b'"
      >\ube44\ubc00\ubc88\ud638\ub97c \uc78a\uc73c\uc168\ub098\uc694?</a>
    </div>
    <div style="margin-bottom: 1rem;">
      <label style="display: block; margin-bottom: 0.4rem; font-size: 0.78rem; font-weight: 600; color: #94a3b8; letter-spacing: 0.06em; text-transform: uppercase;">\uc0c8 \ube44\ubc00\ubc88\ud638</label>
      <input type="password" id="change-pw-new"
        style="width: 100%; box-sizing: border-box; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 0.75rem 1rem; font-size: 0.92rem; color: #f1f5f9; outline: none; transition: border-color 0.2s, box-shadow 0.2s;"
        placeholder="6\uc790\ub9ac \uc774\uc0c1"
        onfocus="this.style.borderColor='rgba(6,182,212,0.5)';this.style.boxShadow='0 0 0 3px rgba(6,182,212,0.08)'"
        onblur="this.style.borderColor='rgba(255,255,255,0.1)';this.style.boxShadow='none'">
    </div>
    <div style="margin-bottom: 1.6rem;">
      <label style="display: block; margin-bottom: 0.4rem; font-size: 0.78rem; font-weight: 600; color: #94a3b8; letter-spacing: 0.06em; text-transform: uppercase;">\uc0c8 \ube44\ubc00\ubc88\ud638 \ud655\uc778</label>
      <input type="password" id="change-pw-confirm"
        style="width: 100%; box-sizing: border-box; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 0.75rem 1rem; font-size: 0.92rem; color: #f1f5f9; outline: none; transition: border-color 0.2s, box-shadow 0.2s;"
        placeholder="\ube44\ubc00\ubc88\ud638 \ub2e4\uc2dc \uc785\ub825"
        onfocus="this.style.borderColor='rgba(6,182,212,0.5)';this.style.boxShadow='0 0 0 3px rgba(6,182,212,0.08)'"
        onblur="this.style.borderColor='rgba(255,255,255,0.1)';this.style.boxShadow='none'">
    </div>
    <button onclick="submitChangePassword()"
      style="width: 100%; background: linear-gradient(135deg, #06b6d4, #0891b2); border: none; border-radius: 10px; padding: 0.85rem 1rem; font-size: 0.95rem; font-weight: 700; color: #030712; cursor: pointer; box-shadow: 0 4px 16px rgba(6,182,212,0.3);"
      onmouseover="this.style.transform='translateY(-1px)';this.style.boxShadow='0 6px 24px rgba(6,182,212,0.45)'"
      onmouseout="this.style.transform='translateY(0)';this.style.boxShadow='0 4px 16px rgba(6,182,212,0.3)'"
    >\ube44\ubc00\ubc88\ud638 \ubcc0\uacbd</button>
    
    <div style="margin-top: 1.5rem; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 1.2rem; text-align: center;">
      <button onclick="deleteAccount()" 
        style="background: none; border: none; color: #64748b; font-size: 0.8rem; cursor: pointer; text-decoration: underline; transition: color 0.2s;"
        onmouseover="this.style.color='#f87171'" onmouseout="this.style.color='#64748b'"
      >\uacc4\uc815 \uc0ad\uc81c\ud558\uae30</button>
    </div>
  </div>
</div>
`;

window.openChangePasswordModal = function() {
    if (!document.getElementById('change-pw-modal')) {
        document.body.insertAdjacentHTML('beforeend', CHANGE_PW_MODAL_HTML);
        document.getElementById('change-pw-confirm').addEventListener('keyup', e => {
            if (e.key === 'Enter') submitChangePassword();
        });
    }
    document.getElementById('change-pw-current').value = '';
    document.getElementById('change-pw-new').value = '';
    document.getElementById('change-pw-confirm').value = '';
    document.getElementById('change-pw-error').style.display = 'none';
    const modal = document.getElementById('change-pw-modal');
    modal.style.display = 'flex';
    setTimeout(() => modal.classList.add('show'), 10);
};

window.closeChangePasswordModal = function() {
    const modal = document.getElementById('change-pw-modal');
    if (!modal) return;
    modal.classList.remove('show');
    setTimeout(() => modal.style.display = 'none', 300);
};

window.submitChangePassword = async function() {
    const currentPw = document.getElementById('change-pw-current').value;
    const newPw = document.getElementById('change-pw-new').value;
    const confirmPw = document.getElementById('change-pw-confirm').value;
    const errorEl = document.getElementById('change-pw-error');
    errorEl.style.display = 'none';

    if (!currentPw) {
        errorEl.textContent = '\ud604\uc7ac \ube44\ubc00\ubc88\ud638\ub97c \uc785\ub825\ud574\uc8fc\uc138\uc694.';
        errorEl.style.display = 'block';
        return;
    }
    if (!newPw || newPw.length < 6) {
        errorEl.textContent = '\ube44\ubc00\ubc88\ud638\ub294 6\uc790\ub9ac \uc774\uc0c1\uc774\uc5b4\uc57c \ud569\ub2c8\ub2e4.';
        errorEl.style.display = 'block';
        return;
    }
    if (newPw !== confirmPw) {
        errorEl.textContent = '\ube44\ubc00\ubc88\ud638\uac00 \uc77c\uce58\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.';
        errorEl.style.display = 'block';
        return;
    }

    try {
        const res = await fetch('/api/auth/change_password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: currentPw, new_password: newPw })
        });
        const data = await res.json();
        if (!res.ok) {
            errorEl.textContent = data.error || '\uc624\ub958\uac00 \ubc1c\uc0dd\ud588\uc2b5\ub2c8\ub2e4.';
            errorEl.style.display = 'block';
        } else {
            closeChangePasswordModal();
            showCustomAlert('\ube44\ubc00\ubc88\ud638\uac00 \ubcc0\uacbd\ub418\uc5c8\uc2b5\ub2c8\ub2e4.');
        }
    } catch (e) {
        errorEl.textContent = '\uc11c\ubc84 \ud1b5\uc2e0 \uc2e4\ud328';
        errorEl.style.display = 'block';
    }
};

window.deleteAccount = async function() {
    showCustomConfirm('정말로 계정을 삭제하시겠습니까?\n모든 정보가 영구적으로 삭제되며 복구할 수 없습니다.', async () => {
        try {
            const res = await fetch('/api/auth/delete_account', { method: 'POST' });
            if (res.ok) {
                closeChangePasswordModal();
                await initAuth();
                showCustomAlert('계정이 성공적으로 삭제되었습니다.\n그동안 이용해 주셔서 감사합니다.');
            } else {
                const data = await res.json();
                showCustomAlert('삭제 실패: ' + (data.error || '알 수 없는 오류'));
            }
        } catch (e) {
            console.error(e);
            showCustomAlert('서버 통신 실패');
        }
    });
};


window.checkAuthForPreview = function() {
    if (typeof KICE_OFFLINE !== 'undefined' && KICE_OFFLINE) return true;
    if (!window.AUTH_STATE.isLoggedIn) {
        showCustomAlert(
            '해당 기능을 이용하시려면 로그인이 필요합니다.\n\n(로그인/가입 후 무료 이용 가능)',
            () => openAuthModal('login')
        );
        return false;
    }
    return true;
};

window.checkPaidForBeta = function(featureName) {
    if (typeof KICE_OFFLINE !== 'undefined' && KICE_OFFLINE) return true;
    if (!window.AUTH_STATE.isLoggedIn) {
        showCustomAlert(
            '해당 기능을 이용하시려면 로그인이 필요합니다.\n\n(로그인/가입 후 이용 가능)',
            () => openAuthModal('login')
        );
        return false;
    }
    if (!window.AUTH_STATE.isPaid) {
        showCustomAlert(`[베타 안내]\n'${featureName}' 기능은 정식 유료회원 전용입니다만,\n베타 기간 동안 무료로 제한 없이 제공합니다.\n\n※ 조만간 정식 유료화가 적용될 예정입니다.`);
        return true;
    }
    return true;
};

window.enableTitleEditing = function() {
    const titles = document.querySelectorAll('.exam-title');
    titles.forEach(t => {
        t.contentEditable = "true";
        t.textContent = "";
    });
    if (titles.length > 0) {
        const t = titles[0];
        t.focus();
        const range = document.createRange();
        range.setStart(t, 0);
        range.collapse(true);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
    }
};

// ── 오류 신고 모달 로직 ──────────────────────────────────
let reportedErrors = new Set();
let selectedErrProbs = new Set();
let selectedErrYear = '';
let selectedErrExam = '';

const yrs1 = [2014, 2015, 2016];
const yrs2 = [2017, 2018, 2019, 2020, 2021];
const yrs3 = [2022, 2023, 2024, 2025, 2026, 2027];
const yrs4 = [2028];

function getYrWrapHtml(yr) {
    return `
    <div class="yr-wrap" data-yr="${yr}">
      <button class="error-btn yr-btn">${yr}</button>
      <div class="error-split-btns" style="display:none;">
        <button class="split-btn exam-btn" data-yr="${yr}" data-exam="6모">6</button>
        <button class="split-btn exam-btn" data-yr="${yr}" data-exam="9모">9</button>
        <button class="split-btn exam-btn" data-yr="${yr}" data-exam="수능">수</button>
      </div>
    </div>
  `;
}

function initErrorReporting() {
    const group1 = document.getElementById('yr-group-1');
    const group2 = document.getElementById('yr-group-2');
    const group3 = document.getElementById('yr-group-3');
    const group4 = document.getElementById('yr-group-4');

    if (group1) group1.insertAdjacentHTML('beforeend', yrs1.map(getYrWrapHtml).join(''));
    if (group2) group2.insertAdjacentHTML('beforeend', yrs2.map(getYrWrapHtml).join(''));
    if (group3) group3.insertAdjacentHTML('beforeend', yrs3.map(getYrWrapHtml).join(''));
    if (group4) group4.insertAdjacentHTML('beforeend', yrs4.map(getYrWrapHtml).join(''));

    document.querySelectorAll('.yr-wrap').forEach(wrap => {
        const yrBtn = wrap.querySelector('.yr-btn');
        const splits = wrap.querySelector('.error-split-btns');
        if (yrBtn && splits) {
            yrBtn.onclick = () => {
                document.querySelectorAll('.error-split-btns').forEach(el => el.style.display = 'none');
                document.querySelectorAll('.yr-btn').forEach(el => { el.style.display = 'block'; });

                yrBtn.style.display = 'none';
                splits.style.display = 'flex';

                selectedErrYear = wrap.dataset.yr;
                selectedErrExam = '';
                const grid = document.getElementById('err-step-grid');
                if (grid) grid.style.display = 'none';
                document.querySelectorAll('.exam-btn').forEach(b => b.classList.remove('selected'));
            };
        }
    });

    document.querySelectorAll('.exam-btn').forEach(btn => {
        btn.onclick = () => {
            document.querySelectorAll('.exam-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            selectedErrYear = btn.dataset.yr;
            selectedErrExam = btn.dataset.exam;
            renderErrorGrid();
        };
    });
}

// Initialize on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initErrorReporting);
} else {
    initErrorReporting();
}

async function openErrorReportModal() {
    const overlay = document.getElementById('error-report-overlay');
    if (overlay) overlay.style.display = 'flex';
    try {
        const res = await fetch('/api/errors');
        if (res.ok) {
            const data = await res.json();
            reportedErrors = new Set(data.errors);
        }
    } catch (e) { }
    resetErrorModalState();
}

function closeErrorReportModal() {
    const overlay = document.getElementById('error-report-overlay');
    if (overlay) overlay.style.display = 'none';
}

function resetErrorModalState() {
    selectedErrYear = ''; selectedErrExam = '';
    document.querySelectorAll('.error-split-btns').forEach(el => el.style.display = 'none');
    document.querySelectorAll('.yr-btn').forEach(el => el.style.display = 'block');
    document.querySelectorAll('.exam-btn').forEach(b => b.classList.remove('selected'));
    const grid = document.getElementById('err-step-grid');
    if (grid) grid.style.display = 'none';
    const submitBtn = document.getElementById('err-submit-btn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = '오류 신고 제출';
    }
    selectedErrProbs.clear();
    renderErrSelectedList();
}

function renderErrSelectedList() {
    const container = document.getElementById('err-selected-list');
    if (!container) return;
    container.innerHTML = '';
    selectedErrProbs.forEach(pid => {
        const item = document.createElement('div');
        item.className = 'err-cart-item';
        const pidText = document.createTextNode(pid + ' ');
        const rmSpan = document.createElement('span');
        rmSpan.className = 'err-cart-rm';
        rmSpan.textContent = '×';
        rmSpan.addEventListener('click', () => removeErrProb(pid));
        item.appendChild(pidText);
        item.appendChild(rmSpan);
        container.appendChild(item);
    });
    const submitBtn = document.getElementById('err-submit-btn');
    if (submitBtn) submitBtn.disabled = selectedErrProbs.size === 0;
}

function removeErrProb(pid) {
    selectedErrProbs.delete(pid);
    renderErrSelectedList();
    const btn = document.querySelector(`.error-prob-btn[data-pid="${pid}"]`);
    if (btn) btn.classList.remove('selected');
}

function renderErrorGrid() {
    const y = parseInt(selectedErrYear);
    const gridContainer = document.getElementById('err-step-grid');
    if (!gridContainer) return;
    gridContainer.style.display = 'flex';
    gridContainer.innerHTML = '';

    let html = '';

    const createBlock = (label, prefixForPid, rows) => {
        let h = `<div style="display:flex; align-items:flex-start; margin-bottom:4px; gap:8px;">`;
        if (label) h += `<span style="font-size:0.75rem; color:var(--accent-cyan); font-weight:700; width:35px; flex-shrink:0; padding-top:6px;">${label}</span>`;

        h += `<div style="display:flex; flex-direction:column; gap:6px; flex:1;">`;
        for (let r of rows) {
            h += `<div class="error-grid-row">`;
            for (let i = r.start; i <= r.end; i++) {
                const numStr = i < 10 ? '0' + i : '' + i;

                let qExam = selectedErrExam === '수능' ? '수능' : '.' + selectedErrExam;
                let pid = `${selectedErrYear}${qExam}${prefixForPid}_${numStr}`;
                if (y >= 2028) pid = `${selectedErrYear}${qExam}_${numStr}`;
                else if (y >= 2022) {
                    if (prefixForPid === '') pid = `${selectedErrYear}${qExam}_${numStr}`;
                    else pid = `${selectedErrYear}${qExam}${prefixForPid}_${numStr}`;
                }

                const isRep = reportedErrors.has(pid);
                const isSel = selectedErrProbs.has(pid);
                const tooltipAttr = isRep ? `data-tooltip="${encodeURIComponent('이미 접수되어 검토 중입니다.')}"` : '';
                h += `<button class="error-prob-btn ${isSel ? 'selected' : ''} ${isRep ? 'reported tooltip-trigger' : ''}" data-pid="${pid}" ${tooltipAttr}>${numStr}</button>`;
            }
            h += `</div>`;
        }
        h += `</div></div>`;
        return h;
    };

    if (y >= 2014 && y <= 2016) {
        html += createBlock('A형', 'A', [{ start: 1, end: 13 }, { start: 14, end: 21 }, { start: 22, end: 25 }, { start: 26, end: 30 }]);
        html += createBlock('B형', 'B', [{ start: 1, end: 13 }, { start: 14, end: 21 }, { start: 22, end: 25 }, { start: 26, end: 30 }]);
    } else if (y >= 2017 && y <= 2021) {
        html += createBlock('가형', '가', [{ start: 1, end: 13 }, { start: 14, end: 21 }, { start: 22, end: 25 }, { start: 26, end: 30 }]);
        html += createBlock('나형', '나', [{ start: 1, end: 13 }, { start: 14, end: 21 }, { start: 22, end: 25 }, { start: 26, end: 30 }]);
    } else if (y >= 2022 && y <= 2027) {
        html += createBlock('공통', '', [{ start: 1, end: 8 }, { start: 9, end: 15 }, { start: 16, end: 19 }, { start: 20, end: 22 }]);
        html += createBlock('확통', '확', [{ start: 23, end: 30 }]);
        html += createBlock('미적', '미', [{ start: 23, end: 30 }]);
        html += createBlock('기하', '기', [{ start: 23, end: 30 }]);
    } else if (y >= 2028) {
        html += createBlock('통합', '', [{ start: 1, end: 13 }, { start: 14, end: 21 }, { start: 22, end: 25 }, { start: 26, end: 30 }]);
    }

    gridContainer.innerHTML = html;

    gridContainer.querySelectorAll('.error-prob-btn').forEach(btn => {
        btn.onclick = () => {
            if (btn.classList.contains('reported')) return;
            const pid = btn.dataset.pid;
            if (selectedErrProbs.has(pid)) {
                selectedErrProbs.delete(pid);
                btn.classList.remove('selected');
            } else {
                selectedErrProbs.add(pid);
                btn.classList.add('selected');
            }
            renderErrSelectedList();
        };
    });
}

async function submitErrorReport() {
    if (selectedErrProbs.size === 0) return;
    const btn = document.getElementById('err-submit-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerText = '처리 중...';
    }

    try {
        const res = await fetch('/api/errors', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ problem_ids: Array.from(selectedErrProbs) })
        });
        if (res.ok) {
            selectedErrProbs.forEach(pid => reportedErrors.add(pid));
            showCustomAlert('오류 신고가 성공적으로 접수되었습니다. 신고해주셔서 감사합니다!');
            closeErrorReportModal();
        } else {
            showCustomAlert('오류 신고 접수에 실패했습니다. (서버 오류)');
            if (btn) {
                btn.disabled = false;
                btn.innerText = '오류 신고 제출';
            }
        }
    } catch (e) {
        showCustomAlert('제출 중 네트워크 오류가 발생했습니다.');
        if (btn) {
            btn.disabled = false;
            btn.innerText = '오류 신고 제출';
        }
    }
}

// Expose modal functions
window.openErrorReportModal = openErrorReportModal;
window.closeErrorReportModal = closeErrorReportModal;
window.submitErrorReport = submitErrorReport;
window.removeErrProb = removeErrProb;


// ── 검색어 추적 ───────────────────────────────────────────────

function recordSearchQuery(query, type) {
    if (!query || (typeof KICE_OFFLINE !== 'undefined' && KICE_OFFLINE)) return;
    searchQueryLog.push({ query, type, addedCount: 0, ts: Date.now() });
    if (searchQueryLog.length > 20) searchQueryLog.shift();
}

function markQueryUsed(query) {
    const entry = [...searchQueryLog].reverse().find(e => e.query === query);
    if (entry) entry.addedCount++;
}

function getBestSearchQuery() {
    const used = searchQueryLog.filter(e => e.addedCount > 0);
    if (used.length > 0) {
        return used.sort((a, b) => b.addedCount - a.addedCount || b.ts - a.ts)[0].query;
    }
    return searchQueryLog.length > 0 ? searchQueryLog[searchQueryLog.length - 1].query : null;
}

function cartMatchesTemp() {
    if (!restoredTempIds) return false;
    const current = Array.from(cartProblemIds);
    if (current.length !== restoredTempIds.length) return false;
    return current.every((id, i) => id === restoredTempIds[i]);
}

function dismissRestoreBanner() {
    const banner = document.getElementById('cart-restore-banner');
    if (banner) banner.style.display = 'none';
}

function onRestoreBannerClick() {
    showCustomConfirm(
        '복원된 문항을 지우고 새로 시작하시겠습니까?',
        async () => {
            cartProblemIds.clear();
            restoredTempIds = null;
            updateCartUI();
            dismissRestoreBanner();
            await fetch('/api/sets/restore', { method: 'DELETE' });
        },
        { confirmText: '새로 시작', dangerous: true }
    );
}

async function restoreTempOnLogin() {
    if (typeof KICE_OFFLINE !== 'undefined' && KICE_OFFLINE) return;
    try {
        const res = await fetch('/api/sets/restore');
        const data = await res.json();
        if (!data.has_temp || !data.problem_ids || data.problem_ids.length === 0) return;
        data.problem_ids.forEach(id => cartProblemIds.add(id));
        restoredTempIds = [...data.problem_ids];
        updateCartUI();
        const banner = document.getElementById('cart-restore-banner');
        const msg = document.getElementById('cart-restore-msg');
        if (banner && msg) {
            msg.textContent = `이전 작업 복원됨 · ${data.problem_ids.length}문항`;
            banner.style.display = 'flex';
        }
    } catch(e) {}
}


// ── 문항지 세트 뷰 ────────────────────────────────────────────

function showSetsView() {
    const cartView = document.getElementById('cart-view');
    const setsView = document.getElementById('sets-view');
    if (cartView) cartView.style.display = 'none';
    if (setsView) { setsView.style.display = 'flex'; loadMySets(); }
}

function showCartView() {
    const cartView = document.getElementById('cart-view');
    const setsView = document.getElementById('sets-view');
    if (setsView) setsView.style.display = 'none';
    if (cartView) cartView.style.display = 'flex';
}

async function loadMySets() {
    const container = document.getElementById('sets-list-container');
    if (!container) return;
    container.innerHTML = '<div style="padding:1rem; color:var(--text-muted); font-size:0.82rem;">불러오는 중...</div>';
    try {
        const res = await fetch('/api/sets/my');
        const { sets } = await res.json();
        renderSetsList(sets, container);
    } catch(e) {
        container.innerHTML = '<div style="padding:1rem; color:#f87171; font-size:0.82rem;">불러오기 실패</div>';
    }
}

function renderSetsList(sets, container) {
    container.innerHTML = '';
    if (!sets || sets.length === 0) {
        container.innerHTML = '<div style="padding:1.5rem 0.5rem; text-align:center; color:var(--text-muted); font-size:0.82rem;">저장된 문항지가 없습니다.</div>';
        return;
    }
    sets.forEach(set => {
        const item = document.createElement('div');
        item.className = 'set-item';
        item.dataset.setId = set.id;
        const favClass = set.is_favorite ? 'set-fav-btn active' : 'set-fav-btn';
        const tempBadge = set.status === 'temp' ? '<span class="badge-temp">임시</span>' : '';
        item.innerHTML = `
            <div class="set-item-main" onclick="loadSetToCart(${set.id})" title="${set.problem_count}문항">
                <div class="set-item-title">${tempBadge}${escapeHtmlStr(set.title)}</div>
                <div class="set-item-meta">${set.created_at}</div>
            </div>
            <button class="${favClass}" onclick="toggleFavoriteSet(event,${set.id})" title="즐겨찾기">★</button>
            <button class="set-del-btn" onclick="deleteSetItem(event,${set.id})" title="삭제">×</button>
        `;
        container.appendChild(item);
    });
}

function escapeHtmlStr(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function loadSetToCart(setId) {
    const doLoad = async () => {
        try {
            const res = await fetch(`/api/sets/${setId}`);
            const set = await res.json();
            cartProblemIds.clear();
            set.problem_ids.forEach(id => cartProblemIds.add(id));
            restoredTempIds = [...set.problem_ids];
            cartRestoreWarningShown = true;
            updateCartUI();
            showCartView();
        } catch(e) {
            showCustomAlert('불러오기 실패');
        }
    };
    if (cartProblemIds.size > 0 && !cartMatchesTemp()) {
        showCustomConfirm(
            `현재 담긴 ${cartProblemIds.size}문항이 사라집니다.\n교체하시겠습니까?`,
            doLoad,
            { confirmText: '교체', dangerous: true }
        );
    } else {
        await doLoad();
    }
}

async function toggleFavoriteSet(event, setId) {
    event.stopPropagation();
    try {
        const res = await fetch(`/api/sets/${setId}/favorite`, { method: 'PATCH' });
        const { is_favorite } = await res.json();
        event.target.classList.toggle('active', is_favorite === 1);
        loadMySets();
    } catch(e) {}
}

function deleteSetItem(event, setId) {
    event.stopPropagation();
    showCustomConfirm(
        '이 문항지를 삭제하시겠습니까?',
        async () => {
            try {
                await fetch(`/api/sets/${setId}`, { method: 'DELETE' });
                const el = document.querySelector(`.set-item[data-set-id="${setId}"]`);
                if (el) el.remove();
            } catch(e) { showCustomAlert('삭제 실패'); }
        },
        { confirmText: '삭제', dangerous: true }
    );
}

// [작성된 문항지] 버튼 이벤트
document.addEventListener('DOMContentLoaded', () => {
    const btnMySets = document.getElementById('btn-my-sets');
    if (!btnMySets) return;
    btnMySets.addEventListener('click', async () => {
        if (!window.AUTH_STATE || !window.AUTH_STATE.isLoggedIn) {
            showCustomAlert('로그인 후 이용 가능합니다.', () => openAuthModal('login'));
            return;
        }
        const hasItems = cartProblemIds.size > 0;
        const alreadySaved = cartMatchesTemp();
        if (hasItems && !alreadySaved) {
            showCustomConfirm(
                '현재 담은 문항을 저장하시겠습니까?',
                async () => {
                    const ids = Array.from(cartProblemIds);
                    let autoTitle = '문항 세트';
                    try {
                        const tr = await fetch(`/api/sets/auto_title?ids=${encodeURIComponent(ids.join(','))}`);
                        autoTitle = (await tr.json()).title || autoTitle;
                    } catch(e) {}
                    showCustomPrompt('저장할 이름을 입력하세요', autoTitle, async (inputTitle) => {
                        if (inputTitle === null) return;
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
                        showSetsView();
                    });
                },
                { confirmText: '저장', confirmStyle: 'safe', onCancel: () => showSetsView() }
            );
        } else {
            showSetsView();
        }
    });
});

// window 전역 노출
window.showSetsView = showSetsView;
window.showCartView = showCartView;
window.loadSetToCart = loadSetToCart;
window.toggleFavoriteSet = toggleFavoriteSet;
window.deleteSetItem = deleteSetItem;
window.dismissRestoreBanner = dismissRestoreBanner;
window.onRestoreBannerClick = onRestoreBannerClick;


// ── 마이페이지 ────────────────────────────────────────────────

function openMyPage() {
    const modal = document.getElementById('mypage-modal');
    if (!modal) return;
    // 사용자 정보 채우기
    const email = window.AUTH_STATE?.email || '';
    const displayName = document.getElementById('auth-display-name')?.textContent || email.split('@')[0];
    const usernameEl = document.getElementById('mypage-username');
    if (usernameEl) usernameEl.textContent = displayName || email.split('@')[0];
    const emailEl = document.getElementById('mypage-email');
    if (emailEl) emailEl.textContent = email;
    const verifyStatusEl = document.getElementById('mypage-verify-status');
    if (verifyStatusEl) verifyStatusEl.innerHTML = '';
    const nameInput = document.getElementById('display-name-input');
    if (nameInput) nameInput.value = displayName !== email.split('@')[0] ? displayName : '';
    const hintEl = document.getElementById('display-name-hint');
    if (hintEl) hintEl.textContent = `현재: ${displayName}`;
    // 첫 번째 탭(내 문항지) 활성화
    document.querySelectorAll('.mypage-tab').forEach(b => b.classList.remove('active'));
    const firstTab = document.querySelector('.mypage-tab[data-tab="my-sets-tab"]');
    if (firstTab) firstTab.classList.add('active');
    document.querySelectorAll('.mypage-tab-content').forEach(c => c.style.display = 'none');
    const setsTab = document.getElementById('my-sets-tab');
    if (setsTab) setsTab.style.display = 'block';
    loadMypageSets();
    modal.style.display = 'flex';
    setTimeout(() => modal.classList.add('show'), 10);
}

function closeMyPage() {
    const modal = document.getElementById('mypage-modal');
    if (!modal) return;
    modal.classList.remove('show');
    setTimeout(() => { if (!modal.classList.contains('show')) modal.style.display = 'none'; }, 250);
}

function openChangePwModal() {
    window.openChangePasswordModal && window.openChangePasswordModal();
}

function confirmDeleteAccount() {
    window.deleteAccount && window.deleteAccount();
}

function switchMypageTab(btn) {
    document.querySelectorAll('.mypage-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.mypage-tab-content').forEach(c => c.style.display = 'none');
    const target = document.getElementById(btn.dataset.tab);
    if (target) target.style.display = 'block';
    if (btn.dataset.tab === 'my-sets-tab') loadMypageSets();
}

async function loadMypageSets() {
    const container = document.getElementById('mypage-sets-list');
    if (!container) return;
    container.innerHTML = '<div style="padding:1rem; color:var(--text-muted); font-size:0.82rem;">불러오는 중...</div>';
    try {
        const res = await fetch('/api/sets/my');
        const { sets } = await res.json();
        renderSetsList(sets, container);
        // 마이페이지에서 loadSetToCart 호출 시 모달도 닫기
        container.querySelectorAll('.set-item-main').forEach(el => {
            const setId = el.closest('.set-item')?.dataset.setId;
            if (setId) {
                el.onclick = async () => {
                    closeMyPage();
                    await loadSetToCart(parseInt(setId));
                    // 장바구니 열기
                    if (problemCart && !problemCart.classList.contains('open')) {
                        problemCart.classList.add('open');
                    }
                };
            }
        });
    } catch(e) {
        container.innerHTML = '<div style="padding:1rem; color:#f87171; font-size:0.82rem;">불러오기 실패</div>';
    }
}

async function saveDisplayName() {
    const input = document.getElementById('display-name-input');
    if (!input) return;
    const name = input.value.trim();
    try {
        const res = await fetch('/api/users/display_name', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: name })
        });
        if (res.ok) {
            const hintEl = document.getElementById('display-name-hint');
            if (hintEl) hintEl.textContent = `저장됨: ${name || '(이메일 앞부분 사용)'}`;
            // 우상단 표시 업데이트
            const displayNameEl = document.getElementById('auth-display-name');
            if (displayNameEl && window.AUTH_STATE) {
                displayNameEl.textContent = name || window.AUTH_STATE.email.split('@')[0];
            }
            const usernameEl = document.getElementById('mypage-username');
            if (usernameEl) usernameEl.textContent = name || window.AUTH_STATE?.email.split('@')[0];
        }
    } catch(e) { showCustomAlert('저장 실패'); }
}

// 모달 외부 클릭 닫기
document.addEventListener('click', (e) => {
    const modal = document.getElementById('mypage-modal');
    if (modal && e.target === modal) closeMyPage();
});

// window 전역 노출
window.openMyPage = openMyPage;
window.closeMyPage = closeMyPage;
window.openChangePwModal = openChangePwModal;
window.confirmDeleteAccount = confirmDeleteAccount;
window.switchMypageTab = switchMypageTab;
window.saveDisplayName = saveDisplayName;
