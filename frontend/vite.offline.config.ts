import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',
  input: 'offline.html',
  publicDir: 'offline-public',
  build: {
    outDir: 'dist-offline',
    target: 'es2020',
    modulePreload: { polyfill: false },
    assetsInlineLimit: 0,
  },
});
