import { readFile } from 'node:fs/promises';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

const AGENT = new URL('../../src/agent/', import.meta.url);

async function source(module: string): Promise<string> {
  return readFile(new URL(module, AGENT), 'utf8');
}

/** Every relative module a source imports: static, side-effect, re-export and dynamic forms. */
function relativeImports(text: string): string[] {
  const { importedFiles } = ts.preProcessFile(text, true, true);
  return importedFiles.map((file) => file.fileName).filter((name) => name.startsWith('.')).sort();
}

describe('Agent client module ownership', () => {
  it('detects every import form the boundary checks rely on', () => {
    const forms = [
      "import { a } from './static.js';",
      'import { b } from "./double.js";',
      "import './side-effect.js';",
      'import "./side-effect-double.js";',
      "export { c } from './re-export.js';",
      "export * from './star.js';",
      "import type { D } from './type-only.js';",
      "const lazy = await import('./dynamic.js');",
      'const lazier = import("./dynamic-double.js");',
    ].join('\n');
    expect(relativeImports(forms)).toEqual([
      './double.js',
      './dynamic-double.js',
      './dynamic.js',
      './re-export.js',
      './side-effect-double.js',
      './side-effect.js',
      './star.js',
      './static.js',
      './type-only.js',
    ]);
  });

  it('keeps every previously exported runtime name importable from client.js and connection.js', async () => {
    expect(Object.keys(await import('../../src/agent/client.js')).sort()).toEqual([
      'Client',
      'ScheduleClient',
      'TaskClient',
      'WorkflowClient',
      'WorkflowHandle',
      'WorkflowUpdateHandle',
    ]);
    expect(Object.keys(await import('../../src/agent/connection.js')).sort()).toEqual(['Connection', 'DEFAULT_BASE_URL']);
  });

  it('keeps workflow models and history paging free of transport and orchestration', async () => {
    expect(relativeImports(await source('_workflow_models.ts'))).toEqual(['./types.js']);
    expect(relativeImports(await source('_history.ts'))).toEqual([]);
  });

  it('gives the archive upload adapter no dependency on the connection or clients', async () => {
    expect(relativeImports(await source('_archive_upload.ts'))).toEqual(['./generated/openapi.js']);
  });

  it('leaves memo, description and paging logic out of client.ts and connection.ts', async () => {
    const client = await source('client.ts');
    const connection = await source('connection.ts');
    expect(client).not.toContain("'postgrip.ui'");
    expect(client).not.toMatch(/function describeWorkflow/);
    expect(connection).not.toMatch(/function\* iterateHistoryPages|function historyPageQuery/);
    expect(connection).not.toContain("'application/gzip'");
  });
});
