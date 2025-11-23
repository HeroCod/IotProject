/**
 * Common JavaScript Functions - Shared across all pages
 */

// Dark mode functionality
function toggleDarkMode() {
    const body = document.body;
    const toggle = document.querySelector('.dark-mode-toggle');

    if (body.getAttribute('data-theme') === 'dark') {
        body.removeAttribute('data-theme');
        toggle.innerHTML = '🌙';
        localStorage.setItem('theme', 'light');
    } else {
        body.setAttribute('data-theme', 'dark');
        toggle.innerHTML = '☀️';
        localStorage.setItem('theme', 'dark');
    }
}

// Initialize theme on page load
function initializeTheme() {
    const savedTheme = localStorage.getItem('theme');
    const toggle = document.querySelector('.dark-mode-toggle');

    if (savedTheme === 'dark') {
        document.body.setAttribute('data-theme', 'dark');
        if (toggle) toggle.innerHTML = '☀️';
    } else {
        if (toggle) toggle.innerHTML = '🌙';
    }
}

// Initialize theme on page load
document.addEventListener('DOMContentLoaded', initializeTheme);
