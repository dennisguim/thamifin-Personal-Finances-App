// Gerenciador de Categorias (Modal) Compartilhado
let globalCategories = [];

document.addEventListener("DOMContentLoaded", () => {
    setupCategoriesModal();
    loadGlobalCategories();
});

async function loadGlobalCategories() {
    try {
        const response = await fetch("/api/categories");
        if (response.ok) {
            globalCategories = await response.json();
            renderModalCategories();
            // Dispara evento para que a página se atualize com as novas categorias
            document.dispatchEvent(new CustomEvent("categoriesUpdated", { detail: globalCategories }));
        }
    } catch (err) {
        console.error("Erro ao carregar categorias globais:", err);
    }
}

function setupCategoriesModal() {
    const manageBtn = document.getElementById("manageCategoriesBtn");
    const closeBtn = document.getElementById("closeCategoriesModalBtn");
    const overlay = document.getElementById("modalOverlay");
    const modal = document.getElementById("categoriesModal");
    const addBtn = document.getElementById("addCategoryBtn");
    const nameInput = document.getElementById("newCategoryName");

    if (!modal || !overlay) return;

    // Abrir Modal
    if (manageBtn) {
        manageBtn.addEventListener("click", (e) => {
            e.preventDefault();
            modal.classList.add("active");
            overlay.classList.add("active");
            
            // Fecha menu lateral mobile ao abrir modal, para melhor visualização
            const sidebar = document.getElementById("dashboardSidebar");
            const sidebarOverlay = document.getElementById("sidebarOverlay");
            if (sidebar && sidebar.classList.contains("active")) {
                sidebar.classList.remove("active");
                sidebarOverlay.classList.remove("active");
            }
            
            loadGlobalCategories(); // Refresh ao abrir
        });
    }

    // Fechar Modal
    const closeModal = () => {
        modal.classList.remove("active");
        overlay.classList.remove("active");
        if (nameInput) nameInput.value = "";
    };

    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (overlay) overlay.addEventListener("click", closeModal);

    // Criar Nova Categoria
    if (addBtn && nameInput) {
        addBtn.addEventListener("click", async () => {
            const name = nameInput.value.trim();
            if (!name) {
                alert("O nome da categoria não pode ser vazio.");
                return;
            }

            const formData = new FormData();
            formData.append("name", name);

            try {
                const response = await fetch("/api/category", {
                    method: "POST",
                    body: formData
                });

                const res = await response.json();
                if (response.ok) {
                    nameInput.value = "";
                    loadGlobalCategories(); // Recarrega do backend e emite evento
                } else {
                    alert("Erro ao cadastrar: " + res.detail);
                }
            } catch (err) {
                console.error("Erro ao cadastrar categoria:", err);
            }
        });

        // Suporte ao Enter no input
        nameInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                addBtn.click();
            }
        });
    }
}

function renderModalCategories() {
    const container = document.getElementById("modalCategoriesList");
    if (!container) return;
    
    container.innerHTML = "";
    globalCategories.forEach(cat => {
        const badge = document.createElement("span");
        badge.className = "badge-category-modal";
        badge.innerHTML = `
            <span class="material-symbols-outlined" style="font-size: 14px; color: var(--md-sys-color-primary);">label</span>
            ${cat}
        `;
        container.appendChild(badge);
    });
}
