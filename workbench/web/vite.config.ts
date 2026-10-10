import { defineConfig } from 'vite';
export default defineConfig({
  base: '/',
  build: { assetsDir: 'static', chunkSizeWarningLimit: 800, rollupOptions: {
    output: { manualChunks(id) { if (id.includes('/three/')) return 'three'; } }
  } },
  server: { proxy: Object.fromEntries(['/api', '/assets', '/outputs', '/imports'].map(path => [path, 'http://127.0.0.1:8765'])) }
});
