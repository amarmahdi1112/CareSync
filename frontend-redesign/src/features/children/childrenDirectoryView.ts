import type { ChildDirectoryPage } from './childrenApi';

export type ChildrenDirectoryEmptyState = 'none' | 'first-record' | 'filtered-empty';

export interface ChildrenDirectoryWindow {
  start: number;
  end: number;
  pageNumber: number;
  pageCount: number;
  canGoBack: boolean;
  canGoForward: boolean;
  emptyState: ChildrenDirectoryEmptyState;
}

export function childrenDirectoryWindow(
  page: ChildDirectoryPage | null,
  hasFilters: boolean,
): ChildrenDirectoryWindow {
  if (!page) {
    return {
      start: 0, end: 0, pageNumber: 0, pageCount: 0,
      canGoBack: false, canGoForward: false, emptyState: 'none',
    };
  }
  const emptyState = page.items.length > 0
    ? 'none'
    : hasFilters
      ? 'filtered-empty'
      : 'first-record';
  return {
    start: page.total ? page.offset + 1 : 0,
    end: Math.min(page.offset + page.items.length, page.total),
    pageNumber: page.total ? Math.floor(page.offset / page.limit) + 1 : 0,
    pageCount: page.total ? Math.ceil(page.total / page.limit) : 0,
    canGoBack: page.offset > 0,
    canGoForward: page.offset + page.limit < page.total,
    emptyState,
  };
}
