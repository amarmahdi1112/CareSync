// Vite executes this config in Node; the application TypeScript project
// intentionally exposes only browser and extension ambient types.
// @ts-expect-error Node built-ins are available in the Vite config runtime.
import { readdirSync, rmSync } from 'node:fs';
// @ts-expect-error Node built-ins are available in the Vite config runtime.
import { resolve } from 'node:path';

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

function removeAppleDoubleFiles(directory: string): void {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.name.startsWith('._')) {
      rmSync(path, { force: true, recursive: true });
    } else if (entry.isDirectory()) {
      removeAppleDoubleFiles(path);
    }
  }
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'caresync-clean-extension-artifact',
      closeBundle() {
        removeAppleDoubleFiles(resolve('dist'));
      },
    },
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        panel: 'index.html',
        background: 'src/background.ts',
        content: 'src/content.ts',
      },
      output: {
        entryFileNames: (chunk) => chunk.name === 'panel' ? 'assets/[name]-[hash].js' : '[name].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  test: {
    exclude: ['**/node_modules/**', '**/dist/**', '**/._*'],
  },
});
