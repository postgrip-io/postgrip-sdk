import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const ROOT = new URL('../', import.meta.url).pathname;

function localDependencies(entry: string): Set<string> {
  const seen = new Set<string>();
  const visit = (file: string) => {
    if (seen.has(file)) return;
    seen.add(file);
    const source = readFileSync(file, 'utf8');
    for (const match of source.matchAll(/(?:from|import)\s*\(?\s*['"](\.[^'"]*)['"]/g)) {
      const candidate = join(dirname(file), match[1].replace(/\.js$/, '.ts'));
      if (existsSync(candidate)) visit(candidate);
    }
  };
  visit(entry);
  return seen;
}

describe('package boundaries', () => {
  it.each(['worker', 'service'])('%s does not load the Agent plane', (plane) => {
    const files = [...localDependencies(join(ROOT, 'src', plane, 'index.ts'))]
      .map((file) => relative(join(ROOT, 'src'), file));
    expect(files.some((file) => file.startsWith('agent/'))).toBe(false);
    expect(files.some((file) => readFileSync(join(ROOT, 'src', file), 'utf8').includes("from 'ws'"))).toBe(false);
  });

  it('declares every public subpath with runtime and type entries', () => {
    const manifest = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8')) as {
      exports: Record<string, { types: string; default: string }>;
    };
    expect(Object.keys(manifest.exports)).toEqual(['.', './agent', './worker', './service']);
    for (const exported of Object.values(manifest.exports)) {
      expect(exported.types.endsWith('.d.ts')).toBe(true);
      expect(exported.default.endsWith('.js')).toBe(true);
    }
  });
});
