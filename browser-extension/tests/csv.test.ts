import JSZip from 'jszip';
import { describe, expect, it } from 'vitest';

import { parseCareSyncZip, parseCsv } from '../src/shared/csv';

const HEADER = [
  'attendance_date',
  'child_id',
  'child_name',
  'session_1_start',
  'session_1_end',
  'session_2_start',
  'session_2_end',
  'schedule_entry_id',
].join(',');

function row(values: string[]): string {
  return values
    .map((value) => (/[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value))
    .join(',');
}

async function dailyZip(files: Record<string, string>): Promise<ArrayBuffer> {
  const zip = new JSZip();
  for (const [name, contents] of Object.entries(files)) zip.file(name, contents);
  return zip.generateAsync({ type: 'arraybuffer' });
}

function csv(...rows: string[][]): string {
  return `${HEADER}\r\n${rows.map(row).join('\r\n')}\r\n`;
}

describe('parseCsv', () => {
  it('handles a BOM, CRLF, commas, embedded newlines, and escaped quotes', () => {
    expect(parseCsv('\uFEFFname,note\r\n"Doe, Jo","line 1\nline ""two"""\r\n')).toEqual([
      ['name', 'note'],
      ['Doe, Jo', 'line 1\nline "two"'],
    ]);
  });

  it('rejects an unclosed quoted field', () => {
    expect(() => parseCsv('name,note\nJo,"unfinished')).toThrow(/unclosed quoted field/i);
  });
});

describe('parseCareSyncZip', () => {
  it('parses and sorts single- and two-session records from daily CSV files', async () => {
    const buffer = await dailyZip({
      'daily_attendance/2026-01-06.csv': csv(
        ['2026-01-06', 'child-2', 'Zoë Smith', '08:15', '16:30', '', '', 'entry-2'],
      ),
      'daily_attendance/2026-01-05.csv': csv(
        ['2026-01-05', 'child-1', 'Amar, Junior', '07:30', '11:45', '12:30', '17:05', 'entry-1'],
      ),
      'manifest.csv': 'ignored,by,the,attendance,parser\n',
    });

    const dataset = await parseCareSyncZip(buffer, 'infants.zip');

    expect(dataset.fileName).toBe('infants.zip');
    expect(dataset.dates).toEqual(['2026-01-05', '2026-01-06']);
    expect(dataset.children).toEqual([
      { id: 'child-1', name: 'Amar, Junior' },
      { id: 'child-2', name: 'Zoë Smith' },
    ]);
    expect(dataset.records).toMatchObject([
      {
        date: '2026-01-05',
        sourceChildId: 'child-1',
        sourceChildName: 'Amar, Junior',
        scheduleEntryId: 'entry-1',
        sessions: [
          { start: '07:30', end: '11:45' },
          { start: '12:30', end: '17:05' },
        ],
      },
      {
        date: '2026-01-06',
        sourceChildId: 'child-2',
        sessions: [{ start: '08:15', end: '16:30' }],
      },
    ]);
  });

  it('rejects duplicate records for the same child and date', async () => {
    const buffer = await dailyZip({
      'daily_attendance/2026-01-05.csv': csv(
        ['2026-01-05', 'child-1', 'Jitu Regassa', '08:00', '16:00', '', '', 'entry-1'],
        ['2026-01-05', 'child-1', 'Jitu Regassa', '08:30', '16:30', '', '', 'entry-2'],
      ),
    });

    await expect(parseCareSyncZip(buffer)).rejects.toThrow(/duplicate rows/i);
  });

  it.each([
    {
      label: 'a partial first session',
      values: ['2026-01-05', 'child-1', 'Jitu Regassa', '08:00', '', '', '', 'entry-1'],
      error: /both an IN and OUT/i,
    },
    {
      label: 'OUT before IN',
      values: ['2026-01-05', 'child-1', 'Jitu Regassa', '16:00', '08:00', '', '', 'entry-1'],
      error: /OUT time must be after/i,
    },
    {
      label: 'overlapping sessions',
      values: ['2026-01-05', 'child-1', 'Jitu Regassa', '08:00', '12:00', '11:30', '16:00', 'entry-1'],
      error: /overlapping attendance sessions/i,
    },
  ])('rejects $label', async ({ values, error }) => {
    const buffer = await dailyZip({ 'daily_attendance/2026-01-05.csv': csv(values) });
    await expect(parseCareSyncZip(buffer)).rejects.toThrow(error);
  });

  it('rejects a second session when the first session is empty', async () => {
    const buffer = await dailyZip({
      'daily_attendance/2026-01-05.csv': csv(
        ['2026-01-05', 'child-1', 'Jitu Regassa', '', '', '12:30', '16:00', 'entry-1'],
      ),
    });

    await expect(parseCareSyncZip(buffer)).rejects.toThrow(/session 2.*session 1|second session.*first/i);
  });

  it('rejects rows whose date does not agree with the daily filename', async () => {
    const buffer = await dailyZip({
      'daily_attendance/2026-01-05.csv': csv(
        ['2026-01-06', 'child-1', 'Jitu Regassa', '08:00', '16:00', '', '', 'entry-1'],
      ),
    });

    await expect(parseCareSyncZip(buffer)).rejects.toThrow(/contains a row for 2026-01-06/i);
  });

  it('rejects ZIP files without a daily attendance CSV', async () => {
    const buffer = await dailyZip({ 'README.txt': 'Not an attendance archive' });
    await expect(parseCareSyncZip(buffer)).rejects.toThrow(/no daily_attendance/i);
  });
});
