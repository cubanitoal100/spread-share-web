document.addEventListener('DOMContentLoaded', () => {
    const elType = document.getElementById('spread_type');
    const elExp = document.getElementById('expiration_menu');
    const elShort = document.getElementById('short_strike');
    const elLong = document.getElementById('long_strike');
    const elCredit = document.getElementById('net_credit');
    const elPrice = document.getElementById('current_price');
    const elComment = document.getElementById('txt_comment');
    const btnShare = document.getElementById('btn_share');
    const btnRefresh = document.getElementById('btn_refresh_price');
    const statusMsg = document.getElementById('status_msg');
    const toggleBtns = document.querySelectorAll('.toggle-btn');

    const chartImg = document.getElementById('chart_img');
    const chartPlaceholder = document.getElementById('chart_placeholder');

    let debounceTimer;
    let currentChartBlob = null;
    let baseChartImg = null;
    let chartAbortController = null;

    function setStatus(msg, color = 'var(--text-muted)') {
        statusMsg.textContent = msg;
        statusMsg.style.color = color;
    }

    async function loadMarketData() {
        setStatus("Connecting to market...", "var(--primary)");
        try {
            const res = await fetch('/api/market_data');
            const data = await res.json();
            if (data.error) throw new Error(data.error);

            elPrice.value = data.current_price.toFixed(2);

            elExp.innerHTML = '';
            if (data.expirations.length > 0) {
                data.expirations.forEach(d => {
                    const opt = document.createElement('option');
                    opt.value = d;
                    opt.textContent = d;
                    elExp.appendChild(opt);
                });
            } else {
                const opt = document.createElement('option');
                opt.textContent = "No data";
                elExp.appendChild(opt);
            }
            setStatus("Market connected. Dates and prices ready.", "var(--success)");
        } catch (e) {
            setStatus("Connection error: " + e.message, "red");
        }
    }

    async function autoCalcCredit() {
        const s_type = elType.value;
        const k_short = elShort.value;
        const k_long = elLong.value;
        const exp_date = elExp.value;

        if (!k_short || !k_long || !exp_date || exp_date === "Searching..." || exp_date === "No data") return;

        setStatus("Calculating premium...", "yellow");
        try {
            const res = await fetch('/api/calculate_credit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ s_type, k_short, k_long, exp_date })
            });
            const data = await res.json();
            if (data.error) throw new Error(data.error);

            elCredit.value = data.net_credit.toFixed(2);
            setStatus("Credit auto-calculated.", "var(--success)");
            await generateBaseChart();
        } catch (e) {
            setStatus("Error: " + e.message, "red");
            elCredit.value = "";
        }
    }

    function onStrikeChange() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(autoCalcCredit, 300);
    }

    async function generateBaseChart() {
        const s_type = elType.value;
        const k_short = elShort.value;
        const k_long = elLong.value;
        const net_credit = elCredit.value;

        if (!k_short || !k_long || !net_credit) {
            setStatus("Missing data for plotting.", "red");
            return;
        }

        if (chartAbortController) chartAbortController.abort();
        chartAbortController = new AbortController();
        const signal = chartAbortController.signal;

        setStatus("Generating chart...", "var(--primary)");
        try {
            const res = await fetch('/api/generate_chart', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ s_type, k_short, k_long, net_credit }),
                signal
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || "Error plotting");
            }

            const blob = await res.blob();
            const url = URL.createObjectURL(blob);

            baseChartImg = new Image();
            baseChartImg.onload = () => renderWithComment();
            baseChartImg.src = url;

            setStatus("Chart generated.", "var(--success)");
        } catch (e) {
            if (e.name !== 'AbortError') setStatus("Error: " + e.message, "red");
        }
    }

    function renderWithComment() {
        if (!baseChartImg) return;

        const comment = elComment.value.trim();
        const w = baseChartImg.naturalWidth;
        const h = baseChartImg.naturalHeight;

        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(baseChartImg, 0, 0);

        if (comment) {
            const panelX = w * 0.67;
            const panelW = w - panelX;
            const boxX = panelX + panelW * 0.04;
            const boxW = panelW * 0.88;
            const boxY = h * 0.76;
            const boxH = h * 0.94 - boxY; // altura fija hasta el fondo del panel
            const padY = 10;
            const maxTextW = boxW - 20;

            // Encuentra el font size más grande que quepa en el espacio fijo
            let fontSize, lines;
            for (fontSize = Math.round(w * 0.030); fontSize >= Math.round(w * 0.009); fontSize--) {
                ctx.font = `italic ${fontSize}px Inter, sans-serif`;
                const lh = fontSize * 1.45;
                const words = comment.split(' ');
                lines = [];
                let line = '';
                for (const word of words) {
                    const test = line ? `${line} ${word}` : word;
                    if (ctx.measureText(test).width > maxTextW && line) {
                        lines.push(line);
                        line = word;
                    } else {
                        line = test;
                    }
                }
                if (line) lines.push(line);
                if (lines.length * lh + padY * 2 <= boxH) break;
            }

            const lineHeight = fontSize * 1.45;
            const r = 6;

            ctx.fillStyle = '#E0E0E0';
            ctx.font = `italic ${fontSize}px Inter, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            // Centrar el bloque de texto verticalmente dentro de la caja
            const totalTextH = lines.length * lineHeight;
            let textY = boxY + padY + (boxH - padY * 2 - totalTextH) / 2;
            for (const l of lines) {
                ctx.fillText(l, boxX + boxW / 2, textY);
                textY += lineHeight;
            }
        }

        canvas.toBlob(blob => {
            currentChartBlob = blob;
            chartImg.src = URL.createObjectURL(blob);
            chartImg.style.display = 'block';
            chartPlaceholder.style.display = 'none';
        }, 'image/png');
    }

    async function shareWhatsApp() {
        if (!currentChartBlob) {
            setStatus("Please generate chart first.", "red");
            return;
        }

        if (!navigator.share) {
            const url = URL.createObjectURL(currentChartBlob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'spread.png';
            a.click();
            setStatus("Image downloaded. You can share it manually.", "var(--primary)");
            return;
        }

        try {
            const file = new File([currentChartBlob], "spread_chart.png", { type: 'image/png' });
            await navigator.share({ title: 'Spread Operation', files: [file] });
            setStatus("Shared successfully!", "var(--success)");
        } catch (e) {
            if (e.name !== 'AbortError') setStatus("Share cancelled.", "var(--text-muted)");
        }
    }

    // Eventos
    elShort.addEventListener('keyup', onStrikeChange);
    elLong.addEventListener('keyup', onStrikeChange);
    elExp.addEventListener('change', autoCalcCredit);
    elComment.addEventListener('input', renderWithComment);

    toggleBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            toggleBtns.forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            elType.value = e.target.dataset.value;
            autoCalcCredit();
        });
    });

    btnRefresh.addEventListener('click', loadMarketData);
    btnShare.addEventListener('click', shareWhatsApp);

    loadMarketData();
});
