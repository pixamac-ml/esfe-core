const defaultTheme = require('tailwindcss/defaultTheme');

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
    "./ui/components/**/*.py",
    "./static/src/js/ui_core/**/*.js",
    "!./.claude/**",
  ],

  theme: {
    extend: {
      colors: {

        // 🔵 Primary Institutionnelle (DEFAULT + light requis pour bg-primary / hover:bg-primary-light)
        primary: {
          DEFAULT: '#1e4f6f',
          light: '#2d6a8f',
          foreground: '#ffffff',
          50: '#eef4f7',
          100: '#d6e4ec',
          200: '#adc9d9',
          300: '#84aec6',
          400: '#5b93b3',
          500: '#1e4f6f',
          600: '#1a4561',
          700: '#163b53',
          800: '#123145',
          900: '#0e2737',
        },

        // 🟢 Turquoise secondaire
        secondary: {
          DEFAULT: '#1db5b0',
          light: '#49c7c3',
          dark: '#179a96',
        },

        // 🟠 Accent (CTA, highlights)
        accent: {
          DEFAULT: '#f39c12',
          light: '#f7b955',
          dark: '#c87f0e',
        },

        // ⚪ Fond doux global
        soft: '#f4fbfb',
        ui: {
          primary: '#1e4f6f',
          'primary-strong': '#163b53',
          'primary-soft': '#eef4f7',
          accent: '#f4b942',
          'accent-strong': '#9a5b00',
          'accent-soft': '#fff7df',
          success: '#177245',
          'success-soft': '#eaf7f0',
          warning: '#9a5b00',
          'warning-soft': '#fff6dd',
          danger: '#b42318',
          'danger-soft': '#fff0ee',
          info: '#176b87',
          'info-soft': '#eaf7fb',
          surface: '#ffffff',
          'surface-soft': '#f8fafc',
          'surface-muted': '#eef2f6',
          'surface-hover': '#f1f5f9',
          active: '#e5eef4',
          selected: '#e8f3f5',
          skeleton: '#e2e8f0',
          'destructive-surface': '#fff0ee',
          border: '#dbe3ea',
          text: '#17212b',
          'text-muted': '#5f6f7f',
          sidebar: '#17394d',
          focus: '#1db5b0',
          'on-primary': '#ffffff',
          overlay: '#0f172a',
        },
      },
      fontFamily: {
        poppins: ['Poppins', ...defaultTheme.fontFamily.sans],
        roboto: ['Roboto', ...defaultTheme.fontFamily.sans],
        sans: ['Roboto', ...defaultTheme.fontFamily.sans],
      },
      borderRadius: {
        '4xl': '2rem',
        'ui-input': '0.375rem',
        'ui-button': '0.375rem',
        'ui-card': '0.5rem',
        'ui-modal': '0.5rem',
        'ui-badge': '9999px',
      },
      boxShadow: {
        soft: '0 10px 30px -18px rgba(15, 23, 42, 0.22)',
        premium: '0 18px 48px -24px rgba(15, 23, 42, 0.28)',
        float: '0 24px 70px -30px rgba(15, 23, 42, 0.35)',
        glow: '0 16px 40px -24px rgba(29, 181, 176, 0.45)',
        'ui-card': '0 1px 3px rgba(15, 23, 42, 0.08)',
        'ui-dropdown': '0 8px 24px rgba(15, 23, 42, 0.12)',
        'ui-drawer': '0 16px 48px rgba(15, 23, 42, 0.20)',
        'ui-modal': '0 20px 60px rgba(15, 23, 42, 0.24)',
      },
      spacing: {
        18: '4.5rem',
        22: '5.5rem',
        'ui-sidebar': '17rem',
        'ui-sidebar-collapsed': '4.5rem',
        'ui-topbar': '4rem',
        'ui-desktop': '2rem',
        'ui-tablet': '1.5rem',
        'ui-mobile': '1rem',
        'ui-control': '2.5rem',
        'ui-chart': '20rem',
        'ui-timeline-dot': '2rem',
      },
      maxWidth: {
        'ui-content': '90rem',
      },
      minWidth: {
        'ui-table': '36rem',
      },
      maxHeight: {
        'ui-overlay': '85vh',
        'ui-panel': '28rem',
      },
      zIndex: {
        'ui-skip': '100',
      },
      backdropBlur: {
        'ui-overlay': '1px',
      },
      fontSize: {
        'ui-display': ['2.25rem', { lineHeight: '2.75rem', fontWeight: '700' }],
        'ui-page-title': ['1.5rem', { lineHeight: '2rem', fontWeight: '700' }],
        'ui-section-title': ['1.125rem', { lineHeight: '1.75rem', fontWeight: '700' }],
        'ui-panel-title': ['1rem', { lineHeight: '1.5rem', fontWeight: '700' }],
        'ui-body': ['0.875rem', { lineHeight: '1.5rem' }],
        'ui-body-small': ['0.8125rem', { lineHeight: '1.25rem' }],
        'ui-label': ['0.75rem', { lineHeight: '1rem', fontWeight: '600' }],
        'ui-caption': ['0.6875rem', { lineHeight: '1rem' }],
        'ui-micro': ['0.625rem', { lineHeight: '0.875rem' }],
      },
      transitionTimingFunction: {
        premium: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },

  plugins: [],
};
