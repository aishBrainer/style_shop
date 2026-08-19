import type { Config } from 'tailwindcss'

/**
 * §45 — "Dark Premium AI Studio".
 *
 * Deliberately restrained: one accent, a narrow neutral ramp, subtle borders.
 * The spec explicitly warns against excessive neon and glassmorphism, and the
 * imagery is meant to be the hero, so the chrome stays quiet.
 */
const config: Config = {
  darkMode: 'class',
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Near-black with a hint of blue — pure #000 makes photography look
        // washed out by comparison.
        canvas: {
          DEFAULT: '#0a0b0f',
          raised: '#101219',
          overlay: '#161923',
        },
        edge: {
          DEFAULT: 'rgba(255,255,255,0.08)',
          strong: 'rgba(255,255,255,0.14)',
        },
        accent: {
          DEFAULT: '#7c5cff',
          hover: '#8f73ff',
          muted: 'rgba(124,92,255,0.14)',
        },
        ink: {
          DEFAULT: '#f2f3f7',
          muted: '#9aa0b4',
          faint: '#606779',
        },
        success: '#3ecf8e',
        warning: '#f0a03c',
        danger: '#f2555a',
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.25rem',
      },
      boxShadow: {
        panel: '0 1px 2px rgba(0,0,0,0.4), 0 8px 32px rgba(0,0,0,0.32)',
        glow: '0 0 0 1px rgba(124,92,255,0.35), 0 8px 40px rgba(124,92,255,0.18)',
      },
      keyframes: {
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(0.9)', opacity: '0.7' },
          '100%': { transform: 'scale(1.6)', opacity: '0' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.8s infinite',
        'fade-up': 'fade-up 0.4s ease-out both',
        'pulse-ring': 'pulse-ring 1.6s ease-out infinite',
      },
    },
  },
  plugins: [],
}

export default config
