/**
 * Toast.js - Painel do Cliente
 *
 * Sistema de notificações toast.
 * Suporta diferentes tipos: success, error, warning, info
 */

'use strict';

window.PainelCliente = window.PainelCliente || {};

PainelCliente.Toast = (function() {
  // Configuration
  const config = {
    duration: 5000,        // Default duration in ms
    position: 'bottom-right', // Position of toast container
    maxToasts: 5,          // Maximum toasts visible at once
    pauseOnHover: true,    // Pause auto-dismiss on hover
    closeOnClick: true     // Close toast on click
  };

  // Toast container
  let container = null;

  // Active toasts
  const toasts = new Map();

  // Icons for each toast type
  const icons = {
    success: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
      <polyline points="22 4 12 14.01 9 11.01"></polyline>
    </svg>`,
    error: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"></circle>
      <line x1="15" y1="9" x2="9" y2="15"></line>
      <line x1="9" y1="9" x2="15" y2="15"></line>
    </svg>`,
    warning: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
      <line x1="12" y1="9" x2="12" y2="13"></line>
      <line x1="12" y1="17" x2="12.01" y2="17"></line>
    </svg>`,
    info: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"></circle>
      <line x1="12" y1="16" x2="12" y2="12"></line>
      <line x1="12" y1="8" x2="12.01" y2="8"></line>
    </svg>`
  };

  /**
   * Initialize the toast container
   */
  function init() {
    container = document.getElementById('toast-container');

    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      container.setAttribute('aria-live', 'polite');
      container.setAttribute('aria-atomic', 'true');
      document.body.appendChild(container);
    }
  }

  /**
   * Create a toast element
   */
  function createToastElement(options) {
    const { id, type, title, message } = options;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    toast.dataset.toastId = id;

    toast.innerHTML = `
      <span class="toast-icon">${icons[type]}</span>
      <div class="toast-content">
        ${title ? `<div class="toast-title">${escapeHtml(title)}</div>` : ''}
        <div class="toast-message">${escapeHtml(message)}</div>
      </div>
      <button type="button" class="toast-close" aria-label="Fechar">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    `;

    return toast;
  }

  /**
   * Escape HTML to prevent XSS
   */
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Generate unique ID
   */
  function generateId() {
    return 'toast-' + Math.random().toString(36).substr(2, 9);
  }

  /**
   * Show a toast notification
   */
  function show(options) {
    if (!container) init();

    const id = generateId();
    const toastOptions = {
      id,
      type: options.type || 'info',
      title: options.title || '',
      message: options.message || '',
      duration: options.duration !== undefined ? options.duration : config.duration
    };

    // Limit number of toasts
    while (toasts.size >= config.maxToasts) {
      const firstId = toasts.keys().next().value;
      dismiss(firstId);
    }

    const toastElement = createToastElement(toastOptions);
    container.appendChild(toastElement);

    // Setup close button
    const closeBtn = toastElement.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => dismiss(id));

    // Setup click to close
    if (config.closeOnClick) {
      toastElement.addEventListener('click', (e) => {
        if (e.target !== closeBtn && !closeBtn.contains(e.target)) {
          dismiss(id);
        }
      });
    }

    // Setup auto-dismiss timer
    let timeoutId = null;
    let remainingTime = toastOptions.duration;
    let startTime = Date.now();

    const startTimer = () => {
      if (remainingTime > 0) {
        timeoutId = setTimeout(() => dismiss(id), remainingTime);
        startTime = Date.now();
      }
    };

    const pauseTimer = () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
        remainingTime -= Date.now() - startTime;
      }
    };

    if (config.pauseOnHover && toastOptions.duration > 0) {
      toastElement.addEventListener('mouseenter', pauseTimer);
      toastElement.addEventListener('mouseleave', startTimer);
    }

    // Start timer
    startTimer();

    // Store toast data
    toasts.set(id, {
      element: toastElement,
      timeoutId,
      options: toastOptions
    });

    // Trigger animation
    requestAnimationFrame(() => {
      toastElement.classList.add('toast-enter');
    });

    return id;
  }

  /**
   * Dismiss a toast
   */
  function dismiss(id) {
    const toastData = toasts.get(id);
    if (!toastData) return;

    const { element, timeoutId } = toastData;

    // Clear timeout
    if (timeoutId) clearTimeout(timeoutId);

    // Add exit animation
    element.classList.add('toast-exit');
    element.classList.remove('toast-enter');

    // Remove after animation
    element.addEventListener('animationend', () => {
      element.remove();
      toasts.delete(id);
    }, { once: true });

    // Fallback removal if animation doesn't fire
    setTimeout(() => {
      if (element.parentNode) {
        element.remove();
        toasts.delete(id);
      }
    }, 300);
  }

  /**
   * Dismiss all toasts
   */
  function dismissAll() {
    toasts.forEach((_, id) => dismiss(id));
  }

  /**
   * Show success toast
   */
  function success(message, title = '', duration) {
    return show({ type: 'success', message, title, duration });
  }

  /**
   * Show error toast
   */
  function error(message, title = '', duration) {
    return show({ type: 'error', message, title, duration });
  }

  /**
   * Show warning toast
   */
  function warning(message, title = '', duration) {
    return show({ type: 'warning', message, title, duration });
  }

  /**
   * Show info toast
   */
  function info(message, title = '', duration) {
    return show({ type: 'info', message, title, duration });
  }

  /**
   * Configure toast options
   */
  function configure(options) {
    Object.assign(config, options);
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Public API
  return {
    show,
    dismiss,
    dismissAll,
    success,
    error,
    warning,
    info,
    configure
  };
})();

// Shorthand for easier access
window.Toast = PainelCliente.Toast;
