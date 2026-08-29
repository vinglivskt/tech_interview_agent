import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// In Docker, the api service is reachable as "api:8000".
// In local dev, the backend runs on localhost:8000.
// Allow override via VITE_API_URL env var.
const apiTarget = process.env.VITE_API_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
