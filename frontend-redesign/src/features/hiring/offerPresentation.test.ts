import { describe, expect, it } from 'vitest';
import { offerDisplayStatus } from './offerPresentation';
import type { OfferVersion } from './hiringApi';
const offer = { status: 'sent', expires_at: '2026-07-20T00:00:00Z' } as OfferVersion;
describe('offer presentation', () => { it('projects an elapsed sent offer as expired without changing canonical status', () => { expect(offerDisplayStatus(offer, Date.parse('2026-07-21T00:00:00Z'))).toBe('expired'); expect(offerDisplayStatus(offer, Date.parse('2026-07-19T00:00:00Z'))).toBe('sent'); }); });
