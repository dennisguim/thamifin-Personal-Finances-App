// Estado global de Planejamento & Previsão
let selectedMonth = new Date().getMonth() + 1;
let selectedYear = new Date().getFullYear();
let cachedPlanejamentoData = null;
let CATEGORIES = [
    "Moradia & Contas", "Mercado", "Transporte", "Lazer", "Serviços & Assinaturas", 
    "Saúde", "Receita", "Transferência entre Contas", "Outros", "Loteria", 
    "Restaurante & Delivery", "Pagamento de Fatura"
];

document.addEventListener("DOMContentLoaded", () => {
    // Inicializa campos de data dos modais com o mês atual selecionado
    updateModalDateDefaults();
    
    // Carrega dados iniciais do planejamento
    loadPlanejamentoData();
    
    // Carrega categorias do servidor
    loadCategories();

    // Configura o drawer mobile e tema
    setupResponsiveMenuAndThemes();

    // Configura formulários dos modais
    setupExpenseForm();
    setupIncomeForm();

    // Ouve atualizações de categorias globais do modal
    document.addEventListener("categoriesUpdated", (e) => {
        if (e.detail) {
            CATEGORIES = e.detail;
            populateCategorySelect();
        }
    });
});

function formatCurrency(val) {
    return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL"
    }).format(val || 0);
}

function updateModalDateDefaults() {
    const mm = String(selectedMonth).padStart(2, "0");
    const todayStr = `${selectedYear}-${mm}-01`;
    const expDate = document.getElementById("expenseStartDate");
    const incDate = document.getElementById("incomeStartDate");
    if (expDate) expDate.value = todayStr;
    if (incDate) incDate.value = todayStr;
}

// Navegação de mês (+1 ou -1)
function navigateMonth(delta) {
    selectedMonth += delta;
    if (selectedMonth > 12) {
        selectedMonth = 1;
        selectedYear += 1;
    } else if (selectedMonth < 1) {
        selectedMonth = 12;
        selectedYear -= 1;
    }
    updateModalDateDefaults();
    loadPlanejamentoData();
}

// Volta ao mês atual
function goToCurrentMonth() {
    const now = new Date();
    selectedMonth = now.getMonth() + 1;
    selectedYear = now.getFullYear();
    updateModalDateDefaults();
    loadPlanejamentoData();
}

// Busca os dados consolidados do backend
async function loadPlanejamentoData() {
    try {
        const response = await fetch(`/api/planejamento/data?month=${selectedMonth}&year=${selectedYear}`);
        if (response.status === 401) {
            window.location.href = "/login";
            return;
        }
        
        const data = await response.json();
        cachedPlanejamentoData = data;
        renderPlanejamentoView(data);
    } catch (err) {
        console.error("Erro ao carregar dados do planejamento:", err);
    }
}

// Renderiza todos os blocos visuais da tela
function renderPlanejamentoView(data) {
    const { period, summary, planned_expenses, planned_incomes, categories_comparison } = data;

    // 1. Barra de Período
    document.getElementById("periodDisplay").innerText = period.label;
    const tagEl = document.getElementById("periodTag");
    if (period.is_current) {
        tagEl.innerText = "Mês Atual";
        tagEl.style.background = "var(--md-sys-color-primary-container)";
        tagEl.style.color = "var(--md-sys-color-primary)";
    } else if (period.is_future) {
        tagEl.innerText = "Previsão Futura";
        tagEl.style.background = "rgba(130, 10, 209, 0.15)";
        tagEl.style.color = "#820ad1";
    } else {
        tagEl.innerText = "Histórico / Concluído";
        tagEl.style.background = "var(--md-sys-color-surface-container-high)";
        tagEl.style.color = "var(--md-sys-color-outline)";
    }

    // Atualiza nome do mês nos títulos de seção
    document.querySelectorAll(".current-month-name").forEach(el => {
        el.innerText = period.label;
    });

    // Insight Rápido de Cobertura
    const insightEl = document.getElementById("quickCoverageInsight");
    if (summary.coverage_status === "superavit") {
        insightEl.innerHTML = `
            <span style="color: #2e7d32; display: flex; align-items: center; gap: 4px;">
                <span class="material-symbols-outlined" style="font-size: 19px;">check_circle</span>
                Superávit Projetado: <b>+${formatCurrency(summary.planned_balance)}</b>
            </span>
        `;
    } else if (summary.coverage_status === "deficit") {
        insightEl.innerHTML = `
            <span style="color: #e53935; display: flex; align-items: center; gap: 4px;">
                <span class="material-symbols-outlined" style="font-size: 19px;">warning</span>
                Déficit: <b>-${formatCurrency(summary.coverage_diff)}</b> (Precisa de receita extra!)
            </span>
        `;
    } else {
        insightEl.innerHTML = `
            <span style="color: var(--md-sys-color-outline); display: flex; align-items: center; gap: 4px;">
                <span class="material-symbols-outlined" style="font-size: 19px;">horizontal_rule</span>
                Receitas cobrem exatamente os gastos previstos
            </span>
        `;
    }

    // 2. KPIS
    // KPI 1: Gastos Previstos
    document.getElementById("totalPlannedExpensesDisplay").innerText = formatCurrency(summary.total_planned_expenses);
    document.getElementById("fixedBreakdown").innerText = `Fixos: ${formatCurrency(summary.total_planned_fixed)}`;
    document.getElementById("variableBreakdown").innerText = `Variáveis: ${formatCurrency(summary.total_planned_variable)}`;

    // KPI 2: Receitas Previstas
    document.getElementById("totalPlannedIncomeDisplay").innerText = formatCurrency(summary.total_planned_income);
    document.getElementById("neededIncomeText").innerHTML = `Necessário para cobrir gastos: <b>${formatCurrency(summary.needed_income)}</b>`;

    // KPI 3: Resultado Projetado
    const projBalEl = document.getElementById("projectedBalanceDisplay");
    const projSubtext = document.getElementById("projectedBalanceSubtext");
    const projCard = document.getElementById("projectedResultCard");
    const projIcon = document.getElementById("projectedResultIcon");

    const pBal = summary.planned_balance;
    const prefix = pBal > 0 ? "+" : "";
    projBalEl.innerText = `${prefix}${formatCurrency(pBal)}`;

    if (pBal > 0) {
        projBalEl.style.color = "#2e7d32";
        projCard.style.borderLeft = "6px solid #2e7d32";
        projIcon.style.color = "#2e7d32";
        projSubtext.innerText = "Previsão de sobra livre ao final do mês";
    } else if (pBal < 0) {
        projBalEl.style.color = "#e53935";
        projCard.style.borderLeft = "6px solid #e53935";
        projIcon.style.color = "#e53935";
        projSubtext.innerText = `Atenção: faltam ${formatCurrency(summary.coverage_diff)} para fechar a conta`;
    } else {
        projBalEl.style.color = "var(--md-sys-color-on-surface)";
        projCard.style.borderLeft = "6px solid var(--md-sys-color-outline)";
        projIcon.style.color = "var(--md-sys-color-outline)";
        projSubtext.innerText = "Orçamento em ponto de equilíbrio";
    }

    // KPI 4: Execução Real dos Extratos
    document.getElementById("realizedExpensesDisplay").innerText = formatCurrency(summary.total_realized_expenses);
    const usageBar = document.getElementById("budgetUsageBar");
    const usagePct = summary.budget_usage_pct;
    usageBar.style.width = `${Math.min(100, usagePct)}%`;

    if (usagePct > 100) {
        usageBar.style.background = "#e53935";
    } else if (usagePct >= 85) {
        usageBar.style.background = "#ff9800";
    } else {
        usageBar.style.background = "linear-gradient(90deg, #2e7d32 0%, var(--md-sys-color-primary) 100%)";
    }

    document.getElementById("budgetUsagePctText").innerText = `${usagePct}% do orçamento consumido`;
    const statusBadgeEl = document.getElementById("budgetStatusBadge");
    if (summary.total_realized_expenses === 0) {
        statusBadgeEl.innerHTML = `<span class="badge-status-neutral">Sem extratos no mês</span>`;
    } else if (usagePct > 100) {
        statusBadgeEl.innerHTML = `<span class="badge-status-exceeded">Excedido em ${formatCurrency(summary.budget_difference)}</span>`;
    } else {
        statusBadgeEl.innerHTML = `<span class="badge-status-ok">Resta ${formatCurrency(summary.total_planned_expenses - summary.total_realized_expenses)}</span>`;
    }

    // 3. Comparativo por Categorias
    renderCategoryComparisonGrid(categories_comparison);

    // 4. Tabelas de Gastos e Receitas
    renderPlannedExpensesTable(planned_expenses);
    renderPlannedIncomesTable(planned_incomes);
}

// Renderiza os Cards de Comparativo por Categoria
function renderCategoryComparisonGrid(categories) {
    const container = document.getElementById("categoryComparisonGrid");
    if (!categories || categories.length === 0) {
        container.innerHTML = `
            <div style="text-align: center; color: var(--md-sys-color-outline); padding: 32px; grid-column: 1 / -1;">
                Nenhuma categoria planejada ou com gastos registrados neste mês. Clique em <b>+ Lançar Gasto Previsto</b> para começar!
            </div>
        `;
        return;
    }

    container.innerHTML = "";
    categories.forEach(item => {
        const card = document.createElement("div");
        card.className = "category-budget-card";

        let statusBadge = "";
        let barColor = "var(--md-sys-color-primary)";

        if (item.status === "ok") {
            statusBadge = `<span class="badge-status-ok"><span class="material-symbols-outlined" style="font-size: 13px;">check</span> Dentro da Meta</span>`;
            barColor = item.usage_pct >= 85 ? "#ff9800" : "#2e7d32";
        } else if (item.status === "exceeded") {
            statusBadge = `<span class="badge-status-exceeded"><span class="material-symbols-outlined" style="font-size: 13px;">error</span> Excedeu ${formatCurrency(item.difference)}</span>`;
            barColor = "#e53935";
        } else if (item.status === "unbudgeted") {
            statusBadge = `<span class="badge-status-exceeded">Não Orçado</span>`;
            barColor = "#e53935";
        } else {
            statusBadge = `<span class="badge-status-neutral">Sem gastos reais</span>`;
            barColor = "var(--md-sys-color-outline-variant)";
        }

        const barWidth = Math.min(100, item.usage_pct);

        card.innerHTML = `
            <div class="category-budget-header">
                <span class="category-budget-title">
                    <span class="material-symbols-outlined" style="font-size: 18px; color: var(--md-sys-color-primary);">category</span>
                    ${item.category}
                </span>
                ${statusBadge}
            </div>

            <!-- Barra de Progresso do Teto -->
            <div class="ratio-progress-bar" style="margin-top: 2px; height: 8px;">
                <div class="ratio-progress-fill" style="width: ${barWidth}%; background: ${barColor};"></div>
            </div>

            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 12.5px; margin-top: 4px;">
                <div>
                    <span style="color: var(--md-sys-color-outline);">Gasto Real:</span>
                    <b style="color: var(--md-sys-color-on-surface); font-size: 13px;">${formatCurrency(item.realized)}</b>
                </div>
                <div style="text-align: right;">
                    <span style="color: var(--md-sys-color-outline);">Teto Previsto:</span>
                    <b style="color: var(--md-sys-color-primary); font-size: 13px;">${formatCurrency(item.planned)}</b>
                </div>
            </div>
        `;

        container.appendChild(card);
    });
}

// Renderiza a tabela de Gastos Previstos
function renderPlannedExpensesTable(expenses) {
    const tbody = document.getElementById("plannedExpensesTableBody");
    tbody.innerHTML = "";

    const filterVal = document.getElementById("expenseFilterType").value;
    let filtered = expenses;

    if (filterVal === "fixo") {
        filtered = filtered.filter(e => e.cost_type === "fixo");
    } else if (filterVal === "variavel") {
        filtered = filtered.filter(e => e.cost_type === "variavel");
    } else if (filterVal === "recurrent") {
        filtered = filtered.filter(e => e.is_recurrent);
    } else if (filterVal === "single") {
        filtered = filtered.filter(e => !e.is_recurrent);
    }

    if (!filtered || filtered.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; color: var(--md-sys-color-outline); padding: 32px;">
                    Nenhum gasto previsto encontrado para este filtro.
                </td>
            </tr>
        `;
        return;
    }

    filtered.forEach(exp => {
        const row = document.createElement("tr");
        row.className = "tx-row";

        const typeBadge = exp.cost_type === "fixo"
            ? `<span class="badge-cost-fixo"><span class="material-symbols-outlined" style="font-size: 13px;">lock</span> Fixo</span>`
            : `<span class="badge-cost-variavel"><span class="material-symbols-outlined" style="font-size: 13px;">tune</span> Variável</span>`;

        const recurBadge = exp.is_recurrent
            ? `<span class="badge-recurrent" title="Gasto se repete todo mês"><span class="material-symbols-outlined" style="font-size: 13px;">all_inclusive</span> Recorrente</span>`
            : `<span class="badge-single" title="Gasto eventual neste mês"><span class="material-symbols-outlined" style="font-size: 13px;">event_available</span> Pontual</span>`;

        row.innerHTML = `
            <td style="font-weight: 600; color: var(--md-sys-color-primary);">Dia ${exp.due_day}</td>
            <td style="font-weight: 600; font-size: 14px; color: var(--md-sys-color-on-surface);">${exp.description}</td>
            <td>
                <span style="font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: var(--radius-sm); background: var(--glass-input-bg); border: 1px solid var(--md-sys-color-outline-variant);">
                    ${exp.category}
                </span>
            </td>
            <td>${typeBadge}</td>
            <td>${recurBadge}</td>
            <td style="font-weight: 700; color: #e53935; font-size: 14.5px;">${formatCurrency(exp.amount)}</td>
            <td style="text-align: center;">
                <button type="button" onclick="deletePlannedExpense(${exp.id}, '${exp.description.replace(/'/g, "\\'")}')" class="m3-btn" style="width: auto; padding: 4px 8px; min-height: 28px; background: rgba(229, 57, 53, 0.1); color: #e53935; border: 1px solid rgba(229, 57, 53, 0.25); border-radius: var(--radius-sm);" title="Excluir gasto previsto">
                    <span class="material-symbols-outlined" style="font-size: 16px;">delete</span>
                </button>
            </td>
        `;

        tbody.appendChild(row);
    });
}

function filterExpensesTable() {
    if (cachedPlanejamentoData) {
        renderPlannedExpensesTable(cachedPlanejamentoData.planned_expenses);
    }
}

// Renderiza a tabela de Receitas Simuladas
function renderPlannedIncomesTable(incomes) {
    const tbody = document.getElementById("plannedIncomesTableBody");
    tbody.innerHTML = "";

    if (!incomes || incomes.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--md-sys-color-outline); padding: 32px;">
                    Nenhuma receita simulada ou fixada para este mês. Clique em <b>+ Simular Receita</b>!
                </td>
            </tr>
        `;
        return;
    }

    incomes.forEach(inc => {
        const row = document.createElement("tr");
        row.className = "tx-row";

        const recurBadge = inc.is_recurrent
            ? `<span class="badge-recurrent" title="Receita fixada nos meses futuros"><span class="material-symbols-outlined" style="font-size: 13px;">all_inclusive</span> Recorrente</span>`
            : `<span class="badge-single" title="Receita pontual neste mês"><span class="material-symbols-outlined" style="font-size: 13px;">event_available</span> Pontual</span>`;

        row.innerHTML = `
            <td style="font-weight: 600; color: #2e7d32;">Dia ${inc.receive_day}</td>
            <td style="font-weight: 600; font-size: 14px; color: var(--md-sys-color-on-surface);">${inc.description}</td>
            <td>${recurBadge}</td>
            <td style="font-weight: 700; color: #2e7d32; font-size: 14.5px;">+${formatCurrency(inc.amount)}</td>
            <td style="text-align: center;">
                <button type="button" onclick="deleteFutureIncomeItem(${inc.id}, '${inc.description.replace(/'/g, "\\'")}')" class="m3-btn" style="width: auto; padding: 4px 8px; min-height: 28px; background: rgba(229, 57, 53, 0.1); color: #e53935; border: 1px solid rgba(229, 57, 53, 0.25); border-radius: var(--radius-sm);" title="Excluir receita simulada">
                    <span class="material-symbols-outlined" style="font-size: 16px;">delete</span>
                </button>
            </td>
        `;

        tbody.appendChild(row);
    });
}

// Excluir Gasto Previsto
async function deletePlannedExpense(id, description) {
    if (!confirm(`Deseja realmente excluir o gasto previsto "${description}"?`)) return;

    try {
        const res = await fetch(`/api/planned-expenses/${id}`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok) {
            loadPlanejamentoData();
        } else {
            alert("Erro: " + data.detail);
        }
    } catch (err) {
        alert("Erro ao excluir gasto previsto.");
    }
}

// Excluir Receita Prevista
async function deleteFutureIncomeItem(id, description) {
    if (!confirm(`Deseja realmente excluir a receita prevista "${description}"?`)) return;

    try {
        const res = await fetch(`/api/future-incomes/${id}`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok) {
            loadPlanejamentoData();
        } else {
            alert("Erro: " + data.detail);
        }
    } catch (err) {
        alert("Erro ao excluir receita prevista.");
    }
}

// Configura o formulário de Gasto Previsto
function setupExpenseForm() {
    const form = document.getElementById("newExpenseForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const desc = document.getElementById("expenseDescription").value.trim();
        const amount = parseFloat(document.getElementById("expenseAmount").value);
        const dueDay = parseInt(document.getElementById("expenseDueDay").value) || 10;
        const category = document.getElementById("expenseCategory").value;
        const costType = document.getElementById("expenseCostType").value;
        const isRecurrent = document.getElementById("expenseIsRecurrent").checked;
        const startDate = document.getElementById("expenseStartDate").value;

        if (!desc || isNaN(amount) || amount <= 0) {
            alert("Preencha descrição e valor válidos.");
            return;
        }

        const formData = new FormData();
        formData.append("description", desc);
        formData.append("amount", amount);
        formData.append("due_day", dueDay);
        formData.append("category", category);
        formData.append("cost_type", costType);
        formData.append("is_recurrent", isRecurrent ? "true" : "false");
        formData.append("start_date", startDate);

        try {
            const res = await fetch("/api/planned-expenses", { method: "POST", body: formData });
            const data = await res.json();
            if (res.ok) {
                closeNewExpenseModal();
                form.reset();
                selectExpenseCostType("fixo");
                document.getElementById("expenseIsRecurrent").checked = true;
                updateModalDateDefaults();
                loadPlanejamentoData();
            } else {
                alert("Erro: " + data.detail);
            }
        } catch (err) {
            alert("Erro ao cadastrar gasto previsto.");
        }
    });

    const overlay = document.getElementById("expenseModalOverlay");
    if (overlay) overlay.addEventListener("click", closeNewExpenseModal);
}

// Configura o formulário de Receita Simulada
function setupIncomeForm() {
    const form = document.getElementById("newIncomeForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const desc = document.getElementById("incomeDescription").value.trim();
        const amount = parseFloat(document.getElementById("incomeAmount").value);
        const receiveDay = parseInt(document.getElementById("incomeReceiveDay").value) || 5;
        const isRecurrent = document.getElementById("incomeIsRecurrent").checked;
        const startDate = document.getElementById("incomeStartDate").value;

        if (!desc || isNaN(amount) || amount <= 0) {
            alert("Preencha descrição e valor válidos.");
            return;
        }

        const formData = new FormData();
        formData.append("description", desc);
        formData.append("amount", amount);
        formData.append("receive_day", receiveDay);
        formData.append("is_recurrent", isRecurrent ? "true" : "false");
        formData.append("start_date", startDate);

        try {
            const res = await fetch("/api/future-incomes", { method: "POST", body: formData });
            const data = await res.json();
            if (res.ok) {
                closeNewIncomeModal();
                form.reset();
                document.getElementById("incomeIsRecurrent").checked = true;
                updateModalDateDefaults();
                loadPlanejamentoData();
            } else {
                alert("Erro: " + data.detail);
            }
        } catch (err) {
            alert("Erro ao cadastrar receita prevista.");
        }
    });

    const overlay = document.getElementById("incomeModalOverlay");
    if (overlay) overlay.addEventListener("click", closeNewIncomeModal);
}

// Modais Controles
function openNewExpenseModal() {
    const modal = document.getElementById("newExpenseModal");
    const overlay = document.getElementById("expenseModalOverlay");
    if (modal && overlay) {
        modal.classList.add("active");
        overlay.classList.add("active");
        document.getElementById("expenseDescription").focus();
    }
}

function closeNewExpenseModal() {
    const modal = document.getElementById("newExpenseModal");
    const overlay = document.getElementById("expenseModalOverlay");
    if (modal && overlay) {
        modal.classList.remove("active");
        overlay.classList.remove("active");
    }
}

function selectExpenseCostType(type) {
    document.getElementById("expenseCostType").value = type;
    const fixoBtn = document.getElementById("typeFixoBtn");
    const varBtn = document.getElementById("typeVariavelBtn");
    if (type === "fixo") {
        fixoBtn.classList.add("active");
        varBtn.classList.remove("active");
    } else {
        varBtn.classList.add("active");
        fixoBtn.classList.remove("active");
    }
}

function openNewIncomeModal() {
    const modal = document.getElementById("newIncomeModal");
    const overlay = document.getElementById("incomeModalOverlay");
    if (modal && overlay) {
        modal.classList.add("active");
        overlay.classList.add("active");
        document.getElementById("incomeDescription").focus();
    }
}

function closeNewIncomeModal() {
    const modal = document.getElementById("newIncomeModal");
    const overlay = document.getElementById("incomeModalOverlay");
    if (modal && overlay) {
        modal.classList.remove("active");
        overlay.classList.remove("active");
    }
}

// Carrega categorias e popula o select
async function loadCategories() {
    try {
        const res = await fetch("/api/categories");
        if (res.ok) {
            const data = await res.json();
            if (data && data.length > 0) {
                CATEGORIES = data.map(c => c.name);
            }
        }
    } catch (e) {
        console.error("Erro ao carregar categorias:", e);
    }
    populateCategorySelect();
}

function populateCategorySelect() {
    const select = document.getElementById("expenseCategory");
    if (!select) return;
    select.innerHTML = "";
    CATEGORIES.forEach(cat => {
        if (cat === "Transferência entre Contas") return; // Não é categoria de gasto orçamentário
        const opt = document.createElement("option");
        opt.value = cat;
        opt.innerText = cat;
        if (cat === "Moradia & Contas") opt.selected = true;
        select.appendChild(opt);
    });
}

// Configura gaveta mobile e alternador de tema
function setupResponsiveMenuAndThemes() {
    const mobileMenuBtn = document.getElementById("mobileMenuBtn");
    const bottomNavMenuBtn = document.getElementById("bottomNavMenuBtn");
    const closeSidebarBtn = document.getElementById("closeSidebarBtn");
    const sidebarOverlay = document.getElementById("sidebarOverlay");
    const dashboardSidebar = document.getElementById("dashboardSidebar");

    if (dashboardSidebar && sidebarOverlay) {
        const openSidebar = () => {
            dashboardSidebar.classList.add("active");
            sidebarOverlay.classList.add("active");
            document.body.style.overflow = "hidden";
        };

        const closeSidebar = () => {
            dashboardSidebar.classList.remove("active");
            sidebarOverlay.classList.remove("active");
            document.body.style.overflow = "";
        };

        if (mobileMenuBtn) mobileMenuBtn.addEventListener("click", openSidebar);
        if (bottomNavMenuBtn) {
            bottomNavMenuBtn.addEventListener("click", () => {
                if (dashboardSidebar.classList.contains("active")) {
                    closeSidebar();
                } else {
                    openSidebar();
                }
            });
        }
        if (closeSidebarBtn) closeSidebarBtn.addEventListener("click", closeSidebar);
        sidebarOverlay.addEventListener("click", closeSidebar);
    }

    // Toggle de Tema
    const desktopThemeToggleBtn = document.getElementById("desktopThemeToggleBtn");
    const mobileThemeToggleBtn = document.getElementById("mobileThemeToggleBtn");
    const desktopThemeToggleIcon = document.getElementById("desktopThemeToggleIcon");
    const mobileThemeToggleIcon = document.getElementById("mobileThemeToggleIcon");

    const updateIcons = (dark) => {
        const iconName = dark ? "light_mode" : "dark_mode";
        if (desktopThemeToggleIcon) desktopThemeToggleIcon.innerText = iconName;
        if (mobileThemeToggleIcon) mobileThemeToggleIcon.innerText = iconName;
        const metaTheme = document.getElementById("themeColorMeta");
        if (metaTheme) metaTheme.setAttribute("content", dark ? "#10141d" : "#f6f8fb");
    };

    updateIcons(document.body.classList.contains("dark-mode"));

    const toggleTheme = () => {
        const isDark = document.body.classList.toggle("dark-mode");
        localStorage.setItem("theme", isDark ? "dark" : "light");
        updateIcons(isDark);
    };

    if (desktopThemeToggleBtn) desktopThemeToggleBtn.addEventListener("click", toggleTheme);
    if (mobileThemeToggleBtn) mobileThemeToggleBtn.addEventListener("click", toggleTheme);
}
