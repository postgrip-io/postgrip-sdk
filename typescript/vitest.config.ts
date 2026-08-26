import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    include: ['test/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['src/generated/**', 'src/types.ts', 'src/worker.ts'],
      reporter: ['text', 'json-summary'],
      thresholds: {
        statements: 35,
        branches: 30,
        functions: 35,
        lines: 36,
      },
    },
  },
});
