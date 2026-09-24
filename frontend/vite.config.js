import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import copy from 'rollup-plugin-copy';

// Dev server proxies /api to the FastAPI backend so `npm run dev` works
// against a locally running `uvicorn main:app --reload` without CORS
// headaches. The production build (used by run.ps1/run.bat) doesn't need
// this proxy since FastAPI serves the built frontend itself, same origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      external: ['soundtouch-audio-worklet'],
    },
  },
});
