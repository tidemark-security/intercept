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
      // Force UX file: linked package to use TMI's copies of React/router
      // to avoid dual-instance issues in tests
      react: resolve(__dirname, "node_modules/react"),
      "react-dom": resolve(__dirname, "node_modules/react-dom"),
      "react/jsx-runtime": resolve(__dirname, "node_modules/react/jsx-runtime"),
      "react/jsx-dev-runtime": resolve(
        __dirname,
        "node_modules/react/jsx-dev-runtime"
      ),
      "react-router": resolve(__dirname, "node_modules/react-router"),
      "react-router-dom": resolve(__dirname, "node_modules/react-router-dom"),
    },
  },
  // @ts-expect-error - Vitest configuration is supported via plugin but not typed in Vite's config schema yet.
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    globals: true,
    css: true,
    exclude: ["e2e/**", "node_modules/**"],
  },
})
