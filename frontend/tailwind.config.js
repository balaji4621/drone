/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Ultra-dark theme: #050507 base
        'nesfic': {
          50: '#f0f0f5',
          100: '#e0e0eb',
          200: '#c1c1d7',
          300: '#9494b8',
          400: '#6b6b94',
          500: '#4a4a70',
          600: '#353552',
          700: '#24243d',
          800: '#141424',
          900: '#0a0a12',
          950: '#050507',  // Base background
        },
        // Accent colors
        'accent': {
          cyan: '#00f5d4',
          amber: '#ffb800',
          red: '#ff4757',
          green: '#2ed573',
          blue: '#3742fa',
          purple: '#a55eea',
        },
        // Glassmorphic surfaces
        'glass': {
          light: 'rgba(255, 255, 255, 0.03)',
          medium: 'rgba(255, 255, 255, 0.05)',
          heavy: 'rgba(255, 255, 255, 0.08)',
          border: 'rgba(255, 255, 255, 0.1)',
          borderBright: 'rgba(255, 255, 255, 0.15)',
        },
      },
      backgroundImage: {
        'grid-pattern': 'linear-gradient(rgba(0, 245, 212, 0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0, 245, 212, 0.03) 1px, transparent 1px)',
        'radial-glow': 'radial-gradient(ellipse at center, rgba(0, 245, 212, 0.15) 0%, transparent 70%)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 20s linear infinite',
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.4s ease-out',
        'blink': 'blink 1s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
      },
      boxShadow: {
        'glow-cyan': '0 0 20px rgba(0, 245, 212, 0.3), 0 0 40px rgba(0, 245, 212, 0.1)',
        'glow-amber': '0 0 20px rgba(255, 184, 0, 0.3), 0 0 40px rgba(255, 184, 0, 0.1)',
        'glow-red': '0 0 20px rgba(255, 71, 87, 0.3), 0 0 40px rgba(255, 71, 87, 0.1)',
        'inner-glass': 'inset 0 1px 0 rgba(255, 255, 255, 0.1), inset 0 -1px 0 rgba(0, 0, 0, 0.2)',
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
}