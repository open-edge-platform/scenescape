// SPDX-FileCopyrightText: (C) 2025 Intel Corporation
// SPDX-License-Identifier: LicenseRef-Intel-Edge-Software
// This file is licensed under the Limited Edge Software Distribution License Agreement.

import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";

export default defineConfig([
  {
    files: ["**/*.js"],
    plugins: {
      js,
    },
    extends: ["js/recommended"],
    rules: {
      "no-unused-vars": "warn",
    },
  },
  globalIgnores([
    "**/node_modules/",
  ])
]);
