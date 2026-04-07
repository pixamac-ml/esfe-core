const defaultTheme = require('tailwindcss/defaultTheme');

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
  ],

  theme: {
    extend: {
      colors: {

        // 🔵 Primary Institutionnelle
        primary: {
          50:  '#eef4f7',
          100: '#d6e4ec',
          200: '#adc9d9',
          300: '#84aec6',
          400: '#5b93b3',
          500: '#1e4f6f',   // ✅ Couleur institutionnelle principale
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
      },
      fontFamily: {
        poppins: ['Poppins', ...defaultTheme.fontFamily.sans],
        roboto: ['Roboto', ...defaultTheme.fontFamily.sans],
        sans: ['Roboto', ...defaultTheme.fontFamily.sans],
      },
      borderRadius: {
        '4xl': '2rem',
      },
      boxShadow: {
        soft: '0 10px 30px -18px rgba(15, 23, 42, 0.22)',
        premium: '0 18px 48px -24px rgba(15, 23, 42, 0.28)',
        float: '0 24px 70px -30px rgba(15, 23, 42, 0.35)',
        glow: '0 16px 40px -24px rgba(29, 181, 176, 0.45)',
      },
      spacing: {
        18: '4.5rem',
        22: '5.5rem',
      },
      transitionTimingFunction: {
        premium: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },

  plugins: [],
};
