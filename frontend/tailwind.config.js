/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#FAF8FC',
          100: '#F2ECF8',
          200: '#E5D9F0',
          300: '#D1BFE3',
          400: '#B89AD0',
          500: '#8967A4',
          600: '#8967A4',
          700: '#674D7B',
          800: '#4D3A5C',
          900: '#33263D',
        },
        secondary: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
        }
      },
      fontFamily: {
        sans: ['Comfortaa', 'system-ui', 'sans-serif'],
        comfortaa: ['Comfortaa', 'system-ui', 'sans-serif'],
      },
      fontWeight: {
        'light': '300',
        'normal': '400',
        'medium': '500',
        'semibold': '600',
        'bold': '700',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
}
