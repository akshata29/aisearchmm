import { defineConfig } from 'vite';
import basicSsl from '@vitejs/plugin-basic-ssl';
import react from '@vitejs/plugin-react';
import path from 'path';

// Vite configuration dedicated to the personal tab experience.
export default defineConfig(({ mode }) => {
  const isDev = mode === 'development';
  const tabRoot = path.resolve(__dirname);

  return {
    plugins: [react(), basicSsl()],
    root: tabRoot,
    base: '/',
    resolve: {
      alias: {
        '~': path.resolve(__dirname, 'src'),
        '@/components': path.resolve(__dirname, 'src/components'),
        '@/hooks': path.resolve(__dirname, 'src/hooks'),
        '@/styles': path.resolve(__dirname, 'src/styles'),
        '@/lib': path.resolve(__dirname, 'src/lib')
      }
    },
    build: {
      outDir: path.resolve(__dirname, '../dist/tab'),
      emptyOutDir: true,
      sourcemap: isDev,
      target: 'esnext'
    },
    server: {
      host: true,
      port: 5300,
      strictPort: true,
      https: true,
      open: false,
      proxy: {
        '/chat': {
          target: process.env.RAG_API_BASE_URL ?? 'http://localhost:5000'
        },
        '/api': {
          target: process.env.RAG_API_BASE_URL ?? 'http://localhost:5000'
        },
        '/upload': {
          target: process.env.RAG_API_BASE_URL ?? 'http://localhost:5000'
        }
      }
    },
    preview: {
      host: true,
      port: 5300,
      https: true
    }
  };
});
