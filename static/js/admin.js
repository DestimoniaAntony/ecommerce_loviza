/* ═══════════════════════════════════════════════════════════
   CommerceHub — Admin JavaScript
   admin.js
═══════════════════════════════════════════════════════════ */

'use strict';

// ── Confirm before dangerous actions ──
document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', (e) => {
        if (!confirm(el.dataset.confirm)) {
            e.preventDefault();
        }
    });
});

// ── Theme Toggle Logic ──
document.addEventListener('DOMContentLoaded', () => {
    const themeToggleBtn = document.getElementById('themeToggle');
    const sunIcon = document.querySelector('.sun-icon');
    const moonIcon = document.querySelector('.moon-icon');

    if (themeToggleBtn) {
        // Initialize UI based on current theme class
        const isLight = document.documentElement.classList.contains('theme-light');
        if (isLight) {
            sunIcon.style.display = 'none';
            moonIcon.style.display = 'block';
        } else {
            sunIcon.style.display = 'block';
            moonIcon.style.display = 'none';
        }

        themeToggleBtn.addEventListener('click', () => {
            const currentlyLight = document.documentElement.classList.contains('theme-light');
            if (currentlyLight) {
                // Switch to dark
                document.documentElement.classList.remove('theme-light');
                localStorage.setItem('commercehub_theme', 'dark');
                sunIcon.style.display = 'block';
                moonIcon.style.display = 'none';
            } else {
                // Switch to light
                document.documentElement.classList.add('theme-light');
                localStorage.setItem('commercehub_theme', 'light');
                sunIcon.style.display = 'none';
                moonIcon.style.display = 'block';
            }
        });
    }
});
