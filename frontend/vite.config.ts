import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // Docker bind mounts and nested workspaces can otherwise surface a second
    // React copy at dev time, which breaks hooks with "invalid hook call".
    dedupe: ['react', 'react-dom'],
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8101',
        changeOrigin: true,
      },
    },
  },
});
