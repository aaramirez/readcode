import { defineConfig, devices } from '@playwright/test';

// End-to-end tests against the real Python server (`readcode serve`) serving the
// BUILT viewer (core/readcode/viewer_dist) and the example kb. `npm run e2e` builds first.
const PORT = 8799;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    viewport: { width: 1400, height: 900 },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1400, height: 900 } } }],
  webServer: {
    command: `readcode serve ../examples/kb --port ${PORT} --no-open`,
    url: `http://127.0.0.1:${PORT}/kb/catalog.json`,
    reuseExistingServer: false,
    timeout: 30_000,
    // the server logs every request to stderr; keep the test output readable
    stderr: 'ignore',
  },
});
