import { describe, expect, it } from 'vitest';
import contract from '../../../contracts/realtime_entity_contract.json';
import {
  downstreamConsumersFor,
  featureIntegrationManifest,
} from './featureIntegrationManifest';

describe('backend to frontend realtime entity contract', () => {
  it('has a canonical consumer for every organization outbox entity', () => {
    for (const entity of contract.organization_outbox_entity_types) {
      expect(
        downstreamConsumersFor(entity),
        `No canonical frontend refresh consumes backend entity ${entity}`,
      ).not.toHaveLength(0);
    }
  });

  it('never subscribes to entity names that the contract explicitly forbids', () => {
    for (const forbidden of contract.forbidden_phantom_entity_types) {
      for (const [feature, value] of Object.entries(featureIntegrationManifest)) {
        expect(
          value.realtimeEntities,
          `${feature} subscribes to phantom backend entity ${forbidden}`,
        ).not.toContain(forbidden);
      }
    }
  });

  it('maps bridge-only command names to a canonical consumed entity', () => {
    for (const [input, output] of Object.entries(contract.bridge_input_aliases)) {
      expect(input).not.toBe(output);
      expect(contract.organization_outbox_entity_types).toContain(output);
      expect(downstreamConsumersFor(output)).not.toHaveLength(0);
    }
  });

  it('keeps privacy-suppressed command entities explicit without calling them outbox rows', () => {
    for (const entity of contract.command_entity_types_suppressed_from_generic_outbox) {
      expect(contract.organization_outbox_entity_types).not.toContain(entity);
    }
  });

  it('declares every database-trigger-only entity as a canonical consumed outbox type', () => {
    for (const entity of contract.database_trigger_only_entity_types) {
      expect(contract.organization_outbox_entity_types).toContain(entity);
      expect(downstreamConsumersFor(entity)).not.toHaveLength(0);
    }
  });
});
