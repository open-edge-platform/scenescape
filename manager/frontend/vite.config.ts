// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";

const SPDX_JS = `// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
`;

const SPDX_CSS = `/*
 * SPDX-FileCopyrightText: (C) 2026 Intel Corporation
 * SPDX-License-Identifier: Apache-2.0
 */
`;

/**
 * Prepend SPDX headers after minify. Rollup `banner` is stripped by esbuild
 * minify, so rewrite built .js / .css on disk in writeBundle.
 */
function spdxLicenseHeaders(): Plugin {
  return {
    name: "spdx-license-headers",
    apply: "build",
    writeBundle(outputOptions, bundle) {
      const outDir = outputOptions.dir;
      if (!outDir) {
        return;
      }
      for (const fileName of Object.keys(bundle)) {
        let header: string | null = null;
        if (fileName.endsWith(".js")) {
          header = SPDX_JS;
        } else if (fileName.endsWith(".css")) {
          header = SPDX_CSS;
        }
        if (!header) {
          continue;
        }
        const fullPath = path.join(outDir, fileName);
        const body = fs.readFileSync(fullPath, "utf8");
        if (body.includes("SPDX-License-Identifier")) {
          continue;
        }
        fs.writeFileSync(fullPath, header + body);
      }
    },
  };
}

/** Copy public/*.html shells into the Django static ui output. */
function copyStaticShell(): Plugin {
  return {
    name: "copy-static-shell",
    apply: "build",
    closeBundle() {
      const destDir = path.resolve(__dirname, "../backend/manager/static/ui");
      fs.mkdirSync(destDir, { recursive: true });
      for (const name of ["shell.html", "sign-in.html"]) {
        const src = path.resolve(__dirname, "public", name);
        if (fs.existsSync(src)) {
          fs.copyFileSync(src, path.join(destDir, name));
        }
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), spdxLicenseHeaders(), copyStaticShell()],
  build: {
    outDir: path.resolve(__dirname, "../backend/manager/static/ui"),
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: {
        chrome: path.resolve(__dirname, "src/chrome-main.tsx"),
        spa: path.resolve(__dirname, "src/spa-main.tsx"),
        "sign-in": path.resolve(__dirname, "src/sign-in-main.tsx"),
        "scene-detail": path.resolve(__dirname, "src/main.tsx"),
        "admin-list": path.resolve(__dirname, "src/admin-list-main.tsx"),
        "destructive-actions": path.resolve(
          __dirname,
          "src/destructive-actions-main.tsx",
        ),
        "scenes-home": path.resolve(__dirname, "src/scenes-home-main.tsx"),
        "list-sheets": path.resolve(__dirname, "src/list-sheets-main.tsx"),
        "models-directory": path.resolve(
          __dirname,
          "src/models-directory-main.tsx",
        ),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        manualChunks(id) {
          if (id.includes("node_modules/three")) {
            return "three";
          }
          return undefined;
        },
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".css")) {
            return "manager-ui.css";
          }
          return "assets/[name]-[hash][extname]";
        },
      },
    },
  },
});
