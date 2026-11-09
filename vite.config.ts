import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/Transport3r/',
  plugins: [react()],
  build: {
    sourcemap: true,
    target: ['es2020', 'edge88', 'firefox78', 'chrome87', 'safari15'],
    chunkSizeWarningLimit: 1800,
  },
});
