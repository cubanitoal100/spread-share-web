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
    let commentDebounceTimer;
    let currentChartBlob = null;

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
            await generateChart();
        } catch (e) {
            setStatus("Error: " + e.message, "red");
            elCredit.value = "";
        }
    }

    function onStrikeChange() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(autoCalcCredit, 300);
    }

    async function generateChart() {
        const s_type = elType.value;
        const k_short = elShort.value;
        const k_long = elLong.value;
        const net_credit = elCredit.value;
        const comment = elComment.value;

        if (!k_short || !k_long || !net_credit) {
            setStatus("Missing data for plotting.", "red");
            return;
        }

        setStatus("Generating professional chart...", "var(--primary)");
        try {
            const res = await fetch('/api/generate_chart', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ s_type, k_short, k_long, net_credit, comment })
            });
            
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || "Error plotting");
            }
            
            currentChartBlob = await res.blob();
            const url = URL.createObjectURL(currentChartBlob);
            
            chartImg.src = url;
            chartImg.style.display = 'block';
            chartPlaceholder.style.display = 'none';
            
            setStatus("Chart generated successfully.", "var(--success)");
        } catch (e) {
            setStatus("Error: " + e.message, "red");
        }
    }

    async function shareWhatsApp() {
        if (!currentChartBlob) {
            setStatus("Please generate chart first.", "red");
            return;
        }

        // Si el usuario cambió el comentario después de graficar, graficamos de nuevo rápido
        setStatus("Preparing to share...", "var(--primary)");
        await generateChart();

        if (!navigator.share) {
            setStatus("Your browser does not natively support Web Share API.", "red");
            // Workaround para navegadores sin Share API: descargar la imagen
            const url = URL.createObjectURL(currentChartBlob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'spread.png';
            a.click();
            setStatus("Image downloaded. You can share it manually.", "var(--primary)");
            return;
        }

        try {
            const file = new File([currentChartBlob], "spread_chart.png", { type: currentChartBlob.type });
            await navigator.share({
                title: 'Spread Operation',
                files: [file]
            });
            setStatus("Shared successfully!", "var(--success)");
        } catch (e) {
            // El usuario canceló o falló
            console.error(e);
            setStatus("Share action completed or cancelled.", "var(--text-muted)");
        }
    }

    function onCommentChange() {
        clearTimeout(commentDebounceTimer);
        commentDebounceTimer = setTimeout(() => {
            if (currentChartBlob) generateChart();
        }, 400);
    }

    // Eventos
    elShort.addEventListener('keyup', onStrikeChange);
    elLong.addEventListener('keyup', onStrikeChange);
    elExp.addEventListener('change', autoCalcCredit);
    elComment.addEventListener('input', onCommentChange);

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

    // Carga inicial
    loadMarketData();
});
