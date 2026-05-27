// Estado global da página de receitas
let allAccounts = [];
let futureIncomes = [];
let CATEGORIES = ["Receita", "Transporte", "Lazer", "Serviços & Assinaturas", "Saúde", "Outros", "Loteria", "Mercado", "Restaurante & Delivery", "Pagamento de Fatura", "Moradia & Contas"];

document.addEventListener("DOMContentLoaded", () => {
    // Carrega dados iniciais da tela
    loadReceitasData();
    // Configura o menu responsivo e alternadores de temas
    setupResponsiveMenuAndThemes();
    // Configura os ouvintes dos filtros
    setupFilters();
    // Configura eventos de formulário de receitas estimadas
    setupFutureIncomeEvents();
    // Ouve atualizações de categorias globais do modal
    document.addEventListener("categoriesUpdated", (e) => {
        if (e.detail) {
            CATEGORIES = e.detail;
            populateCategoryFilter();
            processAndRenderReceitas();
        }
    });
});

async function loadReceitasData() {
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
        
        // Busca Receitas Estimadas / Futuras
        await fetchFutureIncomes();
        
        // Renderiza e calcula receitas
        processAndRenderReceitas();
        
    } catch (err) {
        console.error("Erro ao carregar dados de receitas:", err);
    }
}

async function fetchFutureIncomes() {
    try {
        const response = await fetch("/api/future-incomes");
        if (response.ok) {
            futureIncomes = await response.json();
            renderFutureIncomesList();
        }
    } catch (err) {
        console.error("Erro ao carregar receitas estimadas:", err);
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

    // 4. Popula Categorias
    populateCategoryFilter();
}

function populateCategoryFilter() {
    const categoryFilter = document.getElementById("categoryFilter");
    if (categoryFilter) {
        categoryFilter.innerHTML = '<option value="all">Todas as Categorias</option>';
        let uniqueCategories = new Set();
        allAccounts.forEach(acc => {
            acc.transactions.forEach(tx => {
                if (tx.amount > 0 && tx.category) {
                    uniqueCategories.add(tx.category);
                }
            });
        });
        
        CATEGORIES.forEach(cat => {
            uniqueCategories.add(cat);
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
            
            document.getElementById("startDateFilter").value = "";
            document.getElementById("endDateFilter").value = "";
        } else {
            dmaGroups.forEach(el => el.style.display = "none");
            rangeGroups.forEach(el => el.style.display = "flex");
            
            document.getElementById("dayFilter").value = "all";
            document.getElementById("monthFilter").value = "all";
            document.getElementById("yearFilter").value = "all";
        }
        processAndRenderReceitas();
    });
    
    // Vincula todos os demais filtros de dropdown e input
    const filterIds = [
        "accountFilter", "dayFilter", "monthFilter", "yearFilter",
        "startDateFilter", "endDateFilter", "categoryFilter", "searchInput"
    ];
    
    filterIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("change", processAndRenderReceitas);
            el.addEventListener("input", processAndRenderReceitas);
        }
    });
}

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

function processAndRenderReceitas() {
    const accountFilterValue = document.getElementById("accountFilter").value;
    const categoryFilterValue = document.getElementById("categoryFilter").value;
    
    let realizedReceitas = [];
    
    // 1. Coleta todas as transações com amount > 0
    allAccounts.forEach(acc => {
        if (accountFilterValue !== "all" && accountFilterValue !== acc.id.toString()) {
            return;
        }
        
        acc.transactions.forEach(tx => {
            if (tx.amount > 0) {
                realizedReceitas.push({
                    ...tx,
                    accountId: acc.id,
                    bankName: acc.bank_name
                });
            }
        });
    });
    
    // 2. Filtra por data
    realizedReceitas = realizedReceitas.filter(tx => filterByDate(tx.date));
    
    // 3. Filtra por Categoria
    if (categoryFilterValue !== "all") {
        realizedReceitas = realizedReceitas.filter(tx => tx.category === categoryFilterValue);
    }
    
    // 4. Filtra por busca de nome
    const searchVal = document.getElementById("searchInput").value.trim().toLowerCase();
    if (searchVal) {
        realizedReceitas = realizedReceitas.filter(tx => tx.description.toLowerCase().includes(searchVal));
    }
    
    // Ordena do mais recente ao mais antigo
    realizedReceitas.sort((a, b) => parseDateStr(b.date) - parseDateStr(a.date));
    
    // 5. Calcula Totais
    let totalRealized = 0;
    realizedReceitas.forEach(r => {
        totalRealized += r.amount;
    });
    
    let totalEstimated = 0;
    futureIncomes.forEach(inc => {
        totalEstimated += inc.amount;
    });
    
    // Aproveitamento (Realized vs Estimated Ratio)
    let achievementPct = 0;
    if (totalEstimated > 0) {
        achievementPct = Math.min(100, Math.round((totalRealized / totalEstimated) * 100));
    } else if (totalRealized > 0) {
        achievementPct = 100;
    }
    
    // Atualiza os cards KPIs
    document.getElementById("totalRealizedDisplay").innerText = formatCurrency(totalRealized);
    document.getElementById("totalEstimatedDisplay").innerText = formatCurrency(totalEstimated);
    document.getElementById("achievementDisplay").innerText = `${achievementPct}%`;
    document.getElementById("revenueStreamsDisplay").innerText = `${futureIncomes.length} ${futureIncomes.length === 1 ? 'Fonte' : 'Fontes'}`;
    
    // Atualiza barra de progresso do aproveitamento
    const progressBar = document.getElementById("achievementBar");
    if (progressBar) {
        progressBar.style.width = `${achievementPct}%`;
        if (achievementPct >= 100) {
            progressBar.style.backgroundColor = "var(--md-sys-color-income)";
        } else if (achievementPct >= 50) {
            progressBar.style.backgroundColor = "var(--md-sys-color-primary)";
        } else {
            progressBar.style.backgroundColor = "#FF7A00";
        }
    }
    
    // Renderiza a tabela de receitas realizadas
    renderRealizedTable(realizedReceitas);
}

function renderRealizedTable(realized) {
    const list = document.getElementById("receitasRealizadasList");
    list.innerHTML = "";
    
    if (realized.length === 0) {
        list.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--md-sys-color-outline); padding: 32px;">
                    Nenhuma receita encontrada para os filtros selecionados.
                </td>
            </tr>
        `;
        return;
    }
    
    realized.forEach(tx => {
        const row = document.createElement("tr");
        row.className = "tx-row";
        
        let bankBadgeClass = "badge-bank-default";
        if (tx.bankName.toLowerCase().includes("nubank")) {
            bankBadgeClass = "badge-bank-nubank";
        } else if (tx.bankName.toLowerCase().includes("inter")) {
            bankBadgeClass = "badge-bank-inter";
        } else if (tx.bankName.toLowerCase().includes("caixa")) {
            bankBadgeClass = "badge-bank-caixa";
        }
        const bankBadgeHtml = `<span class="badge-bank ${bankBadgeClass}">${tx.bankName}</span>`;
        
        let typeBadge = "";
        if (tx.type === "PIX_RECEBIDO") {
            typeBadge = `<span class="badge-pix" style="background: var(--md-sys-color-primary-container); color: var(--md-sys-color-on-primary-container);">PIX In</span> `;
        } else if (tx.type === "CREDIT") {
            typeBadge = `<span class="badge-pix" style="background: #E8F5E9; color: #2E7D32;">CRÉDITO</span> `;
        }
        
        // Caixa de seleção de categorias
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
            <td>${selectHtml}</td>
            <td class="tx-amount amount-income" style="font-weight: 600; text-align: right;">${formatCurrency(tx.amount)}</td>
        `;
        
        list.appendChild(row);
    });
}

function renderFutureIncomesList() {
    const list = document.getElementById("incomesList");
    list.innerHTML = "";
    
    if (futureIncomes.length === 0) {
        list.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--md-sys-color-outline); padding: 24px;">
                    Nenhuma receita estimada futura. Cadastre agora!
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
            <td style="font-weight: 600; color: var(--md-sys-color-income); text-align: right;">${formatCurrency(inc.amount)}</td>
            <td style="text-align: right;">
                <button onclick="deleteIncome(${inc.id}, '${inc.description}')" style="background: none; border: none; color: var(--md-sys-color-error); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 4px;">
                    <span class="material-symbols-outlined" style="font-size: 18px;">delete</span>
                </button>
            </td>
        `;
        list.appendChild(row);
    });
}

// Altera a categoria de uma receita e atualiza
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
            allAccounts.forEach(acc => {
                acc.transactions.forEach(t => {
                    if (t.id === transactionId) {
                        t.category = newCategory;
                    }
                });
            });
            processAndRenderReceitas();
        } else {
            console.error("Erro ao alterar categoria da transação.");
        }
    } catch (err) {
        console.error("Erro ao fazer requisição de categoria:", err);
    }
}

// Exclui receita estimada futura
async function deleteIncome(id, desc) {
    if (!confirm(`Deseja excluir a receita estimada "${desc}"?`)) return;
    
    try {
        const response = await fetch(`/api/future-incomes/${id}`, {
            method: "DELETE"
        });
        if (response.ok) {
            await fetchFutureIncomes();
            processAndRenderReceitas();
        }
    } catch (err) {
        console.error("Erro ao deletar receita estimada:", err);
    }
}

function setupFutureIncomeEvents() {
    const openModalBtn = document.getElementById("openIncomeModalBtn");
    const closeModalBtn = document.getElementById("closeIncomeModalBtn");
    const modalOverlay = document.getElementById("modalOverlayIncome");
    const newIncomeModal = document.getElementById("newIncomeModal");
    const newIncomeForm = document.getElementById("newIncomeForm");
    
    if (openModalBtn && closeModalBtn && modalOverlay && newIncomeModal) {
        const openModal = () => {
            newIncomeModal.classList.add("active");
            modalOverlay.classList.add("active");
            
            // Define data atual default no formulário de cadastro (YYYY-MM-DD)
            const today = new Date();
            const yyyy = today.getFullYear();
            const mm = String(today.getMonth() + 1).padStart(2, '0');
            const dd = String(today.getDate()).padStart(2, '0');
            document.getElementById("incomeStartDate").value = `${yyyy}-${mm}-${dd}`;
        };
        
        const closeModal = () => {
            newIncomeModal.classList.remove("active");
            modalOverlay.classList.remove("active");
            newIncomeForm.reset();
        };
        
        openModalBtn.addEventListener("click", openModal);
        closeModalBtn.addEventListener("click", closeModal);
        modalOverlay.addEventListener("click", closeModal);
        
        // Envio do formulário
        newIncomeForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            
            const description = document.getElementById("incomeDescription").value.trim();
            const amount = parseFloat(document.getElementById("incomeAmount").value);
            const receiveDay = parseInt(document.getElementById("incomeDay").value, 10);
            const isRecurrent = document.getElementById("incomeRecurrent").value === "true";
            const startDate = document.getElementById("incomeStartDate").value;
            
            const formData = new FormData();
            formData.append("description", description);
            formData.append("amount", amount);
            formData.append("receive_day", receiveDay);
            formData.append("is_recurrent", isRecurrent);
            formData.append("start_date", startDate);
            
            try {
                const response = await fetch("/api/future-incomes", {
                    method: "POST",
                    body: formData
                });
                
                const res = await response.json();
                if (response.ok) {
                    closeModal();
                    await fetchFutureIncomes();
                    processAndRenderReceitas();
                } else {
                    alert("Erro ao cadastrar: " + res.detail);
                }
            } catch (err) {
                console.error("Erro ao cadastrar receita estimada:", err);
            }
        });
    }
}

// Utilitários de Formatação
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
    };

    if (mobileThemeToggle) mobileThemeToggle.addEventListener("click", toggleTheme);
    if (desktopThemeToggle) desktopThemeToggle.addEventListener("click", toggleTheme);
}
