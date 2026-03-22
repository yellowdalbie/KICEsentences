// cart.js
// Handles Problem Cart and Print Preview Modal logic

const cartProblemIds = new Set();
const cartItemsContainer = document.getElementById('cart-items-container');
const cartBadge = document.getElementById('cart-badge');
const cartEmptyMsg = document.getElementById('cart-empty-msg');
const cartToggleBtn = document.getElementById('cart-toggle-btn');
const problemCart = document.getElementById('problem-cart');
const cartPreviewBtn = document.getElementById('cart-preview-btn');

// Print Modal elements
const printModal = document.getElementById('print-preview-modal');
const printModalBody = document.getElementById('print-preview-body');
const sidebarOrderList = document.getElementById('sidebar-order-list');

// Module-level preview state
let _previewLoadedItems = [];
let _previewAnswerOpt = 'none';
let _previewExpOpt = 'none';
let _selectedSidebarIdx = null;

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

// Toggle cart slide
cartToggleBtn.addEventListener('click', () => {
    problemCart.classList.toggle('open');
    // 사이드바 닫힐 때 남아있는 썸네일 툴팁 제거
    if (!problemCart.classList.contains('open')) hideCartThumbTooltip();
});

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
            tag.innerHTML = `
                <span>${pid}</span>
                <span class="cart-item-remove" title="제거">×</span>
            `;

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
}

function toggleCartItem(problemId) {
    if (!problemId) return;
    const strId = String(problemId);

    if (cartProblemIds.has(strId)) {
        cartProblemIds.delete(strId);
    } else {
        cartProblemIds.add(strId);
        // Auto-open cart if it's the first item added
        if (cartProblemIds.size === 1 && !problemCart.classList.contains('open')) {
            problemCart.classList.add('open');
        }
    }

    updateCartUI();
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
cartPreviewBtn.addEventListener('click', () => {
    if (cartProblemIds.size === 0) {
        showCustomAlert("장바구니가 비어 있습니다.");
        return;
    }

    if (!checkAuthForPreview()) return;

    openPrintPreview();
});

async function openPrintPreview() {
    printModalBody.innerHTML = '<div style="display:flex; justify-content:center; padding:3rem;"><div class="loader">이미지 및 정답을 불러오는 중...</div></div>';
    printModal.style.display = 'flex';
    document.body.style.overflow = 'hidden'; // Prevent background scrolling

    // Hide auth buttons to avoid overlap with print preview
    const authSection = document.getElementById('auth-app-section');
    if (authSection) authSection.style.display = 'none';

    // Slide down the cart to avoid overlapping
    problemCart.classList.remove('open');

    const ids = Array.from(cartProblemIds);
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
        printModalBody.innerHTML = `<p class="placeholder-text" style="color:red;">오류가 발생했습니다: ${e.message}</p>`;
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
                    ansHtml = `<div class="csat-inline-answer">${item.answer}</div>`;
                }
                let extraClass = item.isLong ? ' is-long' : '';
                colDiv.innerHTML += `
                    <div class="csat-item-container${extraClass}">
                        <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom: 5px;">
                            <div>
                                <div class="csat-num-box">${item.examNumber}</div>
                                <div class="csat-db-id-tag">${item.pid}</div>
                            </div>
                            ${ansHtml}
                        </div>
                        <img src="${item.src}" class="csat-prob-img" alt="${item.pid}" />
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

        // 현재 단에 이미 내용이 있고 다음 단에 통째로 들어갈 수 있으면 이동
        if (colUsed() > 0 && fullH <= usableNormal) {
            nextCol();
            addUnit(buildExpItemHtml(item), fullH);
            continue;
        }

        // 단 하나에도 통째로 들어가지 않으면 step 단위로 분할하여 배치
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

    if (target === 'explanation-display-opt' && val === 'separate') {
        if (!checkPaidForBeta("해설 작성")) return;
    }

    document.querySelectorAll(`.print-pill[data-target="${target}"]`).forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(target).value = val;
    openPrintPreview();
}

function closePrintPreview() {
    printModal.style.display = 'none';
    document.body.style.overflow = ''; // Restore background scrolling
    printModalBody.innerHTML = ''; // clear memory

    // Restore auth buttons
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

function showCustomConfirm(message, onConfirm) {
    const modal = document.getElementById('custom-confirm-modal');
    const msgEl = document.getElementById('custom-confirm-message');
    if (!modal || !msgEl) return;

    _customConfirmCallback = onConfirm || null;
    msgEl.innerHTML = message.replace(/\n/g, '<br>');
    modal.style.display = 'flex';

    setTimeout(() => {
        modal.classList.add('show');
    }, 10);
}

function closeCustomConfirm(isConfirmed) {
    const modal = document.getElementById('custom-confirm-modal');
    if (!modal) return;

    modal.classList.remove('show');
    setTimeout(() => {
        modal.style.display = 'none';
        if (isConfirmed && typeof _customConfirmCallback === 'function') {
            _customConfirmCallback();
        }
        _customConfirmCallback = null;
    }, 300);
}

window.showCustomConfirm = showCustomConfirm;
window.closeCustomConfirm = closeCustomConfirm;

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
      style="width: 100%; background: linear-gradient(135deg, #06b6d4, #0891b2); border: none; border-radius: 10px; padding: 0.85rem 1rem; font-size: 0.95rem; font-weight: 700; color: #030712; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 16px rgba(6,182,212,0.3); margin-bottom: 1.2rem;"
      onmouseover="this.style.transform='translateY(-1px)';this.style.boxShadow='0 6px 24px rgba(6,182,212,0.45)'"
      onmouseout="this.style.transform='translateY(0)';this.style.boxShadow='0 4px 16px rgba(6,182,212,0.3)'"
    >\ub85c\uadf8\uc778</button>

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
    
    if (mode === 'login') {
        document.getElementById('auth-modal-title').innerText = '로그인';
        document.getElementById('auth-submit-btn').innerText = '로그인';
        document.getElementById('auth-toggle-text').innerText = '계정이 없으신가요?';
        document.getElementById('auth-toggle-link').innerText = '회원가입';
    } else {
        document.getElementById('auth-modal-title').innerText = '회원가입';
        document.getElementById('auth-submit-btn').innerText = '가입하기';
        document.getElementById('auth-toggle-text').innerText = '이미 계정이 있으신가요?';
        document.getElementById('auth-toggle-link').innerText = '로그인';
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
            await initAuth(); // Refresh session state
            showCustomAlert(authMode === 'login' ? '로그인되었습니다.' : '가입이 완료되었습니다.');
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
            isPaid: data.isPaid || false
        };
    } catch (e) {
        console.error('Auth state fetch failed:', e);
        window.AUTH_STATE = { isLoggedIn: false, email: '', isPaid: false };
    }
    updateAuthNavUI();
}

function updateAuthNavUI() {
    const appSection = document.getElementById('auth-app-section');
    if (!appSection) return;
    
    // Clear existing contents
    appSection.innerHTML = '';
    
    if (window.AUTH_STATE.isLoggedIn) {
        const username = (window.AUTH_STATE.email || '').split('@')[0];
        
        const emailSpan = document.createElement('span');
        emailSpan.textContent = username;
        emailSpan.title = '\ube44\ubc00\ubc88\ud638 \ubcc0\uacbd';
        emailSpan.style.cssText = 'color: var(--text-muted); font-size: 0.76rem; font-weight: 500; cursor: pointer; text-decoration-line: underline; text-underline-offset: 3px; text-decoration-style: dotted; transition: color 0.2s;';
        emailSpan.addEventListener('mouseenter', () => emailSpan.style.color = 'var(--accent-cyan)');
        emailSpan.addEventListener('mouseleave', () => emailSpan.style.color = '');
        emailSpan.addEventListener('click', () => window.openChangePasswordModal());
        
        const logoutBtn = document.createElement('button');
        logoutBtn.textContent = '\ub85c\uadf8\uc544\uc6c3';
        logoutBtn.style.cssText = 'background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: var(--text-color); padding: 0.4rem 0.7rem; border-radius: 8px; cursor: pointer; font-size: 0.78rem; font-weight: 600; backdrop-filter: blur(4px);';
        logoutBtn.addEventListener('click', () => window.logout());
        
        appSection.appendChild(emailSpan);
        appSection.appendChild(logoutBtn);
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

function runAuthInit() {
    injectAuthModal();
    initAuth();
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
    const newPw = document.getElementById('change-pw-new').value;
    const confirmPw = document.getElementById('change-pw-confirm').value;
    const errorEl = document.getElementById('change-pw-error');
    errorEl.style.display = 'none';

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
            body: JSON.stringify({ new_password: newPw })
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
    if (!window.checkPaidForBeta("타이틀 수정")) return;
    const titles = document.querySelectorAll('.exam-title');
    titles.forEach(t => {
        t.contentEditable = "true";
        t.style.color = "gray";
    });
    if (titles.length > 0) titles[0].focus();
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
        container.innerHTML += `<div class="err-cart-item">${pid} <span class="err-cart-rm" onclick="removeErrProb('${pid}')">×</span></div>`;
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
                h += `<button class="error-prob-btn ${isSel ? 'selected' : ''}" data-pid="${pid}" ${isRep ? 'disabled title="이미 접수됨"' : ''}>${numStr}</button>`;
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
