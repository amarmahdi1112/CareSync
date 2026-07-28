import JSZip from 'jszip';
import { assertIsoDate, assertTime24, minutesSinceMidnight } from './format';
import type { AttendanceDataset, AttendanceRecord, AttendanceSession, SourceChild } from './types';

const REQUIRED_HEADERS = [
  'attendance_date', 'child_id', 'child_name',
  'session_1_start', 'session_1_end', 'session_2_start', 'session_2_end',
] as const;

export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let quoted = false;
  const input = text.replace(/^\uFEFF/, '');
  for (let index = 0; index < input.length; index += 1) {
    const character = input[index];
    if (quoted) {
      if (character === '"' && input[index + 1] === '"') {
        field += '"';
        index += 1;
      } else if (character === '"') {
        quoted = false;
      } else {
        field += character;
      }
    } else if (character === '"') {
      quoted = true;
    } else if (character === ',') {
      row.push(field);
      field = '';
    } else if (character === '\n') {
      row.push(field.replace(/\r$/, ''));
      if (row.some((value) => value !== '')) rows.push(row);
      row = [];
      field = '';
    } else {
      field += character;
    }
  }
  if (quoted) throw new Error('Malformed CSV: unclosed quoted field');
  row.push(field.replace(/\r$/, ''));
  if (row.some((value) => value !== '')) rows.push(row);
  return rows;
}

function session(start: string, end: string, label: string): AttendanceSession | null {
  if (!start && !end) return null;
  if (!start || !end) throw new Error(`${label} must include both an IN and OUT time`);
  assertTime24(start);
  assertTime24(end);
  if (minutesSinceMidnight(end) <= minutesSinceMidnight(start)) {
    throw new Error(`${label} OUT time must be after its IN time`);
  }
  return { start, end };
}

export async function parseCareSyncZip(buffer: ArrayBuffer, fileName = 'CareSync_daily_attendance.zip'): Promise<AttendanceDataset> {
  const zip = await JSZip.loadAsync(buffer);
  const files = Object.values(zip.files)
    .filter((file) => !file.dir && /^daily_attendance\/\d{4}-\d{2}-\d{2}\.csv$/i.test(file.name))
    .sort((left, right) => left.name.localeCompare(right.name));
  if (files.length === 0) throw new Error('No daily_attendance/YYYY-MM-DD.csv files were found in this ZIP');

  const records: AttendanceRecord[] = [];
  const children = new Map<string, SourceChild>();
  const recordKeys = new Set<string>();
  for (const file of files) {
    const rows = parseCsv(await file.async('string'));
    if (rows.length < 2) continue;
    const header = rows[0].map((value) => value.trim());
    for (const required of REQUIRED_HEADERS) {
      if (!header.includes(required)) throw new Error(`${file.name} is missing required column ${required}`);
    }
    const column = (name: string) => header.indexOf(name);
    for (const values of rows.slice(1)) {
      const value = (name: string) => (values[column(name)] || '').trim();
      const date = assertIsoDate(value('attendance_date'));
      const expectedDate = file.name.match(/(\d{4}-\d{2}-\d{2})\.csv$/i)?.[1];
      if (expectedDate !== date) throw new Error(`${file.name} contains a row for ${date}`);
      const sourceChildId = value('child_id');
      const sourceChildName = value('child_name');
      if (!sourceChildId || !sourceChildName) throw new Error(`${file.name} contains a row without child_id or child_name`);
      const key = `${date}\u0000${sourceChildId}`;
      if (recordKeys.has(key)) throw new Error(`${date} contains duplicate rows for ${sourceChildName}`);
      recordKeys.add(key);
      const firstSessionStart = value('session_1_start');
      const firstSessionEnd = value('session_1_end');
      const secondSessionStart = value('session_2_start');
      const secondSessionEnd = value('session_2_end');
      if (!firstSessionStart && !firstSessionEnd && (secondSessionStart || secondSessionEnd)) {
        throw new Error(`${date} ${sourceChildName} has session 2 without session 1`);
      }
      const sessions = [
        session(firstSessionStart, firstSessionEnd, `${date} ${sourceChildName} session 1`),
        session(secondSessionStart, secondSessionEnd, `${date} ${sourceChildName} session 2`),
      ].filter((entry): entry is AttendanceSession => entry !== null);
      if (sessions.length === 0) throw new Error(`${date} ${sourceChildName} has no complete attendance session`);
      if (sessions.length === 2 && minutesSinceMidnight(sessions[1].start) < minutesSinceMidnight(sessions[0].end)) {
        throw new Error(`${date} ${sourceChildName} has overlapping attendance sessions`);
      }
      const previous = children.get(sourceChildId);
      if (previous && previous.name !== sourceChildName) {
        throw new Error(`Child ${sourceChildId} has conflicting names: ${previous.name} and ${sourceChildName}`);
      }
      children.set(sourceChildId, { id: sourceChildId, name: sourceChildName });
      records.push({
        date,
        sourceChildId,
        sourceChildName,
        sessions,
        scheduleEntryId: header.includes('schedule_entry_id') ? value('schedule_entry_id') : undefined,
      });
    }
  }
  if (records.length === 0) throw new Error('The CareSync ZIP has no attendance records');
  records.sort((left, right) => left.date.localeCompare(right.date) || left.sourceChildName.localeCompare(right.sourceChildName));
  const datasetChildren = [...children.values()].sort((left, right) => left.name.localeCompare(right.name));
  const dates = [...new Set(records.map((record) => record.date))].sort();
  return {
    id: globalThis.crypto?.randomUUID?.() || `dataset-${Date.now()}`,
    fileName,
    importedAt: new Date().toISOString(),
    dates,
    children: datasetChildren,
    records,
  };
}
