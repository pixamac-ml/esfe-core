window.closeDashboardModal = function closeDashboardModal() {
    window.managerCloseModal();
};

window.openDashboardModal = function openDashboardModal() {
    const modal = document.getElementById('modal-container');
    if (!modal) return;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
};

window.managerToggleSidebar = function managerToggleSidebar() {
    const sidebar = document.getElementById('managerSidebar');
    if (!sidebar) return;
    sidebar.classList.toggle('open');
};

window.managerCloseModal = function managerCloseModal() {
    const modal = document.getElementById('modal-container');
    const content = document.getElementById('modal-content');
    if (content) content.innerHTML = '';
    if (modal) modal.classList.add('hidden');
    document.body.style.overflow = '';
};

window.managerOpenModal = function managerOpenModal(url) {
    const modal = document.getElementById('modal-container');
    const content = document.getElementById('modal-content');
    if (!modal || !content || !url) return;
    window.openDashboardModal();
    content.innerHTML = '<div class="p-6 text-sm font-semibold text-slate-500">Chargement...</div>';
    document.body.style.overflow = 'hidden';
    fetch(url, {
        headers: { 'HX-Request': 'true', 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin'
    }).then(function(response) {
        return response.text().then(function(html) { return { ok: response.ok, html: html }; });
    }).then(function(payload) {
        content.innerHTML = payload.html;
        if (window.htmx && typeof htmx.process === 'function') {
            htmx.process(content);
        }
    }).catch(function() {
        content.innerHTML = '<div class="p-6 text-sm font-semibold text-rose-600">Impossible de charger cette fenetre.</div>';
    });
};

window.managerCreateCashSession = function managerCreateCashSession() {
    const select = document.getElementById('manager-cash-inscription');
    if (!select || !select.value) return;
    const el = document.getElementById('manager-cash-session-url');
    if (!el) return;
    var url = el.value.replace('/0/', '/' + select.value + '/');
    var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
    if (!csrf) return;
    fetch(url, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrf.value,
            'HX-Request': 'true',
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin'
    }).then(function(response) {
        return response.text().then(function(html) { return { ok: response.ok, html: html }; });
    }).then(function(payload) {
        const list = document.getElementById('manager-cash-session-list');
        if (!list) return;
        const wrapper = document.createElement('div');
        wrapper.innerHTML = payload.html.trim();
        const node = wrapper.firstElementChild;
        if (!node) return;
        const emptyState = document.getElementById('manager-cash-session-empty');
        if (emptyState) emptyState.remove();
        const existing = document.getElementById(node.id);
        if (existing) {
            existing.replaceWith(node);
        } else {
            list.prepend(node);
        }
        if (window.htmx && typeof htmx.process === 'function') {
            htmx.process(node);
        }
    });
};

document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        managerCloseModal();
        const sidebar = document.getElementById('managerSidebar');
        if (sidebar) sidebar.classList.remove('open');
    }
});

document.body.addEventListener('inscriptionCreated', function() {
    managerCloseModal();
    window.location.reload();
});

document.body.addEventListener('openInscriptionPositioning', function(event) {
    const url = event.detail && event.detail.url;
    if (url) managerOpenModal(url);
});

document.body.addEventListener('candidatureDeleted', function(event) {
    const id = event.detail && event.detail.id;
    if (!id) return;
    const row = document.getElementById('candidature-' + id);
    if (row) row.remove();
    managerCloseModal();
});

document.body.addEventListener('htmx:afterSwap', function(event) {
    if (event.target && event.target.id === 'modal-content' && event.target.innerHTML.trim()) {
        window.openDashboardModal();
    }
});

window.showToast = function showToast(message, type) {
    type = type || 'info';
    const container = document.getElementById('toast-container');
    if (!container) return;
    const colors = { success: '#16a34a', error: '#ef4444', warning: '#d97706', info: '#2563eb' };
    const icons = { success: 'fa-check-circle', error: 'fa-times-circle', warning: 'fa-exclamation-circle', info: 'fa-info-circle' };
    const toast = document.createElement('div');
    toast.style.cssText = 'background:' + (colors[type] || colors.info) + '; color:#fff; padding:12px 20px; border-radius:14px; box-shadow:0 8px 32px rgba(0,0,0,.18); display:flex; align-items:center; gap:12px; font-size:.85rem; font-weight:700; transform:translateX(120%); opacity:0; transition:all .35s cubic-bezier(.22,1,.36,1); pointer-events:auto; max-width:420px;';
    toast.innerHTML = '<i class="fas ' + (icons[type] || icons.info) + '" style="font-size:1.1rem;"></i><span style="flex:1;">' + message + '</span><button onclick="this.parentElement.remove()" style="background:none; border:none; color:rgba(255,255,255,.7); cursor:pointer; padding:2px;"><i class="fas fa-times"></i></button>';
    container.appendChild(toast);
    requestAnimationFrame(function() {
        toast.style.transform = 'translateX(0)';
        toast.style.opacity = '1';
    });
    setTimeout(function() {
        toast.style.transform = 'translateX(120%)';
        toast.style.opacity = '0';
        setTimeout(function() { toast.remove(); }, 350);
    }, 4500);
};

document.body.addEventListener('htmx:beforeSwap', function(event) {
    var trigger = event.detail.xhr.getResponseHeader('HX-Trigger');
    if (trigger) {
        try {
            var data = JSON.parse(trigger);
            if (data.showToast) {
                showToast(data.showToast.message, data.showToast.type);
            }
        } catch(e) {}
    }
});

(function parseNotice() {
    var params = new URLSearchParams(window.location.search);
    var notice = params.get('notice');
    if (!notice) return;
    var parts = notice.split('_');
    var typeMap = { created: 'success', updated: 'success', deleted: 'warning', cancelled: 'warning', error: 'error' };
    var type = typeMap[parts[0]] || 'info';
    var msgs = {
        'paies_preparees': 'Fiches de paie preparees avec succes.',
        'salaires_disponibles': 'Fiches marquees comme disponibles.',
        'honoraires_preparees': 'Fiches d\'honoraires preparees avec succes.',
        'honoraires_disponibles': 'Honoraires marques comme disponibles.',
        'caisse_sync': 'Caisse synchronisee avec succes.',
        'updated_salaire': 'Fiche de paie mise a jour.',
        'created_paiement': 'Paiement salarie enregistre.',
        'created_avance': 'Avance sur salaire enregistree.',
        'updated_honoraire': 'Fiche d\'honoraire mise a jour.',
        'created_paiement_honoraire': 'Paiement honoraire enregistre.',
        'created_cloture': 'Cloture mensuelle effectuee.',
        'created_depense': 'Depense creee avec succes.',
        'updated_approuvee': 'Depense approuvee.',
        'cancelled_rejetee': 'Depense rejetee.',
        'created_payee': 'Depense payee.',
        'created_mouvement': 'Mouvement de caisse cree.',
    };
    var key = parts.slice(0, -1).join('_');
    var message = msgs[key] || 'Operation effectuee avec succes.';
    showToast(message, type);
    var url = new URL(window.location);
    url.searchParams.delete('notice');
    window.history.replaceState({}, '', url);
})();
