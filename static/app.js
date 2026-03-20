/* ColdCraft — Minimal JS interactions */

// Copy text to clipboard
function copyText(elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;
    const text = el.innerText || el.textContent;
    navigator.clipboard.writeText(text).then(() => {
        // Visual feedback
        const original = el.style.borderColor;
        el.style.borderColor = '#10b981';
        setTimeout(() => { el.style.borderColor = original; }, 1000);
    });
}

// Auto-dismiss flash messages
document.addEventListener('DOMContentLoaded', () => {
    const flashes = document.querySelectorAll('.flash');
    flashes.forEach(f => {
        setTimeout(() => {
            f.style.transition = 'opacity 0.3s, transform 0.3s';
            f.style.opacity = '0';
            f.style.transform = 'translateY(-8px)';
            setTimeout(() => f.remove(), 300);
        }, 5000);
    });
});

// Confirm before destructive actions
function confirmAction(message) {
    return confirm(message || 'Are you sure?');
}
