const js = require("@eslint/js");
const globals = require("globals");

module.exports = [
  { ignores: ["dist/**", "node_modules/**"] },
  js.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "commonjs",
      globals: {
        ...globals.browser,
        ...globals.node,
        chrome: "readonly"
      }
    },
    rules: {
      "no-unused-vars": ["error", { "argsIgnorePattern": "^_" }]
    }
  }
];
