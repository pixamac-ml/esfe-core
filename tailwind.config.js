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
    },
  },

  plugins: [],
};
