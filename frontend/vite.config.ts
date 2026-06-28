import { defineConfig, type PluginOption } from "vite"
import react from "@vitejs/plugin-react"
import svgr from "vite-plugin-svgr"
import { existsSync } from "node:fs"
import { resolve } from "node:path"

const manualChunkGroups = {
  react: ["react", "react-dom", "react-router-dom"],
  radix: [
    "@radix-ui/react-checkbox",
    "@radix-ui/react-collapsible",
    "@radix-ui/react-context-menu",
    "@radix-ui/react-dialog",
    "@radix-ui/react-dropdown-menu",
    "@radix-ui/react-hover-card",
    "@radix-ui/react-popover",
    "@radix-ui/react-select",
    "@radix-ui/react-slider",
    "@radix-ui/react-switch",
    "@radix-ui/react-tooltip",
  ],
  query: ["@tanstack/react-query"],
  markdown: ["react-markdown", "rehype-raw", "rehype-sanitize", "remark-gfm"],
  // CodeMirror packages have cross-package initialization dependencies and
  // break when split across separate chunks by Rollup's default heuristics.
  codemirror: ["@codemirror/", "@lezer/", "codemirror"],
} as const

const localUxWorkspace = resolve(__dirname, "../../ux")
const dockerUxWorkspace = "/ux"
const isVitest = process.env.VITEST === "true" || process.env.NODE_ENV === "test"
const uxWorkspace = !isVitest && existsSync(resolve(dockerUxWorkspace, "package.json"))
  ? dockerUxWorkspace
  : !isVitest && existsSync(resolve(localUxWorkspace, "package.json"))
    ? localUxWorkspace
    : null

const uxAliases = uxWorkspace
  ? [
      {
        find: "@tidemark-security/ux/tokens.css",
        replacement: resolve(uxWorkspace, "src/tokens/index.css"),
      },
      {
        find: "@tidemark-security/ux/ux.css",
        replacement: resolve(uxWorkspace, "dist/ux.css"),
      },
      {
        find: "@tidemark-security/ux",
        replacement: resolve(uxWorkspace, "src/index.ts"),
      },
    ]
  : []

function manualChunks(id: string): string | undefined {
  for (const [chunkName, packages] of Object.entries(manualChunkGroups)) {
    if (packages.some((pkg) => id.includes(`/node_modules/${pkg}/`) || id.includes(`\\node_modules\\${pkg}\\`))) {
      return chunkName
    }
  }

  // Catch-all: keep all remaining vendor code in one chunk to prevent Rollup
  // from creating multiple dist-*.js chunks with circular init dependencies.
  if (id.includes("/node_modules/") || id.includes("\\node_modules\\")) {
    return "vendor"
  }

  return undefined
}

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
    alias: [
      ...uxAliases,
      { find: "@", replacement: resolve(__dirname, "./src") },
      // Force UX file: linked package to use TMI's copies of React/router
      // to avoid dual-instance issues in tests
      { find: "react", replacement: resolve(__dirname, "node_modules/react") },
      { find: "react-dom", replacement: resolve(__dirname, "node_modules/react-dom") },
      { find: "react/jsx-runtime", replacement: resolve(__dirname, "node_modules/react/jsx-runtime") },
      {
        find: "react/jsx-dev-runtime",
        replacement: resolve(__dirname, "node_modules/react/jsx-dev-runtime"),
      },
      { find: "react-router", replacement: resolve(__dirname, "node_modules/react-router") },
      { find: "react-router-dom", replacement: resolve(__dirname, "node_modules/react-router-dom") },
    ],
  },
  optimizeDeps: {
    // UX is linked/mounted during local development. Excluding it prevents Vite
    // from keeping a stale pre-bundled copy when UX adds or removes exports.
    exclude: ["@tidemark-security/ux"],
  },
  server: {
    fs: {
      allow: [resolve(__dirname), localUxWorkspace, dockerUxWorkspace],
    },
    watch: {
      usePolling: process.env.VITE_USE_POLLING === "true",
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks,
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
