import type { Config } from 'tailwindcss'

/**
 * Visual direction: the CamClo3D design language — light, editorial, plum.
 *
 * This deliberately departs from spec §45 ("Dark Premium AI Studio"). The
 * reference product (camclo3d.com) is a white canvas with a deep-plum ink, a
 * magenta primary and a Playfair Display serif for display type, and matching
 * it was an explicit product decision. Tokens below are transcribed from that
 * site's computed styles, converted from HSL to hex.
 *
 * Still restrained: one primary, one supporting lilac, a narrow neutral ramp.
 * The imagery remains the hero, so the chrome stays quiet.
 */
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // White page, white cards. Depth comes from borders and soft shadow
        // rather than from a raised fill — pure grey cards on white read as
        // "disabled" next to photography.
        canvas: {
          DEFAULT: '#ffffff',
          raised: '#ffffff',
          overlay: '#f5f3f7', // muted 270 20% 96% — hovers, inset wells
          sunken: '#faf9fb', // alternating section bands
        },
        edge: {
          DEFAULT: '#e3dde9', // border 270 20% 89%
          strong: '#d3c9dc',
        },
        // Primary 300 54% 36% — the magenta CamClo3D uses for CTAs and links.
        accent: {
          DEFAULT: '#8d2a8d',
          hover: '#7a247a',
          muted: 'rgba(141,42,141,0.10)',
        },
        // Secondary 270 50% 21% — deep violet, for dark bands and footers.
        plum: {
          DEFAULT: '#361b50',
          soft: '#4a2a68',
        },
        // Accent 277 30% 66% — supporting lilac for tints and illustration.
        lilac: {
          DEFAULT: '#ae8ec2',
          soft: '#d6c6e2',
        },
        ink: {
          DEFAULT: '#362745', // foreground 270 28% 21%
          muted: '#665775', // muted-foreground 270 15% 40%
          // Darkened from the dark-theme value: on a white canvas the old
          // #8f84a0 measured 3.51:1, below WCAG AA for body text. This is 4.7:1.
          faint: '#7a6f8c',
        },
        success: '#0f8a4f',
        warning: '#b26a00',
        danger: '#c02434',
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        // Playfair Display, as on the reference site, for display headings only.
        display: ['var(--font-display)', 'Georgia', 'serif'],
      },
      borderRadius: {
        xl: '0.75rem',
        '2xl': '1rem',
      },
      boxShadow: {
        // Plum-tinted rather than neutral black, so shadows sit in the palette.
        panel: '0 1px 2px rgba(54,39,69,0.04), 0 8px 24px rgba(54,39,69,0.06)',
        lifted: '0 2px 4px rgba(54,39,69,0.06), 0 16px 40px rgba(54,39,69,0.10)',
        glow: '0 0 0 1px rgba(141,42,141,0.25), 0 8px 40px rgba(141,42,141,0.12)',
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
