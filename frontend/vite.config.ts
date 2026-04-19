import { defineConfig, type PluginOption } from "vite"
import react from "@vitejs/plugin-react"
import svgr from "vite-plugin-svgr"
import { visualizer } from "rollup-plugin-visualizer"
import { resolve } from "node:path"

async function analyzePlugin(): Promise<PluginOption[]> {
  if (!process.env.ANALYZE) return [];
  const { visualizer } = await import("rollup-plugin-visualizer");
  return [
    visualizer({
      filename: "dist/stats.html",
      template: "treemap",
      gzipSize: true,
      brotliSize: true,
    }),
  ];
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    svgr(),
    analyzePlugin(),
  ],
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
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          radix: [
            '@radix-ui/react-checkbox',
            '@radix-ui/react-collapsible',
            '@radix-ui/react-context-menu',
            '@radix-ui/react-dialog',
            '@radix-ui/react-dropdown-menu',
            '@radix-ui/react-hover-card',
            '@radix-ui/react-popover',
            '@radix-ui/react-select',
            '@radix-ui/react-slider',
            '@radix-ui/react-switch',
            '@radix-ui/react-tooltip',
          ],
          query: ['@tanstack/react-query'],
          markdown: ['react-markdown', 'rehype-raw', 'rehype-sanitize', 'remark-gfm'],
        },
      },
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
