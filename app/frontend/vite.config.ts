import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// One config for both the dev server and the test runner: the frontend has no
// build-time customisation worth splitting the file for.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Fail loudly instead of silently moving to 5174, because the backend's CORS
    // allow-list names 5173. A quiet port change would look like a CORS bug.
    strictPort: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    restoreMocks: true,
  },
});
