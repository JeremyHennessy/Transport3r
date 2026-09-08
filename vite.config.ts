import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/Transport3r/',
  build: {
    sourcemap: true,
    chunkSizeWarningLimit: 1000,
  },
});
