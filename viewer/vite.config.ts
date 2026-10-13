/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { createReadStream, statSync } from 'node:fs';
import { extname, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url));

const TYPES: Record<string, string> = {
  '.json': 'application/json; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.mmd': 'text/plain; charset=utf-8',
};

/** Dev only: serve the kb directory (env READCODE_KB, default ../examples/kb) at /kb/. */
function serveKb(): Plugin {
  const kbRoot = resolve(here, process.env.READCODE_KB ?? '../examples/kb');
  return {
    name: 'readcode-serve-kb',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/kb', (req, res, next) => {
        let rel: string;
        try {
          rel = decodeURIComponent((req.url ?? '/').split('?')[0]);
        } catch {
          res.statusCode = 400;
          return res.end();
        }
        const target = resolve(kbRoot, '.' + rel);
        if (target !== kbRoot && !target.startsWith(kbRoot + sep)) {
          res.statusCode = 404;
          return res.end('404 Not Found');
        }
        let ok = false;
        try {
          ok = statSync(target).isFile();
        } catch {
          ok = false;
        }
        if (!ok) {
          if (req.method !== 'GET' && req.method !== 'HEAD') return next();
          res.statusCode = 404;
          return res.end('404 Not Found');
        }
        res.setHeader('Content-Type', TYPES[extname(target).toLowerCase()] ?? 'application/octet-stream');
        res.setHeader('Cache-Control', 'no-cache');
        createReadStream(target).pipe(res);
      });
    },
  };
}

export default defineConfig({
  base: './',
  plugins: [svelte(), serveKb()],
  build: {
    outDir: '../core/readcode/viewer_dist',
    emptyOutDir: true,
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
});
