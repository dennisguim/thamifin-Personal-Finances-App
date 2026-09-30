// Estado global da página de custos
let allAccounts = [];
let CATEGORIES = ["Transporte", "Lazer", "Serviços & Assinaturas", "Saúde", "Receita", "Outros", "Loteria", "Mercado", "Restaurante & Delivery", "Pagamento de Fatura", "Moradia & Contas"];

document.addEventListener("DOMContentLoaded", () => {
    // Carrega dados iniciais do Dashboard
    loadCostsData();
    // Configura o menu responsivo e alternadores de temas
    setupResponsiveMenuAndThemes();
    // Configura os ouvintes dos filtros
    setupFilters();
});

async function loadCostsData() {
    try {
        const response = await fetch("/api/data");
        if (response.status === 401) {
            window.location.href = "/login";
            return;
        }
        
        const data = await response.json();
        allAccounts = data.accounts;
        
        // Atualiza nome do usuário na sidebar
        document.getElementById("userNameDisplay").innerText = data.user_name;
        
        // Inicializa filtros dinâmicos na primeira carga
        initializeDynamicFilters();
        
        // Renderiza e calcula custos
        processAndRenderCosts();
        
    } catch (err) {
        console.error("Erro ao carregar dados de custos:", err);
    }
}

function initializeDynamicFilters() {
    const accountFilter = document.getElementById("accountFilter");
    const dayFilter = document.getElementById("dayFilter");
    const yearFilter = document.getElementById("yearFilter");
    
    // 1. Popula Contas
    accountFilter.innerHTML = '<option value="all">Todas as Contas</option>';
    allAccounts.forEach(acc => {
        const opt = document.createElement("option");
        opt.value = acc.id;
        opt.innerText = acc.bank_name;
        accountFilter.appendChild(opt);
    });
    
    // 2. Popula Dias (1 a 31)
    dayFilter.innerHTML = '<option value="all">Todos</option>';
    for (let i = 1; i <= 31; i++) {
        const opt = document.createElement("option");
        opt.value = i.toString();
        opt.innerText = i.toString().padStart(2, '0');
        dayFilter.appendChild(opt);
    }
    
    // 3. Popula Anos dinamicamente das transações
    yearFilter.innerHTML = '<option value="all">Todos</option>';
    let years = new Set();
    allAccounts.forEach(acc => {
        acc.transactions.forEach(tx => {
            const parts = tx.date.split("/");
            years.add(parts[2]);
        });
    });
    
    const sortedYears = Array.from(years).sort((a, b) => b - a);
    sortedYears.forEach(y => {
        const opt = document.createElement("option");
        opt.value = y;
        opt.innerText = y;
        yearFilter.appendChild(opt);
    });

    // 4. Popula Categorias dinamicamente das despesas ou usa as padrões
    const categoryFilter = document.getElementById("categoryFilter");
    if (categoryFilter) {
        categoryFilter.innerHTML = '<option value="all">Todas as Categorias</option>';
        let uniqueCategories = new Set();
        allAccounts.forEach(acc => {
            acc.transactions.forEach(tx => {
                if (tx.amount < 0 && tx.category && tx.category !== "Receita") {
                    uniqueCategories.add(tx.category);
                }
            });
        });
        
        CATEGORIES.forEach(cat => {
            if (cat !== "Receita") uniqueCategories.add(cat);
        });
        
        Array.from(uniqueCategories).sort().forEach(cat => {
            const opt = document.createElement("option");
            opt.value = cat;
            opt.innerText = cat;
            categoryFilter.appendChild(opt);
        });
    }
}

function setupFilters() {
    // Alternar filtros de data (Dia/Mês/Ano vs Intervalo)
    const dateModeSelect = document.getElementById("dateModeSelect");
    const dmaGroups = document.querySelectorAll(".date-dma-group");
    const rangeGroups = document.querySelectorAll(".date-range-group");
    
    dateModeSelect.addEventListener("change", () => {
        const mode = dateModeSelect.value;
        if (mode === "dma") {
            dmaGroups.forEach(el => el.style.display = "flex");
            rangeGroups.forEach(el => el.style.display = "none");
            
            // Reseta filtros de intervalo
            document.getElementById("startDateFilter").value = "";
            document.getElementById("endDateFilter").value = "";
        } else {
            dmaGroups.forEach(el => el.style.display = "none");
            rangeGroups.forEach(el => el.style.display = "flex");
            
            // Reseta filtros de dropdown
            document.getElementById("dayFilter").value = "all";
            document.getElementById("monthFilter").value = "all";
            document.getElementById("yearFilter").value = "all";
        }
        processAndRenderCosts();
    });
    
    // Vincula todos os demais filtros de dropdown e input
    const filterIds = [
        "accountFilter", "dayFilter", "monthFilter", "yearFilter",
        "startDateFilter", "endDateFilter", "costTypeFilter", "categoryFilter", "searchInput"
    ];
    
    filterIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("change", processAndRenderCosts);
            el.addEventListener("input", processAndRenderCosts);
        }
    });
}

// Filtro inteligente de data que suporta DMA e Intervalo de Datas
function filterByDate(txDateStr) {
    const dateMode = document.getElementById("dateModeSelect").value;
    const txDate = parseDateStr(txDateStr);
    
    if (dateMode === "range") {
        const startVal = document.getElementById("startDateFilter").value;
        const endVal = document.getElementById("endDateFilter").value;
        
        if (startVal) {
            const startDate = new Date(startVal + "T00:00:00");
            if (txDate < startDate) return false;
        }
        if (endVal) {
            const endDate = new Date(endVal + "T23:59:59");
            if (txDate > endDate) return false;
        }
        return true;
    } else {
        const dayVal = document.getElementById("dayFilter").value;
        const monthVal = document.getElementById("monthFilter").value;
        const yearVal = document.getElementById("yearFilter").value;
        
        const parts = txDateStr.split("/");
        const txDay = parseInt(parts[0], 10).toString();
        const txMonth = parseInt(parts[1], 10).toString();
        const txYear = parts[2];
        
        if (dayVal !== "all" && dayVal !== txDay) return false;
        if (monthVal !== "all" && monthVal !== txMonth) return false;
        if (yearVal !== "all" && yearVal !== txYear) return false;
        
        return true;
    }
}

// Retorna a data final limite do período selecionado para o cálculo do saldo histórico
function getPeriodEndDate() {
    const dateMode = document.getElementById("dateModeSelect").value;
    if (dateMode === "range") {
        const endVal = document.getElementById("endDateFilter").value;
        return endVal ? new Date(endVal + "T23:59:59") : null;
    } else {
        const d = document.getElementById("dayFilter").value;
        const m = document.getElementById("monthFilter").value;
        const y = document.getElementById("yearFilter").value;
        
        if (y === "all" && m === "all" && d === "all") return null;
        
        const year = y !== "all" ? parseInt(y, 10) : new Date().getFullYear();
        const month = m !== "all" ? parseInt(m, 10) - 1 : 11; // Dezembro se todos
        let day;
        if (d !== "all") {
            day = parseInt(d, 10);
        } else {
            // Pega o último dia do mês
            day = new Date(year, month + 1, 0).getDate();
        }
        return new Date(year, month, day, 23, 59, 59);
    }
}

function processAndRenderCosts() {
    const accountFilterValue = document.getElementById("accountFilter").value;
    const costTypeFilterValue = document.getElementById("costTypeFilter").value;
    const categoryFilterElement = document.getElementById("categoryFilter");
    const categoryFilterValue = categoryFilterElement ? categoryFilterElement.value : "all";
    
    let costs = [];
    
    // 1. Coleta todas as despesas das contas correspondentes ao filtro
    allAccounts.forEach(acc => {
        if (accountFilterValue !== "all" && accountFilterValue !== acc.id.toString()) {
            return;
        }
        
        acc.transactions.forEach(tx => {
            if (tx.amount < 0) { // Apenas despesas são custos
                costs.push({
                    ...tx,
                    accountId: acc.id,
                    bankName: acc.bank_name
                });
            }
        });
    });
    
    // 2. Filtra por data usando a lógica inteligente
    costs = costs.filter(tx => filterByDate(tx.date));
    
    // 3. Filtra por Tipo de Custo (Fixo / Variável)
    if (costTypeFilterValue !== "all") {
        costs = costs.filter(tx => tx.cost_type === costTypeFilterValue);
    }
    
    // 3.5 Filtra por Categoria
    if (categoryFilterValue !== "all") {
        costs = costs.filter(tx => tx.category === categoryFilterValue);
    }
    
    // 3.6 Filtra por busca de nome
    const searchVal = document.getElementById("searchInput").value.trim().toLowerCase();
    if (searchVal) {
        costs = costs.filter(tx => tx.description.toLowerCase().includes(searchVal));
    }
    
    // Ordena do mais recente ao mais antigo
    costs.sort((a, b) => parseDateStr(b.date) - parseDateStr(a.date));
    
    // 4. Calcula Totais de Custos
    let totalFixed = 0;
    let totalVariable = 0;
    
    costs.forEach(c => {
        const absVal = Math.abs(c.amount);
        if (c.cost_type === "fixo") {
            totalFixed += absVal;
        } else {
            totalVariable += absVal;
        }
    });
    
    // 5. Calcula o Saldo da Conta no Período Selecionado
    const endDate = getPeriodEndDate();
    let totalPeriodBalance = 0;
    
    allAccounts.forEach(acc => {
        if (accountFilterValue !== "all" && accountFilterValue !== acc.id.toString()) {
            return;
        }
        
        // Saldo histórico inicial da conta + movimentações até o limite do período
        let balance = acc.initial_balance || 0;
        acc.transactions.forEach(t => {
            const txDate = parseDateStr(t.date);
            if (!endDate || txDate <= endDate) {
                balance += t.amount;
            }
        });
        totalPeriodBalance += balance;
    });
    
    // --- ATUALIZA OS CARDS KPIs ---
    document.getElementById("totalFixedDisplay").innerText = formatCurrency(totalFixed);
    document.getElementById("totalVariableDisplay").innerText = formatCurrency(totalVariable);
    
    // Card Proporção (Ratio)
    const totalCosts = totalFixed + totalVariable;
    let fixedPct = 0;
    let variablePct = 0;
    
    if (totalCosts > 0) {
        fixedPct = Math.round((totalFixed / totalCosts) * 100);
        variablePct = 100 - fixedPct;
        document.getElementById("ratioDisplay").innerText = `${fixedPct}% / ${variablePct}%`;
        document.getElementById("ratioFill").style.width = `${fixedPct}%`;
    } else {
        document.getElementById("ratioDisplay").innerText = "0% / 0%";
        document.getElementById("ratioFill").style.width = "0%";
    }
    
    // Card Saldo no Período
    const balanceCardTitle = document.getElementById("balanceCardTitle");
    const periodBalanceDisplay = document.getElementById("periodBalanceDisplay");
    
    if (accountFilterValue === "all") {
        balanceCardTitle.innerText = "Saldo Consolidado";
    } else {
        const selectedAcc = allAccounts.find(a => a.id.toString() === accountFilterValue);
        balanceCardTitle.innerText = `Saldo no ${selectedAcc.bank_name}`;
    }
    periodBalanceDisplay.innerText = formatCurrency(totalPeriodBalance);
    
    // Renderiza a Tabela de despesas filtrada
    renderCostsTable(costs);
}

function renderCostsTable(costs) {
    const listContainer = document.getElementById("costsList");
    listContainer.innerHTML = "";
    
    if (costs.length === 0) {
        listContainer.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; color: var(--md-sys-color-outline); padding: 32px;">
                    Nenhuma despesa encontrada para os filtros selecionados.
                </td>
            </tr>
        `;
        return;
    }
    
    costs.forEach(tx => {
        const row = document.createElement("tr");
        row.className = "tx-row";
        
        // Badge do banco
        let bankBadgeClass = "badge-bank-default";
        if (tx.bankName.toLowerCase().includes("nubank")) {
            bankBadgeClass = "badge-bank-nubank";
        } else if (tx.bankName.toLowerCase().includes("inter")) {
            bankBadgeClass = "badge-bank-inter";
        } else if (tx.bankName.toLowerCase().includes("caixa")) {
            bankBadgeClass = "badge-bank-caixa";
        }
        const bankBadgeHtml = `<span class="badge-bank ${bankBadgeClass}">${tx.bankName}</span>`;
        
        // Badge de PIX
        let typeBadge = "";
        if (tx.type === "PIX_RECEBIDO" || tx.type === "PIX_ENVIADO") {
            typeBadge = `<span class="badge-pix">PIX</span> `;
        }
        
        // Seletor Segmentado Fixo vs Variável
        const isFixo = tx.cost_type === "fixo";
        const controlHtml = `
            <div class="segmented-control table-segmented-control">
                <button class="segmented-btn ${isFixo ? 'active' : ''}" 
                        onclick="changeCostType(${tx.id}, 'fixo', this)" 
                        title="Marcar como Custo Fixo">
                    Fixo
                </button>
                <button class="segmented-btn ${!isFixo ? 'active' : ''}" 
                        onclick="changeCostType(${tx.id}, 'variavel', this)" 
                        title="Marcar como Custo Variável">
                    Variável
                </button>
            </div>
        `;
        
        // Cria caixa de seleção para a categoria (Material Design)
        let selectHtml = `<select class="category-select" onchange="changeCategory(${tx.id}, this.value)">`;
        CATEGORIES.forEach(cat => {
            const selected = tx.category === cat ? "selected" : "";
            selectHtml += `<option value="${cat}" ${selected}>${cat}</option>`;
        });
        selectHtml += "</select>";
        
        row.innerHTML = `
            <td style="color: var(--md-sys-color-secondary); font-weight: 500;">${tx.date}</td>
            <td>${bankBadgeHtml}</td>
            <td>${typeBadge}${tx.description}</td>
            <td>${controlHtml}</td>
            <td>${selectHtml}</td>
            <td class="tx-amount amount-expense">${formatCurrency(tx.amount)}</td>
        `;
        
        listContainer.appendChild(row);
    });
}

// Altera a classificação de custo de uma despesa e aplica a atualização retrospectiva
async function changeCostType(transactionId, newCostType, btnElement) {
    const control = btnElement.parentElement;
    const buttons = control.querySelectorAll(".segmented-btn");
    buttons.forEach(b => b.classList.remove("active"));
    btnElement.classList.add("active");
    
    const formData = new FormData();
    formData.append("cost_type", newCostType);
    
    try {
        const response = await fetch(`/api/transaction/${transactionId}/cost_type`, {
            method: "POST",
            body: formData
        });
        
        if (response.ok) {
            // Recarrega todos os dados do dashboard para atualização dinâmica retrospectiva
            const responseData = await fetch("/api/data");
            const data = await responseData.json();
            allAccounts = data.accounts;
            
            // Recalcula e renderiza na tela
            processAndRenderCosts();
        } else {
            alert("Erro ao alterar classificação de custo.");
            loadCostsData();
        }
    } catch (err) {
        console.error("Erro ao alterar tipo de custo:", err);
        loadCostsData();
    }
}

// --- UTILITÁRIOS E TEMAS CLONADOS PARA SINCRONIZAÇÃO PERFEITA ---

function setupResponsiveMenuAndThemes() {
    const mobileMenuBtn = document.getElementById("mobileMenuBtn");
    const closeSidebarBtn = document.getElementById("closeSidebarBtn");
    const sidebarOverlay = document.getElementById("sidebarOverlay");
    const dashboardSidebar = document.getElementById("dashboardSidebar");

    if (mobileMenuBtn && closeSidebarBtn && sidebarOverlay && dashboardSidebar) {
        const openSidebar = () => {
            dashboardSidebar.classList.add("active");
            sidebarOverlay.classList.add("active");
        };

        const closeSidebar = () => {
            dashboardSidebar.classList.remove("active");
            sidebarOverlay.classList.remove("active");
        };

        mobileMenuBtn.addEventListener("click", openSidebar);
        closeSidebarBtn.addEventListener("click", closeSidebar);
        sidebarOverlay.addEventListener("click", closeSidebar);

        const navLinks = document.querySelectorAll(".nav-item a");
        navLinks.forEach(link => {
            link.addEventListener("click", closeSidebar);
        });
    }

    const mobileThemeToggle = document.getElementById("mobileThemeToggleBtn");
    const desktopThemeToggle = document.getElementById("desktopThemeToggleBtn");

    function updateThemeIcons() {
        const isDark = document.body.classList.contains("dark-mode");
        const iconName = isDark ? "light_mode" : "dark_mode";
        
        const mobileIcon = document.getElementById("mobileThemeToggleIcon");
        const desktopIcon = document.getElementById("desktopThemeToggleIcon");
        
        if (mobileIcon) mobileIcon.innerText = iconName;
        if (desktopIcon) desktopIcon.innerText = iconName;
    }

    updateThemeIcons();

    const toggleTheme = () => {
        document.body.classList.toggle("dark-mode");
        const isDark = document.body.classList.contains("dark-mode");
        localStorage.setItem("theme", isDark ? "dark" : "light");
        updateThemeIcons();
        
        // Notifica o arquivo de custos para recalcular
        processAndRenderCosts();
    };

    if (mobileThemeToggle) {
        mobileThemeToggle.addEventListener("click", toggleTheme);
    }
    if (desktopThemeToggle) {
        desktopThemeToggle.addEventListener("click", toggleTheme);
    }
}

function formatCurrency(value) {
    return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL"
    }).format(value);
}

function parseDateStr(dateStr) {
    const parts = dateStr.split("/");
    return new Date(parts[2], parts[1] - 1, parts[0]);
}

// Altera a categoria de uma despesa e recalcula os totais
async function changeCategory(transactionId, newCategory) {
    const formData = new FormData();
    formData.append("category", newCategory);
    
    try {
        const response = await fetch(`/api/transaction/${transactionId}/category`, {
            method: "POST",
            body: formData
        });
        if (response.ok) {
            // Atualiza os dados locais e re-renderiza
            const responseData = await fetch("/api/data");
            const data = await responseData.json();
            allAccounts = data.accounts;
            processAndRenderCosts();
        }
    } catch (err) {
        console.error("Erro ao alterar categoria:", err);
    }
}

// Ouvinte reativo para atualização dinâmica de categorias
document.addEventListener("categoriesUpdated", (e) => {
    CATEGORIES = e.detail;
    if (allAccounts.length > 0) {
        processAndRenderCosts();
    }
});
