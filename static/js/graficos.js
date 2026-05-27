// Estado global da página de gráficos
let allAccounts = [];
let categoryChartInstance = null;
let flowChartInstance = null;
let costChartInstance = null;

// Formatos selecionados por padrão
let categoryChartType = "doughnut";
let flowChartType = "line";
let costChartType = "doughnut";

document.addEventListener("DOMContentLoaded", () => {
    // Carrega dados iniciais
    loadChartsData();
    // Configura o menu responsivo e alternadores de temas
    setupResponsiveMenuAndThemes();
    // Configura os ouvintes dos filtros superiores
    setupFilters();
    // Configura os ouvintes dos botões segmentados de formato
    setupFormatControls();
});

async function loadChartsData() {
    try {
        const response = await fetch("/api/data");
        if (response.status === 401) {
            window.location.href = "/login";
            return;
        }
        
        const data = await response.json();
        allAccounts = data.accounts;
        
        // Atualiza nome na sidebar
        document.getElementById("userNameDisplay").innerText = data.user_name;
        
        // Inicializa os dropdowns de filtros
        initializeDynamicFilters();
        
        // Gera todos os gráficos com base nos filtros atuais
        renderAllCharts();
        
    } catch (err) {
        console.error("Erro ao carregar dados de gráficos:", err);
    }
}

function initializeDynamicFilters() {
    const accountFilter = document.getElementById("accountFilter");
    const periodFilter = document.getElementById("periodFilter");
    
    accountFilter.innerHTML = '<option value="all">Todas as Contas</option>';
    periodFilter.innerHTML = '<option value="all">Todos os Meses</option>';
    
    // Popula contas
    allAccounts.forEach(acc => {
        const opt = document.createElement("option");
        opt.value = acc.id;
        opt.innerText = acc.bank_name;
        accountFilter.appendChild(opt);
    });
    
    // Popula períodos únicos
    let periods = new Set();
    allAccounts.forEach(acc => {
        acc.transactions.forEach(tx => {
            const parts = tx.date.split("/");
            const monthYear = `${parts[1]}/${parts[2]}`;
            periods.add(monthYear);
        });
    });
    
    const sortedPeriods = Array.from(periods).sort((a, b) => {
        const partsA = a.split("/");
        const partsB = b.split("/");
        const dateA = new Date(partsA[1], partsA[0] - 1);
        const dateB = new Date(partsB[1], partsB[0] - 1);
        return dateB - dateA;
    });
    
    sortedPeriods.forEach(p => {
        const opt = document.createElement("option");
        opt.value = p;
        opt.innerText = formatPeriod(p);
        periodFilter.appendChild(opt);
    });
}

function formatPeriod(periodStr) {
    const parts = periodStr.split("/");
    const months = [
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"
    ];
    return `${months[parseInt(parts[0], 10) - 1]} de ${parts[1]}`;
}

function setupFilters() {
    document.getElementById("accountFilter").addEventListener("change", renderAllCharts);
    document.getElementById("periodFilter").addEventListener("change", renderAllCharts);
}

function setupFormatControls() {
    // 1. Controle de Categorias
    const catBtns = document.querySelectorAll("#categoryFormatControl .segmented-btn");
    catBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            catBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            categoryChartType = btn.getAttribute("data-type");
            renderCategoryChart();
        });
    });

    // 2. Controle de Fluxo
    const flowBtns = document.querySelectorAll("#flowFormatControl .segmented-btn");
    flowBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            flowBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            flowChartType = btn.getAttribute("data-type");
            renderFlowChart();
        });
    });

    // 3. Controle de Custos Fixos vs Variáveis
    const costBtns = document.querySelectorAll("#costFormatControl .segmented-btn");
    costBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            costBtns.forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            costChartType = btn.getAttribute("data-type");
            renderCostTypeChart();
        });
    });
}

// Filtra as transações consolidando-as em uma lista única
function getFilteredTransactions() {
    const accountFilterValue = document.getElementById("accountFilter").value;
    const periodFilterValue = document.getElementById("periodFilter").value;
    
    let list = [];
    allAccounts.forEach(acc => {
        if (accountFilterValue !== "all" && accountFilterValue !== acc.id.toString()) {
            return;
        }
        
        acc.transactions.forEach(tx => {
            list.push({
                ...tx,
                bankName: acc.bank_name
            });
        });
    });
    
    if (periodFilterValue !== "all") {
        list = list.filter(tx => {
            const parts = tx.date.split("/");
            const monthYear = `${parts[1]}/${parts[2]}`;
            return monthYear === periodFilterValue;
        });
    }
    
    return list;
}

// Configura as opções estéticas gerais baseadas no tema dark/light
function getChartThemeOptions() {
    const isDark = document.body.classList.contains("dark-mode");
    return {
        isDark,
        textColor: isDark ? "#cbd5e1" : "#1e293b",
        borderColor: isDark ? "#2a2c35" : "#ffffff",
        gridColor: isDark ? "rgba(255, 255, 255, 0.08)" : "rgba(0, 0, 0, 0.05)"
    };
}

function renderAllCharts() {
    renderCategoryChart();
    renderFlowChart();
    renderCostTypeChart();
}

// --- RENDERS INDIVIDUAIS DOS GRÁFICOS ---

// Gráfico 1: Despesas por Categoria
function renderCategoryChart() {
    const txs = getFilteredTransactions();
    const theme = getChartThemeOptions();
    const ctx = document.getElementById("categoryChart").getContext("2d");
    
    if (categoryChartInstance) {
        categoryChartInstance.destroy();
    }
    
    // Agrupa despesas por categoria
    let categories = {};
    txs.forEach(t => {
        if (t.amount < 0) {
            const cat = t.category;
            const absVal = Math.abs(t.amount);
            categories[cat] = (categories[cat] || 0) + absVal;
        }
    });
    
    const labels = Object.keys(categories);
    const dataValues = Object.values(categories);
    
    if (labels.length === 0) {
        categoryChartInstance = null;
        ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
        return;
    }
    
    const colors = ["#48b9c7", "#008080", "#BA1A1A", "#006E3C", "#FF7A00", "#820AD1", "#64748b"];
    
    categoryChartInstance = new Chart(ctx, {
        type: categoryChartType,
        data: {
            labels: labels,
            datasets: [{
                data: dataValues,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: theme.borderColor
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "bottom",
                    labels: {
                        color: theme.textColor,
                        font: { family: "Inter", weight: "500" },
                        padding: 16
                    }
                }
            },
            cutout: categoryChartType === "doughnut" ? "70%" : undefined
        }
    });
}

// Gráfico 2: Evolução de Saldo ou Entradas vs Saídas
function renderFlowChart() {
    const txs = getFilteredTransactions();
    const theme = getChartThemeOptions();
    const ctx = document.getElementById("evolutionChart").getContext("2d");
    
    if (flowChartInstance) {
        flowChartInstance.destroy();
    }
    
    // Ordena as transações cronologicamente (da mais antiga para a mais recente)
    txs.sort((a, b) => parseDateStr(a.date) - parseDateStr(b.date));
    
    if (txs.length === 0) {
        flowChartInstance = null;
        return;
    }
    
    if (flowChartType === "line") {
        // --- MODO LINHA: Evolução de Saldo Consolidado ---
        // Começa com a soma dos saldos iniciais das contas consideradas
        const accountFilterValue = document.getElementById("accountFilter").value;
        let runningBalance = allAccounts
            .filter(acc => accountFilterValue === "all" || accountFilterValue === acc.id.toString())
            .reduce((total, acc) => total + (acc.initial_balance || 0), 0);
            
        let balancePoints = [];
        let dateLabels = [];
        
        txs.forEach(t => {
            runningBalance += t.amount;
            const lastIdx = dateLabels.length - 1;
            if (lastIdx >= 0 && dateLabels[lastIdx] === t.date) {
                balancePoints[lastIdx] = runningBalance;
            } else {
                dateLabels.push(t.date);
                balancePoints.push(runningBalance);
            }
        });
        
        flowChartInstance = new Chart(ctx, {
            type: "line",
            data: {
                labels: dateLabels,
                datasets: [{
                    label: "Saldo Consolidado (R$)",
                    data: balancePoints,
                    borderColor: "#48b9c7",
                    backgroundColor: "rgba(72, 185, 199, 0.12)",
                    fill: true,
                    tension: 0.3,
                    borderWidth: 3,
                    pointRadius: 4,
                    pointBackgroundColor: "#48b9c7"
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: theme.textColor, font: { family: "Inter" } }
                    },
                    y: {
                        grid: { color: theme.gridColor },
                        ticks: { color: theme.textColor, font: { family: "Inter" } }
                    }
                }
            }
        });
        
    } else {
        // --- MODO BARRAS: Receitas vs Despesas (Agrupado por Dia/Mês) ---
        // Agrupa por dia para simplificar
        let datesMap = {};
        txs.forEach(t => {
            if (!datesMap[t.date]) {
                datesMap[t.date] = { income: 0, expense: 0 };
            }
            if (t.amount > 0) {
                datesMap[t.date].income += t.amount;
            } else {
                datesMap[t.date].expense += Math.abs(t.amount);
            }
        });
        
        const dates = Object.keys(datesMap);
        const incomes = dates.map(d => datesMap[d].income);
        const expenses = dates.map(d => datesMap[d].expense);
        
        flowChartInstance = new Chart(ctx, {
            type: "bar",
            data: {
                labels: dates,
                datasets: [
                    {
                        label: "Receitas",
                        data: incomes,
                        backgroundColor: "#006E3C",
                        borderRadius: 6
                    },
                    {
                        label: "Despesas",
                        data: expenses,
                        backgroundColor: "#BA1A1A",
                        borderRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: { color: theme.textColor, font: { family: "Inter", weight: "500" } }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: theme.textColor, font: { family: "Inter" } }
                    },
                    y: {
                        grid: { color: theme.gridColor },
                        ticks: { color: theme.textColor, font: { family: "Inter" } }
                    }
                }
            }
        });
    }
}

// Gráfico 3: Custos Fixos vs Variáveis
function renderCostTypeChart() {
    const txs = getFilteredTransactions();
    const theme = getChartThemeOptions();
    const ctx = document.getElementById("costTypeChart").getContext("2d");
    
    if (costChartInstance) {
        costChartInstance.destroy();
    }
    
    let totalFixed = 0;
    let totalVariable = 0;
    
    txs.forEach(t => {
        if (t.amount < 0) {
            const absVal = Math.abs(t.amount);
            if (t.cost_type === "fixo") {
                totalFixed += absVal;
            } else {
                totalVariable += absVal;
            }
        }
    });
    
    if (totalFixed === 0 && totalVariable === 0) {
        costChartInstance = null;
        return;
    }
    
    const labels = ["Custos Fixos", "Custos Variáveis"];
    const values = [totalFixed, totalVariable];
    
    const colors = ["#48b9c7", "#ff7a00"];
    
    if (costChartType === "doughnut") {
        costChartInstance = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: colors,
                    borderWidth: 2,
                    borderColor: theme.borderColor
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            color: theme.textColor,
                            font: { family: "Inter", weight: "500" },
                            padding: 16
                        }
                    }
                },
                cutout: "70%"
            }
        });
    } else {
        // Horizontal Bar
        costChartInstance = new Chart(ctx, {
            type: "bar",
            data: {
                labels: ["Custos"],
                datasets: [
                    {
                        label: "Custos Fixos",
                        data: [totalFixed],
                        backgroundColor: "#48b9c7",
                        borderRadius: 6
                    },
                    {
                        label: "Custos Variáveis",
                        data: [totalVariable],
                        backgroundColor: "#ff7a00",
                        borderRadius: 6
                    }
                ]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: { color: theme.textColor, font: { family: "Inter", weight: "500" } }
                    }
                },
                scales: {
                    x: {
                        grid: { color: theme.gridColor },
                        ticks: { color: theme.textColor, font: { family: "Inter" } }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { color: theme.textColor, font: { family: "Inter" } }
                    }
                }
            }
        });
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
        
        // Atualiza a renderização de todos os gráficos instantaneamente para aplicar a nova paleta
        renderAllCharts();
    };

    if (mobileThemeToggle) {
        mobileThemeToggle.addEventListener("click", toggleTheme);
    }
    if (desktopThemeToggle) {
        desktopThemeToggle.addEventListener("click", toggleTheme);
    }
}

function parseDateStr(dateStr) {
    const parts = dateStr.split("/");
    return new Date(parts[2], parts[1] - 1, parts[0]);
}
