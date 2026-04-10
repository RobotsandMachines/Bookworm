/* ============================================================
   Bookworm - Main JavaScript (shared across all pages)
   ============================================================ */

// --- Global state ---
let currentUser = null;

// --- DOM Ready ---
document.addEventListener('DOMContentLoaded', () => {
    initSidebar();
    checkAuth();
    highlightActiveLink();
});

// --- Sidebar toggle ---
function initSidebar() {
    const menuBtn = document.getElementById('menu-btn');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');

    if (menuBtn) {
        menuBtn.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            overlay.classList.toggle('show');
        });
    }

    if (overlay) {
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
        });
    }
}

// --- Highlight current page link ---
function highlightActiveLink() {
    const path = window.location.pathname;
    document.querySelectorAll('.sidebar-link').forEach(link => {
        link.classList.remove('active');
        if (link.getAttribute('href') === path) {
            link.classList.add('active');
        }
    });
}

// --- Auth check ---
async function checkAuth() {
    try {
        const resp = await fetch('/api/auth/me');
        const data = await resp.json();
        currentUser = data.user;
        updateUserUI();
    } catch (e) {
        currentUser = null;
        updateUserUI();
    }
}

function updateUserUI() {
    const userArea = document.getElementById('user-area');
    if (!userArea) return;

    if (currentUser) {
        userArea.innerHTML = `
            <div class="user-badge" onclick="toggleUserMenu()">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                    <circle cx="12" cy="7" r="4"/>
                </svg>
                <span>${currentUser.display_name}</span>
                <span class="role-tag">${currentUser.auth_level}</span>
            </div>
            <div id="user-dropdown" style="display:none; position:absolute; top:56px; right:16px; background:white; border-radius:8px; box-shadow:0 4px 16px rgba(59,46,30,0.15); padding:8px 0; min-width:160px; z-index:1100;">
                <div style="padding:8px 16px; font-size:0.8rem; color:#A0896C; border-bottom:1px solid #EDE6D6;">
                    Signed in as <strong>${currentUser.username}</strong>
                </div>
                <a href="#" onclick="logout(); return false;" style="display:block; padding:10px 16px; font-size:0.9rem; color:#C0392B;">
                    Sign Out
                </a>
            </div>
        `;
    } else {
        userArea.innerHTML = `
            <a href="/login" class="login-btn">Sign In</a>
        `;
    }
}

function toggleUserMenu() {
    const dd = document.getElementById('user-dropdown');
    if (dd) dd.style.display = dd.style.display === 'none' ? 'block' : 'none';
}

// Close user menu on outside click
document.addEventListener('click', (e) => {
    const dd = document.getElementById('user-dropdown');
    const badge = e.target.closest('.user-badge');
    if (dd && !badge) dd.style.display = 'none';
});

async function logout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    currentUser = null;
    window.location.href = '/';
}

// --- Toast Notifications ---
function showToast(message, type = 'success') {
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    container.appendChild(toast);

    setTimeout(() => toast.remove(), 5000);
}

// --- API Helpers ---
async function apiGet(url) {
    const resp = await fetch(url);
    if (resp.status === 401) {
        window.location.href = '/login';
        return null;
    }
    return resp.json();
}

async function apiPost(url, data) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    const result = await resp.json();
    if (!resp.ok) {
        throw new Error(result.error || 'Request failed');
    }
    return result;
}

async function apiPut(url, data) {
    const resp = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    const result = await resp.json();
    if (!resp.ok) {
        throw new Error(result.error || 'Request failed');
    }
    return result;
}

async function apiDelete(url) {
    const resp = await fetch(url, { method: 'DELETE' });
    const result = await resp.json();
    if (!resp.ok) {
        throw new Error(result.error || 'Request failed');
    }
    return result;
}

// --- Load stores into a select element ---
async function loadStoresIntoSelect(selectId, includeAll = false) {
    const select = document.getElementById(selectId);
    if (!select) return;

    const stores = await apiGet('/api/stores');
    if (!stores) return;

    select.innerHTML = '';
    if (includeAll) {
        const opt = document.createElement('option');
        opt.value = 'all';
        opt.textContent = 'All Stores';
        select.appendChild(opt);
    }

    stores.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.store_id;
        opt.textContent = s.store_name;
        select.appendChild(opt);
    });
}
