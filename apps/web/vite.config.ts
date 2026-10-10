import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The API runs separately (uvicorn); the dev server proxies to it so the app and API share an origin.
const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  build: { target: "es2022" }, // top-level await in main.tsx (auth start-up)
  server: {
    port: Number(process.env.WEB_PORT ?? 5173),
    proxy: { "/api": backend, "/dev": backend, "/auth": backend },
  },
});
