import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

import pkg from "./package.json";

// The UI's own version, baked in at build time - the same thing the Content
// Editor does with its __APP_VERSION__. The backend reports its version over
// the API; carrying the UI's separately is what lets the status bar notice a
// stale bundle served by a newer backend, or the other way round.
const appVersion: string = pkg.version;

/*
 * The Exam Bank's front end. A plain browser app that talks to the
 * FastAPI backend (`python -m exam_bank.api`, port 7788) over HTTP and
 * holds no business logic of its own — the bank, the generator and the
 * exporters all live in Python and are reached through the API.
 *
 * Ports: 7789 pairs with the 7788 backend, and both sit well clear of the
 * other Pentaho apps on this machine. 5273 is the Content Editor's Vite and
 * 5681 is Media Studio's; Media Studio already had to move off 5273 once
 * because of that collision, so this app does not go near either.
 *
 * The dev server proxies /api so the front end is same-origin while it is
 * being developed. The API does allow cross-origin calls from localhost, but
 * relying on that would mean developing against a different origin policy
 * than the one the built app runs under.
 */
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion),
  },
  server: {
    port: 7789,
    strictPort: true, // fail loudly rather than drift to another port
    proxy: {
      "/api": { target: "http://127.0.0.1:7788", changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
