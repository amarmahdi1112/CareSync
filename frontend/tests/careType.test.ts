import assert from 'node:assert/strict';
import test from 'node:test';

import { schedulerCareType } from '../src/pages/scheduling/utils/careType.ts';

test('Preschool is full-day daycare, not out-of-school care', () => {
  assert.equal(schedulerCareType('Preschool'), 'Daycare');
  assert.equal(schedulerCareType('preschool'), 'Daycare');
});

test('known OSC labels map to the split school-day window', () => {
  assert.equal(schedulerCareType('SchoolAge'), 'OSC');
  assert.equal(schedulerCareType('School-Age'), 'OSC');
  assert.equal(schedulerCareType('Out-of-school care'), 'OSC');
});

test('the monthly claim category takes precedence over the current age group', () => {
  assert.equal(schedulerCareType('Preschool', 'School-Age'), 'Daycare');
  assert.equal(schedulerCareType('', 'School-Age'), 'OSC');
});

