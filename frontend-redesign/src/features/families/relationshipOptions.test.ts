import { describe, expect, it } from 'vitest';
import {
  RELATIONSHIP_CHOICES,
  customRelationshipValue,
  relationshipSelection,
} from './relationshipOptions';

describe('family relationship choices', () => {
  it('provides the complete ordered set of preloaded choices', () => {
    expect(RELATIONSHIP_CHOICES).toEqual([
      'Mother', 'Father', 'Parent', 'Step-parent', 'Legal Guardian', 'Foster Parent',
      'Grandmother', 'Grandfather', 'Grandparent', 'Sibling', 'Aunt', 'Uncle',
      'Cousin', 'Family Friend', 'Social Worker', 'Other',
    ]);
  });

  it('round-trips known and custom stored values through the select model', () => {
    expect(relationshipSelection('Mother')).toBe('Mother');
    expect(customRelationshipValue('Mother')).toBe('');
    expect(relationshipSelection('Kinship Caregiver')).toBe('Other');
    expect(customRelationshipValue('Kinship Caregiver')).toBe('Kinship Caregiver');
    expect(relationshipSelection('')).toBe('');
  });
});
