import type { Config } from 'tailwindcss';

// 用户端配色 — 镜像 desktop/backend/ui/theme.css 的深色主题
// --accent 是青蓝渐变,--bg 是深蓝灰
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: 'rgb(var(--bg) / <alpha-value>)',
        elev1: 'rgb(var(--bg-elev-1) / <alpha-value>)',
        elev2: 'rgb(var(--bg-elev-2) / <alpha-value>)',
        text: 'rgb(var(--text) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        border: 'rgb(var(--border) / <alpha-value>)',
        accent: 'rgb(var(--accent) / <alpha-value>)',
        good: 'rgb(var(--good) / <alpha-value>)',
        warn: 'rgb(var(--warn) / <alpha-value>)',
        bad: 'rgb(var(--bad) / <alpha-value>)',
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Consolas', 'monospace'],
      },
      fontSize: {
        xxs: ['11px', '1.4'],
        xs: ['12px', '1.5'],
        sm: ['13px', '1.6'],
        base: ['14px', '1.6'],
        lg: ['16px', '1.5'],
        xl: ['18px', '1.4'],
        '2xl': ['22px', '1.3'],
        '3xl': ['28px', '1.2'],
      },
      borderRadius: {
        DEFAULT: '8px',
        sm: '4px',
        md: '10px',
        lg: '14px',
        pill: '999px',
      },
      boxShadow: {
        card: '0 1px 3px rgba(0,0,0,0.16), 0 1px 2px rgba(0,0,0,0.10)',
        soft: '0 6px 24px rgba(0,0,0,0.25)',
      },
    },
  },
  plugins: [],
} satisfies Config;
