import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages base path - set via environment variable or default to repo name
// For local dev, leave empty. For GitHub Pages, use: /COMMAND_UI/
const base = process.env.VITE_BASE_PATH || process.env.GITHUB_PAGES_BASE || "/";

export default defineConfig({
  base,
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
    sourcemap: false,
    minify: "esbuild",
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom"],
        },
      },
    },
  },
});
