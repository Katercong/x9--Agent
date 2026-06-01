import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    server: {
        port: 5173,
        proxy: {
            // Forward all API + auth + asset traffic to the desktop backend
            // running on :8000. Lets the Vite dev server preview the new
            // /preview/* pages against real production data.
            '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, cookieDomainRewrite: '' },
            '/login': { target: 'http://127.0.0.1:8000', changeOrigin: true },
            '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
            '/portal': { target: 'http://127.0.0.1:8000', changeOrigin: true },
        },
    },
    build: {
        outDir: 'dist',
        sourcemap: false,
        chunkSizeWarningLimit: 1500,
        rollupOptions: {
            output: {
                manualChunks: {
                    echarts: ['echarts', 'echarts-for-react'],
                    react: ['react', 'react-dom', 'react-router-dom'],
                },
            },
        },
    },
});
