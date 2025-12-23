/**
 * Theme Toggle - Painel do Cliente
 *
 * Gerencia a troca entre temas claro e escuro.
 * Detecta preferencia do sistema e salva escolha do usuario.
 */

'use strict';

window.PainelCliente = window.PainelCliente || {};

PainelCliente.Theme = (function() {
  // Storage key for theme preference
  const STORAGE_KEY = 'painel-theme';

  // CSS transition class
  const TRANSITION_CLASS = 'theme-transition';

  // Available themes
  const THEMES = {
    LIGHT: 'light',
    DARK: 'dark',
    SYSTEM: 'system'
  };

  // Current theme
  let currentTheme = THEMES.LIGHT;

  /**
   * Get system color scheme preference
   */
  function getSystemPreference() {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return THEMES.DARK;
    }
    return THEMES.LIGHT;
  }

  /**
   * Get saved theme preference
   */
  function getSavedPreference() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      console.warn('[Theme] Could not access localStorage:', e);
      return null;
    }
  }

  /**
   * Save theme preference
   */
  function savePreference(theme) {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (e) {
      console.warn('[Theme] Could not save to localStorage:', e);
    }
  }

  /**
   * Apply theme to document
   */
  function applyTheme(theme, animate = false) {
    const html = document.documentElement;
    const effectiveTheme = theme === THEMES.SYSTEM ? getSystemPreference() : theme;

    // Add transition class for smooth theme change
    if (animate) {
      html.classList.add(TRANSITION_CLASS);

      // Remove transition class after animation completes
      setTimeout(() => {
        html.classList.remove(TRANSITION_CLASS);
      }, 300);
    }

    // Set theme attribute
    html.setAttribute('data-theme', effectiveTheme);

    // Update meta theme-color
    const metaThemeColor = document.getElementById('theme-color-meta');
    if (metaThemeColor) {
      const themeColor = effectiveTheme === THEMES.DARK ? '#0F0D1A' :
        getComputedStyle(html).getPropertyValue('--cor-primaria').trim() || '#8B5CF6';
      metaThemeColor.setAttribute('content', themeColor);
    }

    currentTheme = theme;

    // Dispatch custom event
    window.dispatchEvent(new CustomEvent('themechange', {
      detail: { theme: effectiveTheme, preference: theme }
    }));

    console.log(`[Theme] Applied: ${effectiveTheme} (preference: ${theme})`);
  }

  /**
   * Toggle between light and dark themes
   */
  function toggle() {
    const newTheme = currentTheme === THEMES.DARK ? THEMES.LIGHT : THEMES.DARK;
    setTheme(newTheme);
  }

  /**
   * Set specific theme
   */
  function setTheme(theme) {
    if (!Object.values(THEMES).includes(theme)) {
      console.warn(`[Theme] Invalid theme: ${theme}`);
      return;
    }

    savePreference(theme);
    applyTheme(theme, true);
  }

  /**
   * Get current theme
   */
  function getTheme() {
    return currentTheme;
  }

  /**
   * Get effective theme (resolved from system if needed)
   */
  function getEffectiveTheme() {
    return currentTheme === THEMES.SYSTEM ? getSystemPreference() : currentTheme;
  }

  /**
   * Check if dark mode is active
   */
  function isDark() {
    return getEffectiveTheme() === THEMES.DARK;
  }

  /**
   * Initialize theme toggle button
   */
  function initToggleButton() {
    const toggleBtn = document.getElementById('theme-toggle');

    if (!toggleBtn) return;

    toggleBtn.addEventListener('click', () => {
      toggle();
    });

    // Update button state
    const updateButtonState = () => {
      const isDarkMode = isDark();
      toggleBtn.setAttribute('aria-label', isDarkMode ? 'Ativar modo claro' : 'Ativar modo escuro');
      toggleBtn.setAttribute('title', isDarkMode ? 'Modo claro' : 'Modo escuro');
    };

    // Initial state
    updateButtonState();

    // Listen for theme changes
    window.addEventListener('themechange', updateButtonState);
  }

  /**
   * Listen for system preference changes
   */
  function initSystemListener() {
    if (!window.matchMedia) return;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const handleChange = (e) => {
      // Only react if using system preference
      if (currentTheme === THEMES.SYSTEM) {
        applyTheme(THEMES.SYSTEM, true);
      }
    };

    // Modern browsers
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
    } else {
      // Older browsers
      mediaQuery.addListener(handleChange);
    }
  }

  /**
   * Initialize the theme system
   */
  function init() {
    // Get initial theme
    const savedTheme = getSavedPreference();

    if (savedTheme) {
      currentTheme = savedTheme;
    } else {
      // Default to light, but respect system preference
      currentTheme = THEMES.LIGHT;
    }

    // Apply initial theme (without animation)
    applyTheme(currentTheme, false);

    // Initialize toggle button
    initToggleButton();

    // Listen for system preference changes
    initSystemListener();

    console.log('[Theme] Initialized');
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Public API
  return {
    toggle,
    setTheme,
    getTheme,
    getEffectiveTheme,
    isDark,
    THEMES
  };
})();

// Shorthand for easier access
window.Theme = PainelCliente.Theme;
