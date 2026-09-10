const toast = document.getElementById("toast");

function showToast(message, duration = 2500) {
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), duration);
}

// --- Relógio em tempo real ---
const clockEl = document.getElementById("clock");
const dateEl = document.getElementById("date");
const WEEKDAYS = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado"];
const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function updateClock() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    clockEl.textContent = `${hh}:${mm}`;
    dateEl.textContent = `${WEEKDAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]}`;
}
updateClock();
setInterval(updateClock, 1000);

// --- Clima ---
const tempEl = document.getElementById("weather-temp");
const descEl = document.getElementById("weather-desc");

async function updateWeather() {
    try {
        const res = await fetch("/api/weather");
        const data = await res.json();
        if (data.ok) {
            tempEl.textContent = `${data.temperature}°`;
            descEl.textContent = data.description;
        } else {
            descEl.textContent = data.message || "clima indisponível";
        }
    } catch (err) {
        descEl.textContent = "clima indisponível";
    }
}
updateWeather();
setInterval(updateWeather, 10 * 60 * 1000);

// --- Ícone de voice (stub, até a voz entrar no projeto) ---
document.getElementById("voice-btn").addEventListener("click", () => {
    showToast("Voz ainda não configurada neste projeto — só texto por enquanto.");
});

// --- Monitor local de uso/custo ---
const creditsModal = document.getElementById("credits-modal");
const creditsMsg = document.getElementById("credits-msg");
const creditsQr = document.getElementById("credits-qr");
const qrHint = document.getElementById("qr-hint");

function fmtInt(value) {
    return Number(value || 0).toLocaleString("pt-BR");
}

function fmtUsd(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toLocaleString("pt-BR", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 4,
    });
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function usageRow(label, value) {
    return `<div class="usage-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderUsage(data) {
    const usage = data.usage || {};
    const month = usage.month || {};
    const today = usage.today || {};
    const last30 = usage.last_30_days || {};
    const budget = usage.budget || {};
    const models = usage.models_this_month || [];
    const percent = Math.max(0, Math.min(Number(budget.percent_used || 0), 100));

    const modelHtml = models.length
        ? models.map(item => `
            <div class="usage-model">
                <div class="usage-model-name">${escapeHtml(item.model)}</div>
                <div class="usage-model-meta">
                    ${fmtInt(item.input_tokens)} in · ${fmtInt(item.output_tokens)} out
                    ${item.estimated_cost_usd == null ? " · custo indisponível" : ` · ${fmtUsd(item.estimated_cost_usd)}`}
                </div>
            </div>`).join("")
        : `<div class="usage-muted">Nenhuma chamada registrada neste mês.</div>`;

    const budgetHtml = Number(budget.monthly_usd || 0) > 0 ? `
        <div class="usage-section">
            <div class="usage-section-title">ORÇAMENTO LOCAL</div>
            ${usageRow("Limite mensal", fmtUsd(budget.monthly_usd))}
            ${usageRow("Usado", fmtUsd(budget.used_usd))}
            ${usageRow("Restante calculado", fmtUsd(budget.remaining_usd))}
            <div class="usage-progress" aria-label="Percentual do orçamento usado"><span style="width:${percent}%"></span></div>
            <div class="usage-percent">${Number(budget.percent_used || 0).toFixed(1)}%</div>
            ${budget.warning ? `<div class="usage-warning">⚠ Limite de atenção atingido.</div>` : ""}
        </div>` : "";

    creditsMsg.innerHTML = `
        <div class="usage-monitor">
            <div class="usage-subtitle">Uso local do DOK · este mês</div>
            <div class="usage-section">
                ${usageRow("Requisições", fmtInt(month.requests))}
                ${usageRow("Entrada", fmtInt(month.input_tokens))}
                ${usageRow("Saída", fmtInt(month.output_tokens))}
                ${usageRow("Cache criado", fmtInt(month.cache_creation_input_tokens))}
                ${usageRow("Cache lido", fmtInt(month.cache_read_input_tokens))}
                ${usageRow("Custo estimado", fmtUsd(month.estimated_cost_usd))}
            </div>

            <div class="usage-section">
                <div class="usage-section-title">HOJE</div>
                ${usageRow("Requisições", fmtInt(today.requests))}
                ${usageRow("Tokens", fmtInt(today.total_tokens))}
                ${usageRow("Custo", fmtUsd(today.estimated_cost_usd))}
            </div>

            <div class="usage-section">
                <div class="usage-section-title">ÚLTIMOS 30 DIAS</div>
                ${usageRow("Requisições", fmtInt(last30.requests))}
                ${usageRow("Tokens", fmtInt(last30.total_tokens))}
                ${usageRow("Custo", fmtUsd(last30.estimated_cost_usd))}
            </div>

            ${budgetHtml}

            <div class="usage-section">
                <div class="usage-section-title">MODELOS · ESTE MÊS</div>
                ${modelHtml}
            </div>

            <div class="usage-note">${escapeHtml(usage.notice || "Monitoramento local.")}</div>
            <a class="usage-billing" href="${escapeHtml(data.billing_url || "https://console.anthropic.com/settings/billing")}" target="_blank" rel="noopener">Abrir Billing da Anthropic ↗</a>
        </div>`;
}

async function loadUsage() {
    creditsMsg.textContent = "Carregando uso…";
    try {
        const res = await fetch("/api/usage", { cache: "no-store" });
        const data = await res.json();

        if (!res.ok || !data.ok) {
            creditsMsg.textContent = data.message || "Não foi possível carregar o monitoramento.";
            return;
        }
        renderUsage(data);

        if (data.qr_available) {
            creditsQr.src = data.qr_url + "?t=" + Date.now();
            creditsQr.hidden = false;
            qrHint.hidden = false;
        }
    } catch (err) {
        creditsMsg.textContent = "Não foi possível consultar o monitoramento agora.";
    }
}

document.getElementById("credits-btn").addEventListener("click", async () => {
    creditsModal.classList.add("show");
    creditsQr.hidden = true;
    qrHint.hidden = true;
    await loadUsage();
});

document.getElementById("credits-close").addEventListener("click", () => {
    creditsModal.classList.remove("show");
});
