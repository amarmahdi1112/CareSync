import { beforeEach, describe, expect, it, vi } from 'vitest';
import { dailyClosePreviewFixture } from './dailyCloseTestData';

const { apiRequestMock } = vi.hoisted(() => ({ apiRequestMock: vi.fn() }));
vi.mock('../../api/client', () => ({ apiRequest: apiRequestMock }));

import {
  DailyCloseApiError,
  fetchRoomDailyClosePreview,
  parseRoomDailyClosePreview,
} from './dailyCloseApi';

const copy = () => structuredClone(dailyClosePreviewFixture);

describe('daily close fail-closed response adapter', () => {
  beforeEach(() => apiRequestMock.mockReset());

  it('parses the exact factual projection and verifies the requested boundary', async () => {
    apiRequestMock.mockResolvedValueOnce(copy());
    const result = await fetchRoomDailyClosePreview(
      'room-1',
      '2026-07-15',
      'org-1',
      'facility-1',
    );

    expect(result.children[0].attention_flags).toHaveLength(5);
    expect(result.totals.care_counts.activity).toBe(3);
    expect(apiRequestMock).toHaveBeenCalledWith(
      '/care/rooms/room-1/daily-close-preview?date=2026-07-15',
      { signal: undefined },
    );
  });

  it.each([
    ['organization_id', 'org-elsewhere'],
    ['facility_id', 'facility-elsewhere'],
    ['room_id', 'room-elsewhere'],
    ['service_date', '2026-07-14'],
  ] as const)('rejects a response that crosses the requested %s boundary', async (key, value) => {
    apiRequestMock.mockResolvedValueOnce({ ...copy(), [key]: value });
    await expect(fetchRoomDailyClosePreview('room-1', '2026-07-15', 'org-1', 'facility-1'))
      .rejects.toThrow(/crossed the selected organization, facility, room, or date boundary/i);
  });

  it('rejects undeclared top-level, nested, and photo fields', () => {
    expect(() => parseRoomDailyClosePreview({ ...copy(), certification_status: 'complete' })).toThrow(DailyCloseApiError);
    expect(() => parseRoomDailyClosePreview({
      ...copy(),
      children: [{ ...copy().children[0], guardian_note: 'private' }],
    })).toThrow(DailyCloseApiError);
    expect(() => parseRoomDailyClosePreview({
      ...copy(),
      children: [{ ...copy().children[0], profile_photo_url: 'https://example.com/noor.jpg' }],
    })).toThrow(/photo/i);
    const missingNullable = copy().children[0] as Record<string, unknown>;
    delete missingNullable.last_checkout_at;
    expect(() => parseRoomDailyClosePreview({ ...copy(), children: [missingNullable] })).toThrow(DailyCloseApiError);
  });

  it('rejects attention flags and room totals that disagree with child facts', () => {
    expect(() => parseRoomDailyClosePreview({
      ...copy(),
      children: [{ ...copy().children[0], attention_flags: ['open_sleep'] }],
    })).toThrow(/attention flags/i);
    expect(() => parseRoomDailyClosePreview({
      ...copy(),
      totals: { ...copy().totals, accumulated_minutes: 121 },
    })).toThrow(/room totals/i);
  });

  it('rejects inconsistent attendance, recency, and duplicate identity evidence', () => {
    expect(() => parseRoomDailyClosePreview({
      ...copy(),
      children: [{ ...copy().children[0], currently_on_site: false }],
    })).toThrow(/on-site evidence/i);
    expect(() => parseRoomDailyClosePreview({
      ...copy(),
      children: [{ ...copy().children[0], most_recent_medication_at: null }],
    })).toThrow(/most-recent fact evidence/i);
    expect(() => parseRoomDailyClosePreview({
      ...copy(),
      children: [copy().children[0], copy().children[0]],
    })).toThrow(/more than once/i);
  });
});
