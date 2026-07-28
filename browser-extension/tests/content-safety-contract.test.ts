import { describe, expect, it } from 'vitest';

// Vite supplies the source text for this test-only raw import.
// @ts-expect-error The production TypeScript config intentionally omits Vite client globals.
import source from '../src/content.ts?raw';

describe('content engine destructive-operation contract', () => {
  it('consolidates mapped date-child records before the portal action loop', () => {
    const preparation = source.indexOf('const consolidated = consolidateMappedRecords');
    const actionLoop = source.indexOf('while (true)', preparation);

    expect(preparation).toBeGreaterThan(-1);
    expect(actionLoop).toBeGreaterThan(preparation);
    expect(source.slice(preparation, actionLoop)).toContain('const days = consolidated.days');
  });

  it('never calls a destructive helper from entry processing or a later failure handler', () => {
    const entryStart = source.indexOf('const record = day.records[recordIndex]');

    expect(entryStart).toBeGreaterThan(-1);

    const entrySource = source.slice(entryStart);
    expect(entrySource).not.toContain('deleteAllExisting(');
    expect(entrySource).not.toContain('deleteExisting(');
    expect(entrySource).toContain('existing portal data was preserved');
  });
});
