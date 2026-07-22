/* ═══════════════════════════════════════════════════════════
   CommerceHub — Global JavaScript
   main.js
═══════════════════════════════════════════════════════════ */

'use strict';

// ── Auto-dismiss alerts after 5 seconds ──
document.querySelectorAll('.alert-dismissible').forEach(alert => {
    setTimeout(() => {
        alert.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
        alert.style.opacity = '0';
        alert.style.transform = 'translateY(-8px)';
        setTimeout(() => alert.remove(), 400);
    }, 5000);
});

// ── Sidebar Toggle (mobile) ──
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.getElementById('sidebar');

if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
    });

    // Close sidebar on outside click (mobile)
    document.addEventListener('click', (e) => {
        if (sidebar.classList.contains('open') &&
            !sidebar.contains(e.target) &&
            !sidebarToggle.contains(e.target)) {
            sidebar.classList.remove('open');
        }
    });
}

// ── CSRF token helper for fetch requests ──
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.startsWith(name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
window.CSRF_TOKEN = getCookie('csrftoken');
