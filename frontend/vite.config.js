import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

const backendTarget = process.env.BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [svelte()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true
      },
      "/uploads": {
        target: backendTarget,
        changeOrigin: true
      }
    }
  }
});