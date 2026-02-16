module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
  ],
theme: {
  extend: {
    colors: {
      primary: {
        50: '#eef4ff',
        100: '#d9e6ff',
        200: '#b3ccff',
        300: '#80aaff',
        400: '#4d88ff',
        500: '#1a66ff',
        600: '#0f4dcc',
        700: '#0c3da3',
        800: '#092e7a',
        900: '#061f52',
      }
    }
  }
},

  plugins: [],

  extend: {
  colors: {
    primary: "#0F4C5C",      // turquoise profond
    secondary: "#1AA6B7",    // turquoise standard
    soft: "#F4F8F9",         // fond doux
    accent: "#F4C430"        // accent discret
  }
}

}
