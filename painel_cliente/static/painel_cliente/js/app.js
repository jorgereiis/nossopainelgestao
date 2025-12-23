/**
 * App.js - Painel do Cliente
 *
 * Arquivo principal de inicialização JavaScript.
 * Contém:
 * - Utilitários globais
 * - Inicialização de componentes
 * - Event handlers comuns
 * - Funções de formatação
 */

'use strict';

// ========================================
// NAMESPACE
// ========================================

window.PainelCliente = window.PainelCliente || {};

// ========================================
// UTILITIES
// ========================================

PainelCliente.utils = {
  /**
   * Debounce function
   */
  debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  },

  /**
   * Throttle function
   */
  throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
      if (!inThrottle) {
        func(...args);
        inThrottle = true;
        setTimeout(() => inThrottle = false, limit);
      }
    };
  },

  /**
   * Format currency (BRL)
   */
  formatCurrency(value) {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value);
  },

  /**
   * Format date
   */
  formatDate(date, options = {}) {
    const defaultOptions = {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric'
    };
    return new Intl.DateTimeFormat('pt-BR', { ...defaultOptions, ...options }).format(new Date(date));
  },

  /**
   * Format phone number
   */
  formatPhone(phone) {
    const cleaned = phone.replace(/\D/g, '');
    if (cleaned.length === 11) {
      return cleaned.replace(/(\d{2})(\d{5})(\d{4})/, '($1) $2-$3');
    } else if (cleaned.length === 10) {
      return cleaned.replace(/(\d{2})(\d{4})(\d{4})/, '($1) $2-$3');
    }
    return phone;
  },

  /**
   * Format CPF
   */
  formatCPF(cpf) {
    const cleaned = cpf.replace(/\D/g, '');
    return cleaned.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, '$1.$2.$3-$4');
  },

  /**
   * Validate CPF
   */
  validateCPF(cpf) {
    const cleaned = cpf.replace(/\D/g, '');

    if (cleaned.length !== 11) return false;
    if (/^(\d)\1{10}$/.test(cleaned)) return false;

    let sum = 0;
    for (let i = 0; i < 9; i++) {
      sum += parseInt(cleaned.charAt(i)) * (10 - i);
    }
    let remainder = (sum * 10) % 11;
    if (remainder === 10 || remainder === 11) remainder = 0;
    if (remainder !== parseInt(cleaned.charAt(9))) return false;

    sum = 0;
    for (let i = 0; i < 10; i++) {
      sum += parseInt(cleaned.charAt(i)) * (11 - i);
    }
    remainder = (sum * 10) % 11;
    if (remainder === 10 || remainder === 11) remainder = 0;
    if (remainder !== parseInt(cleaned.charAt(10))) return false;

    return true;
  },

  /**
   * Validate email
   */
  validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
  },

  /**
   * Copy text to clipboard
   */
  async copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      // Fallback for older browsers
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      try {
        document.execCommand('copy');
        textArea.remove();
        return true;
      } catch (err) {
        textArea.remove();
        return false;
      }
    }
  },

  /**
   * Generate random string
   */
  randomString(length = 8) {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < length; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
  },

  /**
   * Check if element is in viewport
   */
  isInViewport(element) {
    const rect = element.getBoundingClientRect();
    return (
      rect.top >= 0 &&
      rect.left >= 0 &&
      rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
      rect.right <= (window.innerWidth || document.documentElement.clientWidth)
    );
  },

  /**
   * Smooth scroll to element
   */
  scrollToElement(element, offset = 0) {
    const elementPosition = element.getBoundingClientRect().top;
    const offsetPosition = elementPosition + window.pageYOffset - offset;

    window.scrollTo({
      top: offsetPosition,
      behavior: 'smooth'
    });
  }
};

// ========================================
// DROPDOWN COMPONENT
// ========================================

PainelCliente.Dropdown = {
  init() {
    document.querySelectorAll('.dropdown').forEach(dropdown => {
      this.setupDropdown(dropdown);
    });

    // Close dropdowns when clicking outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.dropdown')) {
        this.closeAll();
      }
    });

    // Close dropdowns on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.closeAll();
      }
    });
  },

  setupDropdown(dropdown) {
    const trigger = dropdown.querySelector('[aria-expanded]');
    const menu = dropdown.querySelector('.dropdown-menu');

    if (!trigger || !menu) return;

    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = dropdown.classList.contains('is-open');

      // Close all other dropdowns
      this.closeAll();

      if (!isOpen) {
        dropdown.classList.add('is-open');
        trigger.setAttribute('aria-expanded', 'true');
      }
    });

    // Handle keyboard navigation
    trigger.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        dropdown.classList.add('is-open');
        trigger.setAttribute('aria-expanded', 'true');
        const firstItem = menu.querySelector('.dropdown-item');
        if (firstItem) firstItem.focus();
      }
    });

    menu.querySelectorAll('.dropdown-item').forEach((item, index, items) => {
      item.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          const next = items[index + 1];
          if (next) next.focus();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          const prev = items[index - 1];
          if (prev) prev.focus();
          else trigger.focus();
        }
      });
    });
  },

  closeAll() {
    document.querySelectorAll('.dropdown.is-open').forEach(dropdown => {
      dropdown.classList.remove('is-open');
      const trigger = dropdown.querySelector('[aria-expanded]');
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
    });
  }
};

// ========================================
// RIPPLE EFFECT
// ========================================

PainelCliente.Ripple = {
  init() {
    document.querySelectorAll('.ripple-container, .btn').forEach(element => {
      element.addEventListener('click', this.createRipple.bind(this));
    });
  },

  createRipple(event) {
    const element = event.currentTarget;

    // Skip if disabled
    if (element.disabled || element.classList.contains('disabled')) return;

    const ripple = document.createElement('span');
    ripple.classList.add('ripple');

    const rect = element.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height);
    const x = event.clientX - rect.left - size / 2;
    const y = event.clientY - rect.top - size / 2;

    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;

    // Remove existing ripples
    const existingRipple = element.querySelector('.ripple');
    if (existingRipple) existingRipple.remove();

    element.appendChild(ripple);

    // Remove ripple after animation
    ripple.addEventListener('animationend', () => ripple.remove());
  }
};

// ========================================
// FORM HANDLERS
// ========================================

PainelCliente.Forms = {
  init() {
    this.setupInputMasks();
    this.setupValidation();
    this.setupFloatingLabels();
  },

  setupInputMasks() {
    // Phone mask
    document.querySelectorAll('input[data-mask="phone"]').forEach(input => {
      input.addEventListener('input', (e) => {
        let value = e.target.value.replace(/\D/g, '');
        if (value.length <= 11) {
          if (value.length > 6) {
            if (value.length > 10) {
              value = value.replace(/(\d{2})(\d{5})(\d{4})/, '($1) $2-$3');
            } else {
              value = value.replace(/(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3');
            }
          } else if (value.length > 2) {
            value = value.replace(/(\d{2})(\d{0,5})/, '($1) $2');
          }
        }
        e.target.value = value;
      });
    });

    // CPF mask
    document.querySelectorAll('input[data-mask="cpf"]').forEach(input => {
      input.addEventListener('input', (e) => {
        let value = e.target.value.replace(/\D/g, '');
        if (value.length <= 11) {
          value = value.replace(/(\d{3})(\d{3})(\d{3})(\d{0,2})/, (match, p1, p2, p3, p4) => {
            let result = p1;
            if (p2) result += '.' + p2;
            if (p3) result += '.' + p3;
            if (p4) result += '-' + p4;
            return result;
          });
        }
        e.target.value = value;
      });
    });

    // Currency mask
    document.querySelectorAll('input[data-mask="currency"]').forEach(input => {
      input.addEventListener('input', (e) => {
        let value = e.target.value.replace(/\D/g, '');
        value = (parseInt(value) / 100).toFixed(2);
        value = value.replace('.', ',');
        value = value.replace(/(\d)(?=(\d{3})+(?!\d))/g, '$1.');
        e.target.value = 'R$ ' + value;
      });
    });
  },

  setupValidation() {
    document.querySelectorAll('form[data-validate]').forEach(form => {
      form.addEventListener('submit', (e) => {
        if (!form.checkValidity()) {
          e.preventDefault();
          e.stopPropagation();
        }
        form.classList.add('was-validated');
      });
    });
  },

  setupFloatingLabels() {
    document.querySelectorAll('.form-floating input, .form-floating textarea').forEach(input => {
      // Check initial value
      if (input.value) {
        input.classList.add('has-value');
      }

      input.addEventListener('focus', () => input.classList.add('has-focus'));
      input.addEventListener('blur', () => {
        input.classList.remove('has-focus');
        if (!input.value) input.classList.remove('has-value');
      });
      input.addEventListener('input', () => {
        if (input.value) input.classList.add('has-value');
        else input.classList.remove('has-value');
      });
    });
  }
};

// ========================================
// AJAX HELPERS
// ========================================

PainelCliente.ajax = {
  /**
   * Make an AJAX request with CSRF token
   */
  async request(url, options = {}) {
    const defaults = {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.CSRF_TOKEN || this.getCSRFToken()
      }
    };

    const config = { ...defaults, ...options };

    if (config.body && typeof config.body === 'object') {
      config.body = JSON.stringify(config.body);
    }

    try {
      const response = await fetch(url, config);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return await response.json();
      }

      return await response.text();
    } catch (error) {
      console.error('AJAX request failed:', error);
      throw error;
    }
  },

  /**
   * Get CSRF token from cookie
   */
  getCSRFToken() {
    const name = 'csrftoken';
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
      const [cookieName, cookieValue] = cookie.trim().split('=');
      if (cookieName === name) {
        return cookieValue;
      }
    }
    return '';
  },

  /**
   * POST request helper
   */
  post(url, data) {
    return this.request(url, {
      method: 'POST',
      body: data
    });
  },

  /**
   * GET request helper
   */
  get(url) {
    return this.request(url);
  }
};

// ========================================
// LOADING STATE
// ========================================

PainelCliente.Loading = {
  show(element) {
    if (!element) return;

    element.classList.add('is-loading');
    element.disabled = true;

    // Store original content
    element.dataset.originalContent = element.innerHTML;

    // Add spinner
    element.innerHTML = `
      <span class="spinner spinner-sm"></span>
      <span>Carregando...</span>
    `;
  },

  hide(element) {
    if (!element) return;

    element.classList.remove('is-loading');
    element.disabled = false;

    // Restore original content
    if (element.dataset.originalContent) {
      element.innerHTML = element.dataset.originalContent;
      delete element.dataset.originalContent;
    }
  }
};

// ========================================
// INITIALIZATION
// ========================================

document.addEventListener('DOMContentLoaded', () => {
  // Initialize components
  PainelCliente.Dropdown.init();
  PainelCliente.Forms.init();

  // Initialize ripple effect if enabled
  if (document.querySelector('.ripple-container, .btn')) {
    PainelCliente.Ripple.init();
  }

  // Add loaded class to body for animations
  document.body.classList.add('app-loaded');

  console.log('[PainelCliente] App initialized');
});

// ========================================
// EXPORT FOR MODULE SYSTEMS
// ========================================

if (typeof module !== 'undefined' && module.exports) {
  module.exports = PainelCliente;
}
