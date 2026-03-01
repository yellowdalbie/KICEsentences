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
    // 1. Sort inherently by Year and Problem No (String sorting works well for KICE IDs usually, e.g. 2025.6모_01 < 2025.6모_02)
    ids.sort();

    const answerOpt      = document.getElementById('answer-display-opt').value;
    const explanationOpt = document.getElementById('explanation-display-opt').value;

    try {
        // 2. Fetch Answers
        const res = await fetch('/api/problem_answers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ problem_ids: ids })
        });
        const ansData = await res.json();
        const answers = ansData.answers || {};

        // 3. Fetch explanation steps (separate 옵션일 때만)
        let stepsData = {};
        if (explanationOpt === 'separate') {
            const expRes = await fetch('/api/problem_steps_bulk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ problem_ids: ids })
            });
            const expData = await expRes.json();
            stepsData = expData.steps || {};
        }

        // 4. Measure Images
        const loadedItems = [];
        for (const pid of ids) {
            const imgInfo = await loadAndMeasureImage(`/thumbnail/${pid}`);
            // Determine if long: If aspect ratio (height/width) is > 1.0 (approximating more than half a page high)
            const isLong = (imgInfo.height / imgInfo.width) > 1.0;
            loadedItems.push({
                pid,
                src:    `/thumbnail/${pid}`,
                isLong,
                answer: answers[pid] || '',
                steps:  stepsData[pid] || []
            });
        }

        // 4. Flow Algorithm
        const pages = [];
        let currentPage = { cols: [[], []] }; // A page has 2 columns
        pages.push(currentPage);

        let activeColIdx = 0; // 0 for left, 1 for right

        loadedItems.forEach((item, index) => {
            item.examNumber = index + 1; // 1-based index

            if (item.isLong) {
                // Needs a full column. If current active column has items, jump to next column block.
                if (currentPage.cols[activeColIdx].length > 0) {
                    activeColIdx++;
                    if (activeColIdx > 1) {
                        // Create new page
                        currentPage = { cols: [[], []] };
                        pages.push(currentPage);
                        activeColIdx = 0;
                    }
                }
                currentPage.cols[activeColIdx].push(item);
                // After placing a long item, the column is full. Move to next.
                activeColIdx++;
                if (activeColIdx > 1) {
                    currentPage = { cols: [[], []] };
                    pages.push(currentPage);
                    activeColIdx = 0;
                }
            } else {
                // Short item. Max 2 per column.
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

        // Clean up empty pages
        if (pages.length > 0 && pages[pages.length - 1].cols[0].length === 0 && pages[pages.length - 1].cols[1].length === 0) {
            pages.pop();
        }

        if (answerOpt === 'end') {
            let tableHtml = `<div style="text-align:center; font-size:1.1rem; font-weight:bold; margin-bottom:10px; border:2px solid black; padding:4px;">정답표</div>`;
            const colsPerBlock = 5;
            for (let i = 0; i < loadedItems.length; i += colsPerBlock) {
                const chunk = loadedItems.slice(i, i + colsPerBlock);
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

        // 6. Build explanation pages (separate 옵션일 때만)
        let expPages = [];
        if (explanationOpt === 'separate') {
            const expItems = loadedItems
                .filter(item => item.steps && item.steps.length > 0)
                .map(item => ({ pid: item.pid, examNumber: item.examNumber, steps: item.steps, answer: item.answer }));
            if (expItems.length > 0) {
                expPages = await buildExplanationPages(expItems, pages.length);
            }
        }
        const totalPageCount = pages.length + expPages.length;

        // 5. Render HTML
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

                // Add vertical divider if it's the first column
                if (cIdx === 0) {
                    const vLine = document.createElement('div');
                    vLine.className = 'csat-vline';
                    colsDiv.appendChild(vLine);
                }
            });

            pageDiv.appendChild(colsDiv);

            // Append Footer
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

        // 전체 KaTeX 렌더링 (문제지 + 해설지)
        if (window.renderMathInElement) {
            renderMathInElement(printModalBody, {
                delimiters: [
                    { left: '$$', right: '$$', display: true },
                    { left: '$',  right: '$',  display: false }
                ]
            });
        }

    } catch (e) {
        console.error(e);
        printModalBody.innerHTML = `<p class="placeholder-text" style="color:red;">오류가 발생했습니다: ${e.message}</p>`;
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

    // 임시 페이지로 가용 컬럼 높이 측정
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
    const usableColHeightNormal = pageHeight - 80 - footerHeight - 20; // csat-header-normal ≈ 80px
    tempPage.remove();

    // 각 아이템 높이 기록 (12px gap 포함)
    for (const { item, el } of measuredItems) {
        item.measuredHeight = el.offsetHeight + 12;
    }

    // 측정 컨테이너 제거
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

        // 헤더
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

        // 2단 컬럼
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

        // 푸터
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
