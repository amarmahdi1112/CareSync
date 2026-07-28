export const RELATIONSHIP_CHOICES = [
  'Mother',
  'Father',
  'Parent',
  'Step-parent',
  'Legal Guardian',
  'Foster Parent',
  'Grandmother',
  'Grandfather',
  'Grandparent',
  'Sibling',
  'Aunt',
  'Uncle',
  'Cousin',
  'Family Friend',
  'Social Worker',
  'Other',
] as const;

export type RelationshipChoice = (typeof RELATIONSHIP_CHOICES)[number];
export type RelationshipSelection = RelationshipChoice | '';

const PRELOADED_RELATIONSHIPS = new Set<string>(RELATIONSHIP_CHOICES.filter((choice) => choice !== 'Other'));

/** Maps stored free text to the select without changing the stored value. */
export function relationshipSelection(value: string): RelationshipSelection {
  const cleaned = value.trim();
  if (!cleaned) return '';
  return PRELOADED_RELATIONSHIPS.has(cleaned) ? cleaned as RelationshipChoice : 'Other';
}

export function customRelationshipValue(value: string): string {
  return relationshipSelection(value) === 'Other' ? value : '';
}
