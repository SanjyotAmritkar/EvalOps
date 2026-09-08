import next from "eslint-config-next";

/**
 * `eslint-config-next` (v16) is already a flat-config array bundling the
 * Next.js, React, React Hooks, import, and jsx-a11y rules plus the TypeScript
 * parser. We only add project-local ignores on top.
 */
const eslintConfig = [
  ...next,
  {
    ignores: ["coverage/**", "next-env.d.ts"],
  },
];

export default eslintConfig;
