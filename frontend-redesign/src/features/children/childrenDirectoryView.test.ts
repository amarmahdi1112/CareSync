import { describe, expect, it } from 'vitest';
import { childrenDirectoryWindow } from './childrenDirectoryView';
import type { ChildDirectoryPage } from './childrenApi';

const counts = {
  total: 0, active: 0, inactive: 0, daycare: 0, out_of_school_care: 0,
  unassigned: 0, reserved: 0, needs_review: 0,
};

describe('children directory presentation states', () => {
  it('distinguishes a genuinely empty roster from an empty filtered result', () => {
    const page: ChildDirectoryPage = { items: [], total: 0, limit: 50, offset: 0, counts };
    expect(childrenDirectoryWindow(page, false).emptyState).toBe('first-record');
    expect(childrenDirectoryWindow(page, true).emptyState).toBe('filtered-empty');
  });

  it('derives exact bounded pagination controls', () => {
    const page = { items: Array.from({ length: 50 }, () => ({})), total: 120, limit: 50, offset: 50, counts } as unknown as ChildDirectoryPage;
    expect(childrenDirectoryWindow(page, false)).toMatchObject({
      start: 51, end: 100, pageNumber: 2, pageCount: 3,
      canGoBack: true, canGoForward: true, emptyState: 'none',
    });
  });

  it('labels the final short page without overstating its range', () => {
    const page = { items: Array.from({ length: 20 }, () => ({})), total: 120, limit: 50, offset: 100, counts } as unknown as ChildDirectoryPage;
    expect(childrenDirectoryWindow(page, false)).toMatchObject({ start: 101, end: 120, pageNumber: 3, pageCount: 3, canGoForward: false });
  });
});
