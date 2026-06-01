import type { Creator } from '@/api/types';

const PENDING_CONTACT_STATUSES = new Set(['prospect', 'pending_contact', '待建联', '待联系', '未建联', '潜在线索']);
const INACTIVE_STATUSES = new Set(['dropped', '已放弃', '放弃', '黑名单']);

export function normalizeCreatorStatus(status: string | null | undefined) {
  return String(status || '').trim();
}

export function isPendingContactCreator(status: string | null | undefined) {
  return PENDING_CONTACT_STATUSES.has(normalizeCreatorStatus(status));
}

export function isActiveCreator(status: string | null | undefined) {
  const normalized = normalizeCreatorStatus(status);
  return Boolean(normalized) && !INACTIVE_STATUSES.has(normalized) && !PENDING_CONTACT_STATUSES.has(normalized);
}

export function isRecentCreator(createdAt: string | null | undefined, days = 30) {
  if (!createdAt) return false;
  const createdTime = new Date(createdAt).getTime();
  if (!Number.isFinite(createdTime)) return false;
  return Date.now() - createdTime < days * 24 * 3600_000;
}

export function countHeadTierCreators(creators: Creator[]) {
  return creators.filter((creator) => {
    const tier = String(creator.tier || '').trim().toUpperCase();
    return tier === 'S' || tier === 'A';
  }).length;
}
