import type { OfferVersion } from './hiringApi';
export type OfferDisplayStatus = OfferVersion['status'] | 'expired';
export function offerDisplayStatus(offer: OfferVersion, now = Date.now()): OfferDisplayStatus { return offer.status === 'sent' && offer.expires_at != null && new Date(offer.expires_at).getTime() <= now ? 'expired' : offer.status; }
