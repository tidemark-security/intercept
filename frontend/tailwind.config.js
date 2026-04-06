/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./src/ui/**/*.{tsx,ts,js,jsx}",
    "./node_modules/@tidemark-security/ux/dist/index.js",
  ],
  theme: {
    extend: {
      animation: {
        'slide-in-right': 'slideInRight 0.25s ease-out forwards',
      },
      keyframes: {
        slideInRight: {
          '0%': { clipPath: 'polygon(100% 0, 100% 0, 100% 100%, 100% 100%)', opacity: '0.3' },
          '100%': { clipPath: 'polygon(0 0, 100% 0, 100% 100%, 0 100%)', opacity: '1' },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
    function({ addBase, theme }) {
      addBase({
        '::selection': {
          backgroundColor: theme('colors.accent-1-primary'),
          color: theme('colors.black'),
        },
        '::-moz-selection': {
          backgroundColor: theme('colors.accent-1-primary'),
          color: theme('colors.black'),
        },
      })
    },
  ],
  presets: [require("./src/config/tailwind.config.js")]
};
