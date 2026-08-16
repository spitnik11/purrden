import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";
import path from "node:path";

export default defineConfig({
  resolve: {
    alias: {
      "@content": path.resolve(__dirname, "../../content"),
      "@spawn": path.resolve(__dirname, "../../packages/spawn-engine-js/src"),
      "@domain": path.resolve(__dirname, "../../packages/domain-ts"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Dev: browser calls /api/* → local FastAPI (Purrden-API-Dev.bat)
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
  plugins: [
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "Purrden",
        short_name: "Purrden",
        description: "Pixel-art cat garden × focus timer",
        theme_color: "#1a1c2c",
        background_color: "#1a1c2c",
        display: "standalone",
        start_url: "/",
        icons: [
          {
            src: "favicon.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        // Cache app shell + static assets only. Never cache API or save blobs.
        globPatterns: ["**/*.{js,css,html,svg,png,json,woff2}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
});
