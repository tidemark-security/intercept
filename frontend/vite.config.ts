import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import svgr from "vite-plugin-svgr"
import { resolve } from "node:path"

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), svgr()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
  // @ts-expect-error - Vitest configuration is supported via plugin but not typed in Vite's config schema yet.
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    globals: true,
    css: true,
  },
})
