import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Dev-only proxy target for the Flask API (never exposed to the browser bundle).
  const apiProxyTarget = env.API_PROXY_TARGET || "http://127.0.0.1:5000";

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": { target: apiProxyTarget, changeOrigin: true },
        // Uploaded, optimised media (Flask serves them in development; Nginx in production).
        "/media": { target: apiProxyTarget, changeOrigin: true },
      },
    },
    preview: { port: 4173 },
    build: {
      outDir: "dist",
      sourcemap: false,
    },
    ssr: {
      // Bundle these into the SSR build so the prerender script runs without extra resolution.
      noExternal: ["@reduxjs/toolkit", "react-redux", "lucide-react"],
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.js"],
      include: ["src/**/*.test.{js,jsx}"],
      css: false,
    },
  };
});
