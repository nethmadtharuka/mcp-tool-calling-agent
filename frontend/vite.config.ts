/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import pkg from "./package.json" with { type: "json" };

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Dev only: with VITE_API_BASE_URL unset, the app calls same-origin
  // /api and /health, and the dev server forwards them to the backend.
  // No CORS needed locally. Never part of the production bundle.
  const target = env.VITE_DEV_PROXY_TARGET || "http://127.0.0.1:8000";
  const proxy = { "/api": target, "/health": target };

  return {
    plugins: [react(), tailwindcss()],
    define: { __APP_VERSION__: JSON.stringify(pkg.version) },
    server: { proxy },
    preview: { proxy },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      restoreMocks: true,
    },
  };
});
