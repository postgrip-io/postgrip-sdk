import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

// The published names of each package entry, split into runtime values and
// type-only exports. A difference fails the test; after a deliberate surface
// change, regenerate with UPDATE_PUBLIC_SURFACE=1 and review the manifest diff.

const ROOT = new URL('../', import.meta.url).pathname;
const MANIFEST = join(ROOT, 'test', 'public-surface.json');
const ENTRIES: Record<string, string> = {
  '.': 'src/index.ts',
  './agent': 'src/agent/index.ts',
  './worker': 'src/worker/index.ts',
  './service': 'src/service/index.ts',
};

interface EntrySurface {
  values: string[];
  types: string[];
}

async function publicSurface(): Promise<Record<string, EntrySurface>> {
  const config = ts.parseJsonConfigFileContent(
    ts.readConfigFile(join(ROOT, 'tsconfig.json'), ts.sys.readFile).config,
    ts.sys,
    ROOT,
  );
  const files = Object.values(ENTRIES).map((file) => join(ROOT, file));
  const program = ts.createProgram(files, config.options);
  const checker = program.getTypeChecker();
  const surface: Record<string, EntrySurface> = {};
  for (const [subpath, file] of Object.entries(ENTRIES)) {
    const source = program.getSourceFile(join(ROOT, file));
    const moduleSymbol = source && checker.getSymbolAtLocation(source);
    if (!moduleSymbol) throw new Error(`cannot resolve ${file}`);
    const runtime: Record<string, unknown> = await import(join(ROOT, file));
    const names = checker.getExportsOfModule(moduleSymbol).map((symbol) => symbol.name).sort();
    surface[subpath] = {
      values: names.filter((name) => name in runtime),
      types: names.filter((name) => !(name in runtime)),
    };
  }
  return surface;
}

describe('public surface', () => {
  it('matches the recorded manifest for every package entry', async () => {
    const actual = await publicSurface();
    if (process.env.UPDATE_PUBLIC_SURFACE === '1') {
      writeFileSync(MANIFEST, `${JSON.stringify(actual, null, 2)}\n`);
    }
    const recorded = JSON.parse(readFileSync(MANIFEST, 'utf8')) as Record<string, EntrySurface>;
    expect(Object.keys(actual)).toEqual(Object.keys(recorded));
    for (const subpath of Object.keys(recorded)) {
      for (const kind of ['values', 'types'] as const) {
        const added = actual[subpath][kind].filter((name) => !recorded[subpath][kind].includes(name));
        const removed = recorded[subpath][kind].filter((name) => !actual[subpath][kind].includes(name));
        expect({ subpath, kind, added, removed }).toEqual({ subpath, kind, added: [], removed: [] });
      }
    }
  }, 60_000);
});
