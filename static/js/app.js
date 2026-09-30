// Armazena as instâncias dos gráficos globalmente para podermos destruí-los/recriá-los ao atualizar dados
let categoryChartInstance = null;
let evolutionChartInstance = null;

// Categorias disponíveis para seleção manual (inicialmente padrão, atualizadas dinamicamente)
let CATEGORIES = ["Transporte", "Lazer", "Serviços & Assinaturas", "Saúde", "Receita", "Outros", "Loteria", "Mercado", "Restaurante & Delivery", "Pagamento de Fatura", "Moradia & Contas"];

document.addEventListener("DOMContentLoaded", () => {
    // Carrega dados iniciais do Dashboard
    loadDashboardData();
    // Configura o menu responsivo e alternadores de temas
    setupResponsiveMenuAndThemes();
});

async function loadDashboardData() {
    try {
        const response = await fetch("/api/data");
        if (response.status === 401) {
            // Se o token estiver expirado, redireciona ao login
            window.location.href = "/login";
            return;
        }
        
        const data = await response.json();
        
        // Atualiza cabeçalhos
        document.getElementById("userNameDisplay").innerText = data.user_name;
        document.getElementById("welcomeMessage").innerText = `Olá, ${data.user_name.split(" ")[0]}!`;
        document.getElementById("totalBalanceDisplay").innerText = formatCurrency(data.total_balance);
        
        renderAccountsCards(data.accounts);
        renderTransactions(data.accounts);
        generateCharts(data.accounts);
        
    } catch (err) {
        console.error("Erro ao carregar dados do dashboard:", err);
    }
}

// Renderiza os Cards de Bancos e configura a área Drag & Drop para cada um deles
function renderAccountsCards(accounts) {
    const grid = document.getElementById("accountsGrid");
    
    // Remove os cards de bancos antigos para não duplicá-los no DOM
    const oldCards = grid.querySelectorAll(".bank-render-card");
    oldCards.forEach(c => c.remove());
    
    accounts.forEach(acc => {
        const card = document.createElement("div");
        card.className = "m3-card bank-render-card";
        
        // Aplica identidade visual de acordo com o banco
        if (acc.bank_name.toLowerCase().includes("nubank")) {
            card.classList.add("card-nubank");
        } else if (acc.bank_name.toLowerCase().includes("inter")) {
            card.classList.add("card-inter");
        } else if (acc.bank_name.toLowerCase().includes("caixa")) {
            card.classList.add("card-caixa");
        }
        
        card.innerHTML = `
            <div class="card-header-bank">
                <h3>${acc.bank_name}</h3>
                <span class="material-symbols-outlined">account_balance</span>
            </div>
            <div class="balance-display">${formatCurrency(acc.balance)}</div>
            
            <!-- Zona de Upload de Extrato OFX -->
            <div class="drag-drop-area" id="dropzone-${acc.id}">
                <span class="material-symbols-outlined" style="font-size: 32px; color: var(--md-sys-color-primary);">upload_file</span>
                <div>Arraste seu extrato <b>OFX/XML</b> aqui</div>
                <input type="file" id="fileInput-${acc.id}" style="display: none;" accept=".ofx,.xml">
            </div>
        `;
        
        grid.appendChild(card);
        
        // Configura ouvintes de upload assíncronos para a zona arrastar e soltar
        setupDragAndDrop(acc.id);
    });
}

function setupDragAndDrop(accountId) {
    const dropzone = document.getElementById(`dropzone-${accountId}`);
    const fileInput = document.getElementById(`fileInput-${accountId}`);
    
    // Clicar na área abre a seleção de arquivos padrão
    dropzone.addEventListener("click", () => fileInput.click());
    
    // Ao selecionar arquivo
    fileInput.addEventListener("change", () => {
        if (fileInput.files.length > 0) {
            handleFileUpload(fileInput.files[0], accountId);
        }
    });
    
    // Efeitos visuais ao arrastar arquivo sobre o card
    ["dragenter", "dragover"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropzone.classList.add("dragover");
        }, false);
    });
    
    ["dragleave", "drop"].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropzone.classList.remove("dragover");
        }, false);
    });
    
    // Soltar arquivo
    dropzone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            handleFileUpload(files[0], accountId);
        }
    });
}

async function handleFileUpload(file, accountId) {
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const response = await fetch(`/api/upload/${accountId}`, {
            method: "POST",
            body: formData
        });
        
        const res = await response.json();
        
        if (response.ok) {
            // Emite notificação de sucesso e recarrega dados do painel
            alert(res.message);
            loadDashboardData();
        } else {
            alert("Erro no upload: " + res.detail);
        }
    } catch (err) {
        console.error("Erro ao enviar arquivo:", err);
    }
}

// Consolida e renderiza a tabela única de transações mesclando todos os bancos
function renderTransactions(accounts) {
    const listContainer = document.getElementById("transactionsList");
    listContainer.innerHTML = "";
    
    // Mescla todas as transações das contas em uma lista única
    let allTransactions = [];
    accounts.forEach(acc => {
        acc.transactions.forEach(tx => {
            allTransactions.push({
                ...tx,
                bankName: acc.bank_name
            });
        });
    });
    
    if (allTransactions.length === 0) {
        listContainer.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--md-sys-color-outline); padding: 32px;">
                    Nenhum extrato importado ainda. Faça upload de arquivos OFX acima!
                </td>
            </tr>
        `;
        return;
    }
    
    // Ordena por data decrescente (da mais recente para a mais antiga)
    allTransactions.sort((a, b) => {
        const dateA = parseDateStr(a.date);
        const dateB = parseDateStr(b.date);
        return dateB - dateA;
    });
    
    allTransactions.forEach(tx => {
        const row = document.createElement("tr");
        row.className = "tx-row";
        
        // Estiliza de acordo com tipo de movimentação
        const amountClass = tx.amount > 0 ? "amount-income" : "amount-expense";
        const amountPrefix = tx.amount > 0 ? "+" : "";
        
        // Cria caixa de seleção para a categoria (Material Design)
        let selectHtml = `<select class="category-select" onchange="changeCategory(${tx.id}, this.value)">`;
        CATEGORIES.forEach(cat => {
            const selected = tx.category === cat ? "selected" : "";
            selectHtml += `<option value="${cat}" ${selected}>${cat}</option>`;
        });
        selectHtml += "</select>";
        
        // Se for PIX, adiciona uma badge visual estilizada (cor oficial do Banco Central)
        let typeBadge = "";
        if (tx.type === "PIX_RECEBIDO" || tx.type === "PIX_ENVIADO") {
            typeBadge = `<span class="badge-pix">PIX</span> `;
        }
        
        // Cria badge ou botão de parcelamento para despesas
        let installmentBadge = "";
        if (tx.amount < 0) { // Apenas despesas
            if (tx.installment_plan_id) {
                installmentBadge = `
                    <span class="badge-installment" onclick="unlinkTransaction(${tx.id})" title="Clique para desvincular">
                        ${tx.installment_plan_name} (${tx.installment_number}/${tx.installment_plan_total_parts})
                        <span class="material-symbols-outlined" style="font-size: 14px; vertical-align: middle;">close</span>
                    </span>
                `;
            } else {
                installmentBadge = `
                    <button class="link-installment-action-btn" onclick="openLinkInstallmentModal(${tx.id}, '${tx.description.replace(/'/g, "\\'")}', ${Math.abs(tx.amount)})" title="Vincular a um parcelamento">
                        <span class="material-symbols-outlined" style="font-size: 18px;">link</span>
                    </button>
                `;
            }
        }
        
        row.innerHTML = `
            <td style="color: var(--md-sys-color-secondary); font-weight: 500;">${tx.date}</td>
            <td style="font-weight: 600;">${tx.bankName}</td>
            <td>
                <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%;">
                    <span>${typeBadge}${tx.description}</span>
                    ${installmentBadge}
                </div>
            </td>
            <td>${selectHtml}</td>
            <td class="tx-amount ${amountClass}">${amountPrefix}${formatCurrency(tx.amount)}</td>
        `;
        
        listContainer.appendChild(row);
    });
}

// Altera a categoria de uma despesa no banco de dados e recalcula os gráficos
async function changeCategory(transactionId, newCategory) {
    const formData = new FormData();
    formData.append("category", newCategory);
    
    try {
        const response = await fetch(`/api/transaction/${transactionId}/category`, {
            method: "POST",
            body: formData
        });
        if (response.ok) {
            // Recarrega apenas os dados para atualizar os gráficos sem dar F5
            loadDashboardData();
        }
    } catch (err) {
        console.error("Erro ao alterar categoria:", err);
    }
}

// --- CONSTRUÇÃO DOS GRÁFICOS (CHART.JS) ---

function generateCharts(accounts) {
    // 1. AGREGAÇÃO DE DADOS POR CATEGORIA (Apenas saídas/despesas)
    let categoryData = {};
    let evolutionPoints = [];
    
    // Mescla todas as transações
    let allTransactions = [];
    accounts.forEach(acc => {
        acc.transactions.forEach(tx => {
            allTransactions.push(tx);
        });
    });
    
    // Agrupa valores por categoria
    allTransactions.forEach(t => {
        if (t.amount < 0) {  // Apenas despesas
            const cat = t.category;
            const absVal = Math.abs(t.amount);
            categoryData[cat] = (categoryData[cat] || 0) + absVal;
        }
    });

    // Detecta se o Modo Escuro está ativo para ajustar as cores do Chart.js
    const isDark = document.body.classList.contains("dark-mode");
    const chartTextColor = isDark ? "#cbd5e1" : "#1e293b";
    const chartBorderColor = isDark ? "#2a2c35" : "#ffffff";
    const chartGridColor = isDark ? "rgba(255, 255, 255, 0.08)" : "rgba(0, 0, 0, 0.05)";
    
    // --- GRÁFICO 1: DISTRIBUIÇÃO POR CATEGORIA ---
    const ctxCategory = document.getElementById("categoryChart").getContext("2d");
    
    // Destrói gráfico antigo se existir
    if (categoryChartInstance) {
        categoryChartInstance.destroy();
    }
    
    const labels = Object.keys(categoryData);
    const values = Object.values(categoryData);
    
    if (labels.length === 0) {
        // Sem despesas para renderizar
        categoryChartInstance = null;
    } else {
        categoryChartInstance = new Chart(ctxCategory, {
            type: "doughnut",
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        "#48b9c7", "#008080", "#BA1A1A", "#006E3C", "#FF7A00", "#820AD1", "#64748b"
                    ],
                    borderWidth: 2,
                    borderColor: chartBorderColor
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            color: chartTextColor,
                            font: { family: "Inter", weight: "500" },
                            padding: 16
                        }
                    }
                },
                cutout: "70%"
            }
        });
    }
    
    // --- GRÁFICO 2: EVOLUÇÃO DE SALDO ---
    // Ordena transações das mais antigas para as mais recentes
    allTransactions.sort((a, b) => parseDateStr(a.date) - parseDateStr(b.date));
    
    // Começa o saldo acumulado com a soma dos saldos iniciais de todas as contas
    let runningBalance = accounts.reduce((total, acc) => total + (acc.initial_balance || 0), 0);
    let balancePoints = [];
    let dateLabels = [];
    
    allTransactions.forEach(t => {
        runningBalance += t.amount;
        // Agrupa por dia para não gerar pontos duplicados no gráfico de linha
        const lastIdx = dateLabels.length - 1;
        if (lastIdx >= 0 && dateLabels[lastIdx] === t.date) {
            balancePoints[lastIdx] = runningBalance;
        } else {
            dateLabels.push(t.date);
            balancePoints.push(runningBalance);
        }
    });
    
    const ctxEvolution = document.getElementById("evolutionChart").getContext("2d");
    if (evolutionChartInstance) {
        evolutionChartInstance.destroy();
    }
    
    evolutionChartInstance = new Chart(ctxEvolution, {
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
                    ticks: { 
                        color: chartTextColor,
                        font: { family: "Inter" } 
                    }
                },
                y: {
                    grid: {
                        color: chartGridColor
                    },
                    ticks: { 
                        color: chartTextColor,
                        font: { family: "Inter" } 
                    }
                }
            }
        }
    });
}

// Configura o drawer mobile deslizante e os seletores de tema síncronos
function setupResponsiveMenuAndThemes() {
    // 1. Controle do Drawer Responsivo (Mobile)
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

        // Fecha drawer se algum item for clicado
        const navLinks = document.querySelectorAll(".nav-item a");
        navLinks.forEach(link => {
            link.addEventListener("click", closeSidebar);
        });
    }

    // 2. Lógica de Alternância de Tema Sincronizada (Desktop & Mobile)
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

    // Inicializa ícones com o estado do tema
    updateThemeIcons();

    const toggleTheme = () => {
        document.body.classList.toggle("dark-mode");
        const isDark = document.body.classList.contains("dark-mode");
        localStorage.setItem("theme", isDark ? "dark" : "light");
        updateThemeIcons();
        
        // Recarrega os dados do painel para redesenhar os gráficos com a nova paleta de cor
        loadDashboardData();
    };

    if (mobileThemeToggle) {
        mobileThemeToggle.addEventListener("click", toggleTheme);
    }
    if (desktopThemeToggle) {
        desktopThemeToggle.addEventListener("click", toggleTheme);
    }
}

// --- UTILITÁRIOS ---

function formatCurrency(value) {
    return new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL"
    }).format(value);
}

// Transforma string "DD/MM/AAAA" em objeto Date
function parseDateStr(dateStr) {
    const parts = dateStr.split("/");
    return new Date(parts[2], parts[1] - 1, parts[0]);
}

// Ouvinte reativo para atualização dinâmica de categorias
document.addEventListener("categoriesUpdated", (e) => {
    CATEGORIES = e.detail;
    // Se o dashboard já carregou alguma conta, re-renderiza para aplicar novas categorias
    const txTable = document.getElementById("transactionsList");
    if (txTable && txTable.innerHTML !== "") {
        loadDashboardData();
    }
});

// --- LÓGICA DE VÍNCULO DE PARCELAMENTOS ---

let activeLinkTransactionId = null;

async function openLinkInstallmentModal(transactionId, description, amount) {
    activeLinkTransactionId = transactionId;
    
    try {
        const response = await fetch("/api/installments");
        if (!response.ok) return;
        const plans = await response.json();
        
        if (plans.length === 0) {
            alert("Você não possui nenhum parcelamento cadastrado. Vá até a tela de 'Parcelamentos' para criar um!");
            return;
        }
        
        let modal = document.getElementById("linkInstallmentModal");
        if (!modal) {
            modal = document.createElement("div");
            modal.id = "linkInstallmentModal";
            modal.className = "m3-modal";
            modal.style.maxWidth = "400px";
            modal.innerHTML = `
                <div class="card-header-bank" style="border-bottom: 1px solid var(--md-sys-color-outline-variant); padding-bottom: 12px; margin-bottom: 16px;">
                    <h3 style="font-weight: 600; display: flex; align-items: center; gap: 8px; margin: 0; font-size: 18px;">
                        <span class="material-symbols-outlined" style="color: var(--md-sys-color-primary);">link</span>
                        Vincular Parcelamento
                    </h3>
                    <button class="close-sidebar-btn" onclick="closeLinkInstallmentModal()" style="display: flex;" title="Fechar">
                        <span class="material-symbols-outlined">close</span>
                    </button>
                </div>
                <div style="margin-bottom: 16px;">
                    <p style="font-size: 13px; color: var(--md-sys-color-outline); font-weight: 600; margin-bottom: 4px;">Transação:</p>
                    <p id="linkTxDesc" style="font-weight: 600; font-size: 15px; margin: 0;"></p>
                    <p id="linkTxVal" style="font-size: 13px; opacity: 0.8; margin-top: 4px;"></p>
                </div>
                <form id="linkInstallmentForm" onsubmit="submitLinkInstallment(event)" style="display: flex; flex-direction: column; gap: 16px;">
                    <div style="display: flex; flex-direction: column; gap: 6px;">
                        <label for="linkPlanSelect" style="font-size: 13px; font-weight: 600; color: var(--md-sys-color-outline);">Selecione o Parcelamento:</label>
                        <select id="linkPlanSelect" onchange="suggestNextPart()" class="filter-select" style="border-radius: var(--md-shape-corner-medium); padding: 10px 16px; border: 1px solid var(--md-sys-color-outline-variant); background: var(--md-sys-color-surface);" required>
                            <!-- Populado dinamicamente -->
                        </select>
                    </div>
                    <div style="display: flex; flex-direction: column; gap: 6px;">
                        <label for="linkPartNumber" style="font-size: 13px; font-weight: 600; color: var(--md-sys-color-outline);">Número da Parcela:</label>
                        <input type="number" id="linkPartNumber" min="1" class="filter-select" style="border-radius: var(--md-shape-corner-medium); padding: 10px 16px; border: 1px solid var(--md-sys-color-outline-variant); background: var(--md-sys-color-surface);" required>
                    </div>
                    <button type="submit" class="m3-btn m3-btn-primary" style="margin-top: 8px;">Confirmar Vínculo</button>
                </form>
            `;
            document.body.appendChild(modal);
        }
        
        document.getElementById("linkTxDesc").innerText = description;
        document.getElementById("linkTxVal").innerText = `Valor: ${formatCurrency(amount)}`;
        
        const select = document.getElementById("linkPlanSelect");
        select.innerHTML = '<option value="" disabled selected>Selecione um plano...</option>';
        
        window.tempInstallmentPlans = plans;
        
        plans.forEach(plan => {
            const opt = document.createElement("option");
            opt.value = plan.id;
            opt.innerText = `${plan.name} (${plan.total_parts}x de ${formatCurrency(plan.installment_amount)})`;
            select.appendChild(opt);
        });
        
        const overlay = document.getElementById("modalOverlay");
        modal.classList.add("active");
        overlay.classList.add("active");
        
        const originalOverlayClick = overlay.onclick;
        overlay.onclick = () => {
            closeLinkInstallmentModal();
            overlay.onclick = originalOverlayClick;
        };
        
    } catch (err) {
        console.error("Erro ao abrir modal de vínculo:", err);
    }
}

function closeLinkInstallmentModal() {
    const modal = document.getElementById("linkInstallmentModal");
    const overlay = document.getElementById("modalOverlay");
    if (modal) modal.classList.remove("active");
    if (overlay) overlay.classList.remove("active");
    activeLinkTransactionId = null;
}

function suggestNextPart() {
    const select = document.getElementById("linkPlanSelect");
    const planId = parseInt(select.value);
    const plans = window.tempInstallmentPlans || [];
    const selectedPlan = plans.find(p => p.id === planId);
    
    if (selectedPlan) {
        const nextPart = selectedPlan.paid_parts + 1;
        const input = document.getElementById("linkPartNumber");
        input.value = Math.min(nextPart, selectedPlan.total_parts);
        input.max = selectedPlan.total_parts;
    }
}

async function submitLinkInstallment(e) {
    e.preventDefault();
    if (!activeLinkTransactionId) return;
    
    const planId = document.getElementById("linkPlanSelect").value;
    const partNumber = document.getElementById("linkPartNumber").value;
    
    const formData = new FormData();
    formData.append("installment_plan_id", planId);
    formData.append("installment_number", partNumber);
    
    try {
        const response = await fetch(`/api/transaction/${activeLinkTransactionId}/link`, {
            method: "POST",
            body: formData
        });
        const res = await response.json();
        
        if (response.ok) {
            alert(res.message);
            closeLinkInstallmentModal();
            loadDashboardData();
        } else {
            alert("Erro ao vincular: " + res.detail);
        }
    } catch (err) {
        console.error("Erro ao vincular transação:", err);
    }
}

async function unlinkTransaction(transactionId) {
    if (!confirm("Deseja realmente desvincular esta transação do parcelamento?")) {
        return;
    }
    
    try {
        const response = await fetch(`/api/transaction/${transactionId}/unlink`, {
            method: "POST"
        });
        const res = await response.json();
        
        if (response.ok) {
            alert(res.message);
            loadDashboardData();
        } else {
            alert("Erro ao desvincular: " + res.detail);
        }
    } catch (err) {
        console.error("Erro ao desvincular transação:", err);
    }
}
