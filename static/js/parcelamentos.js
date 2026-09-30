let CATEGORIES = ["Transporte", "Lazer", "Serviços & Assinaturas", "Saúde", "Receita", "Outros", "Loteria", "Mercado", "Restaurante & Delivery", "Pagamento de Fatura", "Moradia & Contas"];

document.addEventListener("DOMContentLoaded", () => {
    // Carrega os dados de parcelamento
    loadInstallmentsData();
    // Configura o menu responsivo e alternadores de temas
    setupResponsiveMenuAndThemes();
    // Configura eventos da tela
    setupInstallmentEvents();
});

async function loadInstallmentsData() {
    try {
        const response = await fetch("/api/installments");
        if (response.status === 401) {
            window.location.href = "/login";
            return;
        }
        
        const installments = await response.json();
        
        // Carrega as informações do usuário para atualizar a sidebar
        const userRes = await fetch("/api/data");
        if (userRes.ok) {
            const userData = await userRes.json();
            document.getElementById("userNameDisplay").innerText = userData.user_name;
        }

        renderTotals(installments);
        renderInstallmentsList(installments);
        
    } catch (err) {
        console.error("Erro ao carregar dados de parcelamentos:", err);
    }
}

function renderTotals(installments) {
    let totalCompromised = 0;
    let totalPaid = 0;
    let totalRemaining = 0;

    installments.forEach(plan => {
        totalCompromised += plan.total_amount;
        totalPaid += plan.paid_amount;
        totalRemaining += plan.remaining_amount;
    });

    document.getElementById("totalCompromisedDisplay").innerText = formatCurrency(totalCompromised);
    document.getElementById("totalPaidDisplay").innerText = formatCurrency(totalPaid);
    document.getElementById("totalRemainingDisplay").innerText = formatCurrency(totalRemaining);
}

function renderInstallmentsList(installments) {
    const container = document.getElementById("installmentsGrid");
    container.innerHTML = "";

    if (installments.length === 0) {
        container.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; color: var(--md-sys-color-outline); padding: 48px; background: var(--md-sys-color-surface-container-low); border-radius: var(--md-shape-corner-large); border: 1px dashed var(--md-sys-color-outline-variant);">
                <span class="material-symbols-outlined" style="font-size: 48px; margin-bottom: 12px; display: inline-block;">credit_card_off</span>
                <p style="font-weight: 500;">Nenhum parcelamento cadastrado.</p>
                <p style="font-size: 13px; opacity: 0.8; margin-top: 4px;">Clique em "Novo Parcelamento" para registrar suas despesas parceladas.</p>
            </div>
        `;
        return;
    }

    installments.forEach(plan => {
        const card = document.createElement("div");
        card.className = "m3-card bank-render-card";
        card.style.display = "flex";
        card.style.flexDirection = "column";
        card.style.justifyContent = "space-between";
        card.style.gap = "16px";
        card.style.padding = "24px";
        card.style.borderLeft = `5px solid var(--md-sys-color-primary)`;

        // Calcula porcentagem paga
        const percent = plan.total_parts > 0 ? (plan.paid_parts / plan.total_parts) * 100 : 0;
        const formattedPercent = percent.toFixed(0);

        // Ícones de categoria convenientes
        let categoryIcon = "payments";
        if (plan.category.toLowerCase().includes("alimenta")) categoryIcon = "restaurant";
        else if (plan.category.toLowerCase().includes("transp")) categoryIcon = "directions_car";
        else if (plan.category.toLowerCase().includes("lazer")) categoryIcon = "sports_esports";
        else if (plan.category.toLowerCase().includes("servi")) categoryIcon = "subscriptions";
        else if (plan.category.toLowerCase().includes("saud")) categoryIcon = "medical_services";

        card.innerHTML = `
            <div>
                <div class="card-header-bank" style="margin-bottom: 8px;">
                    <h3 style="font-weight: 600; font-size: 18px; margin: 0;">${plan.name}</h3>
                    <button class="delete-installment-btn" onclick="deleteInstallment(${plan.id}, '${plan.name}')" title="Excluir parcelamento" style="background: none; border: none; color: var(--md-sys-color-error); cursor: pointer; display: flex; align-items: center; justify-content: center; padding: 4px; border-radius: 50%;">
                        <span class="material-symbols-outlined" style="font-size: 20px;">delete</span>
                    </button>
                </div>
                
                <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 16px;">
                    <span class="badge-pix" style="background: var(--md-sys-color-primary-container); color: var(--md-sys-color-on-primary-container); display: flex; align-items: center; gap: 4px; padding: 4px 10px; font-size: 11px;">
                        <span class="material-symbols-outlined" style="font-size: 14px;">${categoryIcon}</span>
                        ${plan.category}
                    </span>
                    <span class="badge-pix" style="background: var(--md-sys-color-surface-container-high); color: var(--md-sys-color-on-surface); font-size: 11px; padding: 4px 10px;">
                        ${plan.total_parts}x de ${formatCurrency(plan.installment_amount)}
                    </span>
                </div>
                
                <div style="margin-bottom: 4px; display: flex; justify-content: space-between; font-size: 13px; font-weight: 500;">
                    <span>Progresso de Quitação</span>
                    <span style="color: var(--md-sys-color-secondary); font-weight: 600;">${plan.paid_parts}/${plan.total_parts} (${formattedPercent}%)</span>
                </div>
                
                <!-- Barra de progresso linear M3 -->
                <div style="width: 100%; height: 8px; background-color: var(--md-sys-color-surface-container-high); border-radius: 4px; overflow: hidden; margin-bottom: 12px;">
                    <div style="width: ${percent}%; height: 100%; background-color: var(--md-sys-color-secondary); border-radius: 4px; transition: width 0.5s ease-in-out;"></div>
                </div>
            </div>

            <div style="border-top: 1px solid var(--md-sys-color-outline-variant); padding-top: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                <div>
                    <span style="font-size: 11px; color: var(--md-sys-color-outline); font-weight: 600; text-transform: uppercase;">Já Pago</span>
                    <div style="font-size: 15px; font-weight: 600; color: var(--md-sys-color-secondary);">${formatCurrency(plan.paid_amount)}</div>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 11px; color: var(--md-sys-color-outline); font-weight: 600; text-transform: uppercase;">Restante</span>
                    <div style="font-size: 15px; font-weight: 600; color: var(--md-sys-color-on-surface);">${formatCurrency(plan.remaining_amount)}</div>
                </div>
            </div>
        `;

        container.appendChild(card);
    });
}

async function deleteInstallment(id, name) {
    if (!confirm(`Deseja realmente excluir o parcelamento "${name}"? As transações vinculadas serão mantidas, mas o vínculo de parcelas será removido.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/installments/${id}`, {
            method: "DELETE"
        });
        const res = await response.json();
        
        if (response.ok) {
            alert(res.message);
            loadInstallmentsData();
        } else {
            alert("Erro ao excluir: " + res.detail);
        }
    } catch (err) {
        console.error("Erro ao excluir parcelamento:", err);
    }
}

function setupInstallmentEvents() {
    const modal = document.getElementById("newInstallmentModal");
    const overlay = document.getElementById("modalOverlay");
    const openBtn = document.getElementById("openNewInstallmentModalBtn");
    const closeBtn = document.getElementById("closeNewInstallmentModalBtn");
    const form = document.getElementById("newInstallmentForm");

    const totalInput = document.getElementById("installmentTotalAmount");
    const partsInput = document.getElementById("installmentParts");
    const partAmountInput = document.getElementById("installmentPartAmount");

    // Lógica inteligente de cálculo do valor da parcela
    const calculatePartAmount = () => {
        const total = parseFloat(totalInput.value);
        const parts = parseInt(partsInput.value);
        if (total > 0 && parts > 0) {
            partAmountInput.value = (total / parts).toFixed(2);
        }
    };

    totalInput.addEventListener("input", calculatePartAmount);
    partsInput.addEventListener("input", calculatePartAmount);

    const openModal = () => {
        modal.classList.add("active");
        overlay.classList.add("active");
        form.reset();
        
        // Povoar categorias se houver um seletor dinâmico
        loadCategoriesSelect();
    };

    const closeModal = () => {
        modal.classList.remove("active");
        overlay.classList.remove("active");
    };

    openBtn.addEventListener("click", openModal);
    closeBtn.addEventListener("click", closeModal);
    overlay.addEventListener("click", closeModal);

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const formData = new FormData();
        formData.append("name", document.getElementById("installmentName").value);
        formData.append("total_amount", totalInput.value);
        formData.append("installment_amount", partAmountInput.value);
        formData.append("total_parts", partsInput.value);
        formData.append("category", document.getElementById("installmentCategory").value);

        try {
            const response = await fetch("/api/installments", {
                method: "POST",
                body: formData
            });

            const res = await response.json();

            if (response.ok) {
                alert(res.message);
                closeModal();
                loadInstallmentsData();
            } else {
                alert("Erro ao cadastrar: " + res.detail);
            }
        } catch (err) {
            console.error("Erro ao cadastrar parcelamento:", err);
        }
    });
}

async function loadCategoriesSelect() {
    try {
        const response = await fetch("/api/categories");
        if (response.ok) {
            const categories = await response.json();
            const select = document.getElementById("installmentCategory");
            select.innerHTML = "";
            categories.forEach(cat => {
                if (cat !== "Receita") { // Evita parcelar receitas
                    const opt = document.createElement("option");
                    opt.value = cat;
                    opt.innerText = cat;
                    select.appendChild(opt);
                }
            });
        }
    } catch (err) {
        console.error("Erro ao carregar categorias:", err);
    }
}

// Ouvinte reativo para atualização dinâmica de categorias
document.addEventListener("categoriesUpdated", (e) => {
    CATEGORIES = e.detail;
});

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
        loadInstallmentsData();
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
