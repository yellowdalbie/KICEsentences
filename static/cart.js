// cart.js
// Handles Problem Cart and Print Preview Modal logic

const cartProblemIds = new Set();
const cartItemsContainer = document.getElementById('cart-items-container');
const cartBadge = document.getElementById('cart-badge');
const cartEmptyMsg = document.getElementById('cart-empty-msg');
const cartToggleBtn = document.getElementById('cart-toggle-btn');
const problemCart = document.getElementById('problem-cart');
const cartClearBtn = document.getElementById('cart-clear-btn');
const cartPreviewBtn = document.getElementById('cart-preview-btn');

// Print Modal elements
const printModal = document.getElementById('print-preview-modal');
const printModalBody = document.getElementById('print-preview-body');
const sidebarOrderList = document.getElementById('sidebar-order-list');

// Module-level preview state (enables drag-and-drop reorder without re-fetching)
let _previewLoadedItems = [];
let _previewAnswerOpt   = 'none';
let _previewExpOpt      = 'none';
let _dragSrcIdx         = null;

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
        let top  = rect.bottom + 6;
        let left = rect.left;
        if (top + tooltip.offsetHeight > window.innerHeight) {
            top = rect.top - tooltip.offsetHeight - 6;
        }
        if (left + tooltip.offsetWidth > window.innerWidth) {
            left = window.innerWidth - tooltip.offsetWidth - 8;
        }
        tooltip.style.top  = Math.max(4, top) + 'px';
        tooltip.style.left = Math.max(4, left) + 'px';
    });
}

function hideCartThumbTooltip() {
    if (_cartThumbTooltipEl) _cartThumbTooltipEl.style.display = 'none';
}

// ── 드래그 삽입 위치 표시 초기화 ──
function clearDragInsertIndicators() {
    document.querySelectorAll('.sidebar-item').forEach(el => {
        el.classList.remove('drag-insert-before', 'drag-insert-after-prev');
    });
}

// Toggle cart slide
cartToggleBtn.addEventListener('click', () => {
    problemCart.classList.toggle('open');
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
cartClearBtn.addEventListener('click', () => {
    cartProblemIds.clear();
    updateCartUI();
});

// Print Preview Logic
cartPreviewBtn.addEventListener('click', () => {
    if (cartProblemIds.size === 0) {
        showCustomAlert("장바구니가 비어 있습니다.");
        return;
    }

    openPrintPreview();
});

async function openPrintPreview() {
    printModalBody.innerHTML = '<div style="display:flex; justify-content:center; padding:3rem;"><div class="loader">이미지 및 정답을 불러오는 중...</div></div>';
    printModal.style.display = 'flex';
    document.body.style.overflow = 'hidden'; // Prevent background scrolling

    // Slide down the cart to avoid overlapping
    problemCart.classList.remove('open');

    const ids = Array.from(cartProblemIds);
    // Sort by Year and Problem No
    ids.sort();

    _previewAnswerOpt = document.getElementById('answer-display-opt').value;
    _previewExpOpt    = document.getElementById('explanation-display-opt').value;

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
                src:    `/thumbnail/${pid}`,
                isLong,
                answer: answers[pid] || '',
                steps:  stepsData[pid] || []
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

// ── 기능 2: 사이드바 렌더링 + 드래그앤드롭 ──
function renderSidebar() {
    sidebarOrderList.innerHTML = '';

    _previewLoadedItems.forEach((item, idx) => {
        const li = document.createElement('li');
        li.className = 'sidebar-item';
        li.draggable = true;
        li.dataset.idx = idx;
        li.innerHTML = `
            <span class="sidebar-item-num">${idx + 1}</span>
            <span class="sidebar-item-pid">${item.pid}</span>
        `;

        li.addEventListener('dragstart', (e) => {
            _dragSrcIdx = idx;
            li.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        });

        li.addEventListener('dragend', () => {
            li.classList.remove('dragging');
            clearDragInsertIndicators();
        });

        li.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            clearDragInsertIndicators();
            // 타겟 아이템 위쪽 경계 강조
            li.classList.add('drag-insert-before');
            // 타겟 바로 위 아이템 아래쪽 경계 강조
            const prevSibling = li.previousElementSibling;
            if (prevSibling && prevSibling.classList.contains('sidebar-item')) {
                prevSibling.classList.add('drag-insert-after-prev');
            }
        });

        li.addEventListener('dragleave', () => {
            clearDragInsertIndicators();
        });

        li.addEventListener('drop', (e) => {
            e.preventDefault();
            if (_dragSrcIdx === null || _dragSrcIdx === idx) {
                _dragSrcIdx = null;
                return;
            }

            // 순서 재배열
            const moved = _previewLoadedItems.splice(_dragSrcIdx, 1)[0];
            _previewLoadedItems.splice(idx, 0, moved);
            _dragSrcIdx = null;

            // 사이드바 + 페이지 재렌더링
            renderSidebar();
            renderPreviewPages();
        });

        sidebarOrderList.appendChild(li);
    });
}

// ── 페이지 렌더링 (순서 변경 시 재호출) ──
async function renderPreviewPages() {
    const items      = _previewLoadedItems;
    const answerOpt  = _previewAnswerOpt;
    const expOpt     = _previewExpOpt;

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
        let tableHtml = `<div style="text-align:center; font-size:1.1rem; font-weight:bold; margin-bottom:10px; border:2px solid black; padding:4px;">정답표</div>`;
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
                        <span class="exam-title" contenteditable="true">2028학년도 대학수학능력시험 대비 문제지</span>
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
                { left: '$',  right: '$',  display: false }
            ]
        });
    }
}

// ── 해설 아이템 HTML 생성 헬퍼 ──
function buildExpItemHtml(item) {
    const stepsHtml = item.steps.map(step => `
        <div class="csat-exp-step">
            <div class="csat-exp-step-title">Step ${step.step_number}${step.step_title ? ' — ' + step.step_title : ''}</div>
            <div class="csat-exp-step-body">${step.explanation_html}</div>
        </div>
    `).join('');

    const ansHtml = item.answer
        ? `<span class="csat-exp-answer">${item.answer}</span>`
        : '';

    return `
        <div class="csat-exp-item-header">
            <div class="csat-exp-item-header-left">
                <span class="csat-num-box">${item.examNumber}</span>
                <span class="csat-db-id-tag">${item.pid}</span>
            </div>
            ${ansHtml}
        </div>
        <div class="csat-exp-item-steps">${stepsHtml}</div>
    `;
}

// ── 해설지 페이지 배열 생성 (DOM 측정 기반 2단 흐름) ──
async function buildExplanationPages(expItems, problemPageCount) {
    // 1단계: 측정용 컨테이너 준비 (csat-col 실효 너비와 동일하게)
    const measureContainer = document.createElement('div');
    measureContainer.style.cssText =
        'position:absolute; left:-9999px; top:0; visibility:hidden; ' +
        'width:calc((210mm - 30mm - 21px) / 2); overflow:visible;';
    document.body.appendChild(measureContainer);

    // 2단계: 각 해설 아이템 DOM 생성 및 KaTeX 렌더링
    const measuredItems = [];
    for (const item of expItems) {
        const el = document.createElement('div');
        el.className = 'csat-exp-item';
        el.innerHTML = buildExpItemHtml(item);
        measureContainer.appendChild(el);
        if (window.renderMathInElement) {
            renderMathInElement(el, {
                delimiters: [
                    { left: '$$', right: '$$', display: true },
                    { left: '$',  right: '$',  display: false }
                ]
            });
        }
        measuredItems.push({ item, el });
    }

    // 3단계: 브라우저 레이아웃 완료 후 기준 높이 측정
    await new Promise(resolve => requestAnimationFrame(resolve));

    const tempPage = document.createElement('div');
    tempPage.className = 'csat-page';
    tempPage.style.cssText = 'position:absolute; left:-9999px; visibility:hidden;';
    tempPage.innerHTML = `
        <div class="csat-header-page1">
            <div class="h1-top"></div>
            <div class="h1-main-wrapper"></div>
            <div class="h1-divider"></div>
        </div>
        <div class="csat-footer"></div>`;
    document.body.appendChild(tempPage);
    await new Promise(resolve => requestAnimationFrame(resolve));

    const headerHeight  = tempPage.querySelector('.csat-header-page1').offsetHeight;
    const footerHeight  = tempPage.querySelector('.csat-footer').offsetHeight;
    const pageHeight    = tempPage.offsetHeight;
    const usableColHeightFirst  = pageHeight - headerHeight - footerHeight - 20;
    const usableColHeightNormal = pageHeight - 80 - footerHeight - 20;
    tempPage.remove();

    // 각 아이템 높이 기록
    for (const { item, el } of measuredItems) {
        item.measuredHeight = el.offsetHeight + 12;
    }

    measureContainer.remove();

    // 4단계: 배치 알고리즘
    const expPagesList = [];
    let curPage = { isFirst: true, cols: [{ items: [], usedHeight: 0 }, { items: [], usedHeight: 0 }] };
    expPagesList.push(curPage);
    let colIdx = 0;

    for (const { item } of measuredItems) {
        const colLimit = curPage.isFirst ? usableColHeightFirst : usableColHeightNormal;
        if (curPage.cols[colIdx].usedHeight + item.measuredHeight > colLimit) {
            colIdx++;
            if (colIdx > 1) {
                curPage = { isFirst: false, cols: [{ items: [], usedHeight: 0 }, { items: [], usedHeight: 0 }] };
                expPagesList.push(curPage);
                colIdx = 0;
            }
        }
        curPage.cols[colIdx].items.push(item);
        curPage.cols[colIdx].usedHeight += item.measuredHeight;
    }

    // 5단계: 해설지 DOM 렌더링
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
                        <span class="exam-title" contenteditable="true">2028학년도 대학수학능력시험 대비 해설지</span>
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

            col.items.forEach(item => {
                const el = document.createElement('div');
                el.className = 'csat-exp-item';
                el.innerHTML = buildExpItemHtml(item);
                colDiv.appendChild(el);
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

function closePrintPreview() {
    printModal.style.display = 'none';
    document.body.style.overflow = ''; // Restore background scrolling
    printModalBody.innerHTML = ''; // clear memory
    // 모듈 변수 초기화
    _previewLoadedItems = [];
}

// Custom Alert Functions
function showCustomAlert(message) {
    const modal = document.getElementById('custom-alert-modal');
    const msgEl = document.getElementById('custom-alert-message');
    if (!modal || !msgEl) return;

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
    }, 300); // Wait for transition
}

// Global exposure for index.html calls
window.showCustomAlert = showCustomAlert;
window.closeCustomAlert = closeCustomAlert;

// Initial UI setup
updateCartUI();
