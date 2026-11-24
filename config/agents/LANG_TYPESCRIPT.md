# TypeScript conventions

- `strict: true`. No implicit `any`; prefer `unknown` + narrowing over casts.
- Match the repo's package manager (pnpm/npm/yarn/bun) — check the lockfile first.
- Lint+format with the repo's eslint/prettier/biome config; don't impose a new one.
- Prefer explicit return types on exported functions; discriminated unions over enums.
- Async: no floating promises; handle rejections. Validate external input (zod or equiv).
- Run typecheck + tests (`tsc --noEmit`, vitest/jest) before claiming done.
