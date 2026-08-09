// SPDX-FileCopyrightText: (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, "../src/manager/static/ui"),
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      input: {
        "scene-detail": path.resolve(__dirname, "src/main.tsx"),
        "admin-form": path.resolve(__dirname, "src/admin-form-main.tsx"),
        "admin-list": path.resolve(__dirname, "src/admin-list-main.tsx"),
        "destructive-actions": path.resolve(
          __dirname,
          "src/destructive-actions-main.tsx",
        ),
        "scenes-home": path.resolve(__dirname, "src/scenes-home-main.tsx"),
        "list-sheets": path.resolve(__dirname, "src/list-sheets-main.tsx"),
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
