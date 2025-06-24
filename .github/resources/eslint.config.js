// eslint.config.js
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
