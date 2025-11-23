/**
 * Optimizer UI Functions
 */

export function showMessage(message, type) {
    const responseDiv = document.getElementById('response-message');
    if (responseDiv) {
        const bgColor = type === 'success' ? '#d4edda' : '#f8d7da';
        const textColor = type === 'success' ? '#155724' : '#721c24';
        const borderColor = type === 'success' ? '#c3e6cb' : '#f5c6cb';

        responseDiv.innerHTML = `<div style="padding: 15px; border-radius: 8px; background: ${bgColor}; color: ${textColor}; border: 1px solid ${borderColor};">${message}</div>`;

        setTimeout(() => {
            responseDiv.innerHTML = '';
        }, 5000);
    }
}
