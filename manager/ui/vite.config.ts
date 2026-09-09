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

export default defineConfig({
  plugins: [react(), spdxLicenseHeaders()],
  build: {
    outDir: path.resolve(__dirname, "../src/manager/static/ui"),
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: {
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
