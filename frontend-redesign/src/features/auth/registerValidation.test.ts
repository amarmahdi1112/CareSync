import { describe, expect, it } from 'vitest';
import { validateRegisterDraft, type RegisterDraft } from './registerValidation';

const valid: RegisterDraft = {
  firstName: 'Avery', lastName: 'Morgan', organizationName: 'North Star Childcare', email: 'avery@example.ca',
  password: 'care-sync123', confirmPassword: 'care-sync123', acceptedTerms: true,
};

describe('validateRegisterDraft', () => {
  it('accepts a complete registration', () => expect(validateRegisterDraft(valid)).toEqual({}));

  it('reports identity, password, confirmation, and consent errors together', () => {
    const errors = validateRegisterDraft({
      firstName: '', lastName: '', organizationName: '', email: 'invalid', password: 'short',
      confirmPassword: 'different', acceptedTerms: false,
    });
    expect(errors).toMatchObject({
      firstName: expect.any(String), lastName: expect.any(String), email: expect.any(String),
      password: expect.any(String), confirmPassword: expect.any(String), acceptedTerms: expect.any(String),
    });
  });
});
