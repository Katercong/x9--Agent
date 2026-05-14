import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eff5ff',
          100: '#dbe7ff',
          200: '#bed1ff',
          300: '#94b1ff',
          400: '#6087ff',
          500: '#3370ff',
          600: '#2050d4',
          700: '#1a3fa8',
          800: '#162f80',
          900: '#101f55',
        },
        sidebar: {
          DEFAULT: '#1f1f2e',
          hover: '#2a2a3d',
          text: '#b8b8c4',
          'text-active': '#ffffff',
        },
        accent: {
          orange: '#f97316',
          'orange-bg': '#fef3eb',
          'orange-text': '#d97706',
        },
        good: '#16a34a',
        warn: '#f5a623',
        bad: '#ef4444',
        muted: '#86909c',
        line: '#e5e6eb',
        soft: '#f7f7f9',
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'Roboto',
          '"Helvetica Neue"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          'sans-serif',
        ],
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
        '3xl': ['26px', '1.2'],
        '4xl': ['32px', '1.2'],
      },
      borderRadius: {
        DEFAULT: '6px',
        sm: '4px',
        md: '8px',
        lg: '10px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(0,0,0,0.04), 0 1px 1px rgba(0,0,0,0.02)',
        soft: '0 2px 8px rgba(0,0,0,0.05)',
      },
    },
  },
  plugins: [],
} satisfies Config;
