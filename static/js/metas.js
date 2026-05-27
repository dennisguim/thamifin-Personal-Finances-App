let projectionChartInstance = null;

// Dados globais da simulação carregados do backend
let currentBalance = 0.0;
let historicalAverageExpenses = 2000.0;
let installmentsProjection = [];
let futureIncomes = [];
let financialGoals = [];

document.addEventListener("DOMContentLoaded", () => {
    // Carrega dados iniciais da tela
    loadProjectionData();
    // Configura o menu responsivo e temas
    setupResponsiveMenuAndThemes();
    // Configura eventos da tela
    setupProjectionEvents();
});

async function loadProjectionData() {
    try {
        // 1. Busca dados de simulação basilar
        const simRes = await fetch("/api/simulation/projection");
        if (simRes.status === 401) {
            window.location.href = "/login";
            return;
        }
        const simData = await simRes.json();
        
        currentBalance = simData.current_balance;
        historicalAverageExpenses = simData.average_expenses;
        installmentsProjection = simData.installments_projection;
        
        // Inicializa o slider se for a primeira vez
        const slider = document.getElementById("expenseSlider");
        if (!slider.value || slider.value == 50) { // Valor default não inicializado
            slider.value = Math.round(historicalAverageExpenses);
            document.getElementById("historicalAvgMarker").innerText = `Média Real: ${formatCurrency(historicalAverageExpenses)}`;
        }
        
        document.getElementById("sliderValueText").innerText = formatCurrency(slider.value);
        
        // 2. Busca Receitas Futuras e Metas
        await fetchIncomes();
        await fetchGoals();
        
        // 3. Executa a projeção e desenha o gráfico
        calculateAndRenderProjection();
        
    } catch (err) {
        console.error("Erro ao carregar dados de projeção:", err);
    }
}

async function fetchIncomes() {
    try {
        const response = await fetch("/api/future-incomes");
        if (response.ok) {
            futureIncomes = await response.json();
            renderIncomesList();
        }
    } catch (err) {
        console.error("Erro ao carregar receitas estimadas:", err);
    }
}

async function fetchGoals() {
    try {
        const response = await fetch("/api/financial-goals");
        if (response.ok) {
            financialGoals = await response.json();
        }
    } catch (err) {
        console.error("Erro ao carregar objetivos:", err);
    }
}

function renderIncomesList() {
    const list = document.getElementById("incomesList");
    list.innerHTML = "";

    if (futureIncomes.length === 0) {
        list.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--md-sys-color-outline); padding: 24px;">
                    Nenhuma receita futura estimada. Cadastre acima!
                </td>
            </tr>
        `;
        return;
    }

    futureIncomes.forEach(inc => {
        const row = document.createElement("tr");
        
        const typeText = inc.is_recurrent ? "Mensal" : "Único";
        const dateObj = new Date(inc.start_date + "T00:00:00");
        const formattedDate = dateObj.toLocaleDateString("pt-BR", { month: "short", year: "2-digit" });

        row.innerHTML = `
            <td style="font-weight: 600;">${inc.description}</td>
            <td><span class="badge-pix" style="background: var(--md-sys-color-primary-container); color: var(--md-sys-color-on-primary-container); padding: 2px 8px; font-size: 11px;">${typeText}</span></td>
            <td>Dia ${inc.receive_day} (${formattedDate})</td>
            <td style="font-weight: 600; color: var(--md-sys-color-income);">${formatCurrency(inc.amount)}</td>
            <td style="text-align: right;">
                <button onclick="deleteIncome(${inc.id}, '${inc.description}')" style="background: none; border: none; color: var(--md-sys-color-error); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 4px;">
                    <span class="material-symbols-outlined" style="font-size: 18px;">delete</span>
                </button>
            </td>
        `;
        list.appendChild(row);
    });
}

async function deleteIncome(id, desc) {
    if (!confirm(`Deseja excluir a receita estimada "${desc}"?`)) return;
    
    try {
        const response = await fetch(`/api/future-incomes/${id}`, {
            method: "DELETE"
        });
        if (response.ok) {
            await fetchIncomes();
            calculateAndRenderProjection();
        }
    } catch (err) {
        console.error("Erro ao deletar receita:", err);
    }
}

async function deleteGoal(id, name) {
    if (!confirm(`Deseja excluir o objetivo "${name}"?`)) return;
    
    try {
        const response = await fetch(`/api/financial-goals/${id}`, {
            method: "DELETE"
        });
        if (response.ok) {
            await fetchGoals();
            calculateAndRenderProjection();
        }
    } catch (err) {
        console.error("Erro ao deletar objetivo:", err);
    }
}

// EXECUTA O CÁLCULO MÊS A MÊS DA PROJEÇÃO E CONSTRUÇÃO DOS GRAFICOS
function calculateAndRenderProjection() {
    const sliderValue = parseFloat(document.getElementById("expenseSlider").value);
    
    const projectionMonths = 24;
    const projectedBalances = [];
    const labels = [];
    
    const startDate = new Date();
    let rollingBalance = currentBalance;
    
    // Lista de receitas e despesas estimadas por mês
    const monthProjections = [];
    
    // 1. Calcula as receitas e despesas de cada um dos próximos 24 meses
    for (let i = 0; i < projectionMonths; i++) {
        const projectedMonth = new Date(startDate.getFullYear(), startDate.getMonth() + i, 1);
        const year = projectedMonth.getFullYear();
        const monthIndex = projectedMonth.getMonth();
        
        // Label do mês no formato "Jun/26"
        const monthLabel = projectedMonth.toLocaleDateString("pt-BR", { month: "short", year: "2-digit" });
        labels.push(monthLabel);
        
        // A. Soma Receitas do Mês i
        let monthIncome = 0.0;
        futureIncomes.forEach(inc => {
            const incStart = new Date(inc.start_date + "T00:00:00");
            const startYear = incStart.getFullYear();
            const startMonth = incStart.getMonth();
            
            if (inc.is_recurrent) {
                // Se é recorrente, aplica se o mês projetado for igual ou maior que a data de início
                if (projectedMonth >= new Date(startYear, startMonth, 1)) {
                    monthIncome += inc.amount;
                }
            } else {
                // Se é pontual, aplica apenas no mês correspondente
                if (year === startYear && monthIndex === startMonth) {
                    monthIncome += inc.amount;
                }
            }
        });
        
        // B. Soma Despesas do Mês i
        const monthlyVariableExpense = sliderValue;
        const installmentExpense = installmentsProjection[i] || 0.0;
        const monthExpense = monthlyVariableExpense + installmentExpense;
        
        // C. Atualiza o saldo corrido
        rollingBalance = rollingBalance + monthIncome - monthExpense;
        projectedBalances.push(rollingBalance);
        
        monthProjections.push({
            date: new Date(year, monthIndex, 28), // Fim do mês para cálculos de metas
            balance: rollingBalance,
            saving: monthIncome - monthExpense
        });
    }
    
    // --- CÁLCULO E PROCESSO DE METAS ---
    let goalsMetCount = 0;
    const goalsContainer = document.getElementById("goalsGrid");
    goalsContainer.innerHTML = "";
    
    // Marcadores dinâmicos para colocar no Chart.js
    const chartAnnotations = [];
    
    financialGoals.forEach(goal => {
        const goalTargetDate = new Date(goal.target_date + "T00:00:00");
        
        // Encontra o primeiro mês onde o saldo acumulado é maior ou igual à meta
        let metMonthIndex = -1;
        for (let i = 0; i < projectionMonths; i++) {
            if (projectedBalances[i] >= goal.target_amount) {
                metMonthIndex = i;
                break;
            }
        }
        
        let statusText = "";
        let statusClass = "goal-status-pending";
        let onTime = false;
        let metDateStr = "";
        
        if (metMonthIndex !== -1) {
            const metMonthDate = new Date(startDate.getFullYear(), startDate.getMonth() + metMonthIndex, 28);
            metDateStr = metMonthDate.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
            
            if (metMonthDate <= goalTargetDate) {
                statusText = `Alcançável em ${metDateStr} (No prazo! 🎉)`;
                statusClass = "goal-status-on-time";
                onTime = true;
                goalsMetCount++;
            } else {
                statusText = `Alcançável em ${metDateStr} (Fora do prazo desejado ⚠️)`;
                statusClass = "goal-status-delayed";
            }
            
            // Adiciona anotação no gráfico
            chartAnnotations.push({
                x: labels[metMonthIndex],
                y: goal.target_amount,
                label: goal.name
            });
        } else {
            statusText = "Não alcançável nos próximos 24 meses. Aumente sua poupança!";
            statusClass = "goal-status-failed";
        }
        
        // Progresso circular/percentual baseado no saldo atual
        const percent = Math.min(100, Math.max(0, (projectedBalances[0] / goal.target_amount) * 100)).toFixed(0);
        
        let categoryIcon = "military_tech";
        if (goal.category.toLowerCase().includes("lazer")) categoryIcon = "flight_takeoff";
        else if (goal.category.toLowerCase().includes("bem")) categoryIcon = "directions_car";
        else if (goal.category.toLowerCase().includes("mora")) categoryIcon = "home";
        else if (goal.category.toLowerCase().includes("invest")) categoryIcon = "savings";

        const card = document.createElement("div");
        card.className = `m3-card goal-render-card ${onTime ? 'card-goal-active' : ''}`;
        card.style.padding = "16px";
        card.style.borderLeft = `5px solid ${onTime ? 'var(--md-sys-color-secondary)' : '#FF7A00'}`;
        card.style.display = "flex";
        card.style.flexDirection = "column";
        card.style.justifyContent = "space-between";
        card.style.gap = "12px";
        
        card.innerHTML = `
            <div>
                <div class="card-header-bank" style="margin-bottom: 4px;">
                    <h4 style="font-weight: 600; margin: 0; font-size: 15px;">${goal.name}</h4>
                    <button onclick="deleteGoal(${goal.id}, '${goal.name}')" style="background: none; border: none; color: var(--md-sys-color-error); cursor: pointer; padding: 4px;">
                        <span class="material-symbols-outlined" style="font-size: 18px;">delete</span>
                    </button>
                </div>
                
                <div style="display: flex; gap: 6px; align-items: center; margin-bottom: 8px;">
                    <span class="badge-pix" style="background: var(--md-sys-color-surface-container-high); color: var(--md-sys-color-on-surface); font-size: 10px; display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px;">
                        <span class="material-symbols-outlined" style="font-size: 12px;">${categoryIcon}</span>
                        ${goal.category}
                    </span>
                    <span class="badge-pix" style="background: var(--md-sys-color-primary-container); color: var(--md-sys-color-on-primary-container); font-size: 10px; padding: 2px 8px;">
                        Meta: ${formatCurrency(goal.target_amount)}
                    </span>
                </div>
                
                <div style="font-size: 12px; color: var(--md-sys-color-outline); font-weight: 500; margin-bottom: 4px;">
                    Prazo desejado: ${new Date(goal.target_date + "T00:00:00").toLocaleDateString("pt-BR")}
                </div>
            </div>
            
            <div style="border-top: 1px solid var(--md-sys-color-outline-variant); padding-top: 8px;">
                <div class="${statusClass}" style="font-size: 12px; font-weight: 600; line-height: 1.4;">${statusText}</div>
                
                <!-- Barra de Progresso baseada no saldo de hoje -->
                <div style="margin-top: 8px;">
                    <div style="display: flex; justify-content: space-between; font-size: 11px; font-weight: 600; margin-bottom: 2px;">
                        <span>Coberto com poupança atual:</span>
                        <span>${percent}%</span>
                    </div>
                    <div style="width: 100%; height: 6px; background-color: var(--md-sys-color-surface-container-high); border-radius: 3px; overflow: hidden;">
                        <div style="width: ${percent}%; height: 100%; background-color: ${onTime ? 'var(--md-sys-color-secondary)' : '#FF7A00'}; border-radius: 3px;"></div>
                    </div>
                </div>
            </div>
        `;
        
        goalsContainer.appendChild(card);
    });
    
    // Atualiza KPIs da tela
    const currentIncomesTotal = futureIncomes
        .filter(inc => inc.is_recurrent)
        .reduce((sum, inc) => sum + inc.amount, 0.0);
        
    const estimatedSavings = currentIncomesTotal - sliderValue;
    
    document.getElementById("estimatedSavingsDisplay").innerText = formatCurrency(estimatedSavings);
    document.getElementById("twelveMonthBalanceDisplay").innerText = formatCurrency(projectedBalances[11] || 0.0);
    document.getElementById("goalsStatusDisplay").innerText = `${goalsMetCount} / ${financialGoals.length}`;
    
    // --- ATUALIZAÇÃO DO GRÁFICO (CHART.JS) ---
    renderChart(labels, projectedBalances, chartAnnotations);
}

function renderChart(labels, balances, annotations) {
    const ctx = document.getElementById("projectionChart").getContext("2d");
    
    if (projectionChartInstance) {
        projectionChartInstance.destroy();
    }
    
    const isDark = document.body.classList.contains("dark-mode");
    const textColor = isDark ? "#cbd5e1" : "#1e293b";
    const gridColor = isDark ? "rgba(255, 255, 255, 0.08)" : "rgba(0, 0, 0, 0.05)";
    
    projectionChartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [{
                label: "Saldo Acumulado Projetado",
                data: balances,
                borderColor: "#48b9c7",
                backgroundColor: "rgba(72, 185, 199, 0.1)",
                borderWidth: 3,
                fill: true,
                tension: 0.3,
                pointRadius: 4,
                pointBackgroundColor: "#008080"
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `Saldo: ${formatCurrency(context.parsed.y)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: gridColor
                    },
                    ticks: {
                        color: textColor,
                        font: { family: "Inter", size: 11, weight: "500" }
                    }
                },
                y: {
                    grid: {
                        color: gridColor
                    },
                    ticks: {
                        color: textColor,
                        font: { family: "Inter", size: 11, weight: "500" },
                        callback: function(value) {
                            return "R$ " + value.toLocaleString("pt-BR");
                        }
                    }
                }
            }
        }
    });
}

function setupProjectionEvents() {
    const slider = document.getElementById("expenseSlider");
    
    // Ao mover o slider, faz o cálculo e renderiza dinamicamente
    slider.addEventListener("input", (e) => {
        document.getElementById("sliderValueText").innerText = formatCurrency(e.target.value);
        calculateAndRenderProjection();
    });

    // --- MODAL DE RECEITA FUTURA ---
    const incomeModal = document.getElementById("newIncomeModal");
    const incomeOverlay = document.getElementById("modalOverlayIncome");
    const openIncBtn = document.getElementById("openIncomeModalBtn");
    const closeIncBtn = document.getElementById("closeIncomeModalBtn");
    const incForm = document.getElementById("newIncomeForm");

    openIncBtn.addEventListener("click", () => {
        incomeModal.classList.add("active");
        incomeOverlay.classList.add("active");
        incForm.reset();
        document.getElementById("incomeStartDate").value = new Date().toISOString().substring(0, 10);
    });

    const closeIncModal = () => {
        incomeModal.classList.remove("active");
        incomeOverlay.classList.remove("active");
    };

    closeIncBtn.addEventListener("click", closeIncModal);
    incomeOverlay.addEventListener("click", closeIncModal);

    incForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const formData = new FormData();
        formData.append("description", document.getElementById("incomeDescription").value);
        formData.append("amount", document.getElementById("incomeAmount").value);
        formData.append("is_recurrent", document.getElementById("incomeRecurrent").value);
        formData.append("receive_day", document.getElementById("incomeDay").value);
        formData.append("start_date", document.getElementById("incomeStartDate").value);

        try {
            const response = await fetch("/api/future-incomes", {
                method: "POST",
                body: formData
            });
            const res = await response.json();
            if (response.ok) {
                alert(res.message);
                closeIncModal();
                loadProjectionData();
            } else {
                alert("Erro ao cadastrar: " + res.detail);
            }
        } catch (err) {
            console.error(err);
        }
    });

    // --- MODAL DE META ---
    const goalModal = document.getElementById("newGoalModal");
    const goalOverlay = document.getElementById("modalOverlayGoal");
    const openGoalBtn = document.getElementById("openGoalModalBtn");
    const closeGoalBtn = document.getElementById("closeGoalModalBtn");
    const goalForm = document.getElementById("newGoalForm");

    openGoalBtn.addEventListener("click", () => {
        goalModal.classList.add("active");
        goalOverlay.classList.add("active");
        goalForm.reset();
        document.getElementById("goalTargetDate").value = new Date(new Date().getFullYear() + 1, new Date().getMonth(), 1).toISOString().substring(0, 10);
    });

    const closeGoalModal = () => {
        goalModal.classList.remove("active");
        goalOverlay.classList.remove("active");
    };

    closeGoalBtn.addEventListener("click", closeGoalModal);
    goalOverlay.addEventListener("click", closeGoalModal);

    goalForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const formData = new FormData();
        formData.append("name", document.getElementById("goalName").value);
        formData.append("target_amount", document.getElementById("goalTargetAmount").value);
        formData.append("target_date", document.getElementById("goalTargetDate").value);
        formData.append("category", document.getElementById("goalCategory").value);

        try {
            const response = await fetch("/api/financial-goals", {
                method: "POST",
                body: formData
            });
            const res = await response.json();
            if (response.ok) {
                alert(res.message);
                closeGoalModal();
                loadProjectionData();
            } else {
                alert("Erro ao cadastrar objetivo: " + res.detail);
            }
        } catch (err) {
            console.error(err);
        }
    });
}

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
        calculateAndRenderProjection();
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
