import { isCommandOutcomeUnknown } from '../../api/childcareCommand';
import {
  buildFamilyCoreUpdateCommand,
  buildFamilyEmergencyContactsReplacementCommand,
  buildFamilyGuardianReplacementCommand,
  type FamilyCoreUpdateCommand,
  type FamilyEmergencyContactsReplacementCommand,
  type FamilyGuardianReplacementCommand,
} from './familiesApi';
import { familyCoreChanged, toFamilyPatchInput } from './familyForms';
import type { FamilyDetailRecord, FamilyEditInput } from './types';

export type FamilyEditStage = 'core' | 'primary_guardian' | 'secondary_guardian' | 'emergency_contacts';

const STAGE_LABELS: Record<FamilyEditStage, string> = {
  core: 'family details',
  primary_guardian: 'primary guardian',
  secondary_guardian: 'secondary guardian',
  emergency_contacts: 'emergency contacts',
};

export interface FamilyEditPlanErrorOptions {
  stage: FamilyEditStage;
  confirmedStages: readonly FamilyEditStage[];
  cause: unknown;
  outcomeUnknown: boolean;
}

/**
 * Reports a staged family save without pretending earlier, confirmed commands
 * were rolled back. Durable recovery resolves unknown outcomes before any new command.
 */
export class FamilyEditPlanError extends Error {
  readonly stage: FamilyEditStage;
  readonly stageLabel: string;
  readonly confirmedStages: readonly FamilyEditStage[];
  readonly confirmedStageLabels: readonly string[];
  readonly outcomeUnknown: boolean;
  readonly cause: unknown;

  constructor(options: FamilyEditPlanErrorOptions) {
    const confirmed = options.confirmedStages.map((stage) => STAGE_LABELS[stage]);
    const prefix = confirmed.length
      ? `${confirmed.join(', ')} ${confirmed.length === 1 ? 'is' : 'are'} confirmed saved. `
      : 'No family section is confirmed saved yet. ';
    const suffix = options.outcomeUnknown
      ? `CareSync could not confirm the ${STAGE_LABELS[options.stage]} command. Check the saved result; earlier sections will not be sent again.`
      : `The ${STAGE_LABELS[options.stage]} command failed. Reload the record before correcting only that section and anything after it.`;
    super(`${prefix}${suffix}`);
    this.name = 'FamilyEditPlanError';
    this.stage = options.stage;
    this.stageLabel = STAGE_LABELS[options.stage];
    this.confirmedStages = Object.freeze([...options.confirmedStages]);
    this.confirmedStageLabels = Object.freeze(confirmed);
    this.outcomeUnknown = options.outcomeUnknown;
    this.cause = options.cause;
  }
}

interface FamilyEditPlanDependencies {
  updateCore: (
    familyId: string,
    command: FamilyCoreUpdateCommand,
    organizationId: string,
    signal?: AbortSignal,
  ) => Promise<FamilyDetailRecord>;
  replaceGuardian: (
    familyId: string,
    slot: 'primary' | 'secondary',
    command: FamilyGuardianReplacementCommand,
    organizationId: string,
    signal?: AbortSignal,
  ) => Promise<FamilyDetailRecord>;
  replaceEmergencyContacts: (
    familyId: string,
    command: FamilyEmergencyContactsReplacementCommand,
    organizationId: string,
    signal?: AbortSignal,
  ) => Promise<FamilyDetailRecord>;
}

interface FamilyEditPlanInput {
  baseline: FamilyDetailRecord;
  edit: FamilyEditInput;
  organizationId: string;
  signal?: AbortSignal;
}

type StageCommand =
  | FamilyCoreUpdateCommand
  | FamilyGuardianReplacementCommand
  | FamilyEmergencyContactsReplacementCommand;

interface PlannedStage {
  key: FamilyEditStage;
  build: (current: FamilyDetailRecord) => StageCommand;
  execute: (
    current: FamilyDetailRecord,
    command: StageCommand,
    signal?: AbortSignal,
  ) => Promise<FamilyDetailRecord>;
}

export async function runFamilyEditCommandPlan(
  input: FamilyEditPlanInput,
  dependencies: FamilyEditPlanDependencies,
): Promise<FamilyDetailRecord> {
  const changed = toFamilyPatchInput(input.edit, input.baseline);
  const stages: PlannedStage[] = [];

  if (familyCoreChanged(input.edit, input.baseline)) {
    stages.push({
      key: 'core',
      build: (current) => buildFamilyCoreUpdateCommand(input.edit, current.version),
      execute: (current, command, signal) => dependencies.updateCore(
        current.id,
        command as FamilyCoreUpdateCommand,
        input.organizationId,
        signal,
      ),
    });
  }
  if (Object.prototype.hasOwnProperty.call(changed, 'primary_guardian')) {
    stages.push({
      key: 'primary_guardian',
      build: (current) => buildFamilyGuardianReplacementCommand(changed.primary_guardian ?? null, current.version),
      execute: (current, command, signal) => dependencies.replaceGuardian(
        current.id,
        'primary',
        command as FamilyGuardianReplacementCommand,
        input.organizationId,
        signal,
      ),
    });
  }
  if (Object.prototype.hasOwnProperty.call(changed, 'secondary_guardian')) {
    stages.push({
      key: 'secondary_guardian',
      build: (current) => buildFamilyGuardianReplacementCommand(changed.secondary_guardian ?? null, current.version),
      execute: (current, command, signal) => dependencies.replaceGuardian(
        current.id,
        'secondary',
        command as FamilyGuardianReplacementCommand,
        input.organizationId,
        signal,
      ),
    });
  }
  if (Object.prototype.hasOwnProperty.call(changed, 'emergency_contacts')) {
    stages.push({
      key: 'emergency_contacts',
      build: (current) => buildFamilyEmergencyContactsReplacementCommand(changed.emergency_contacts ?? [], current.version),
      execute: (current, command, signal) => dependencies.replaceEmergencyContacts(
        current.id,
        command as FamilyEmergencyContactsReplacementCommand,
        input.organizationId,
        signal,
      ),
    });
  }

  const runFrom = async (
    index: number,
    current: FamilyDetailRecord,
    confirmed: readonly FamilyEditStage[],
    signal: AbortSignal | undefined,
  ): Promise<FamilyDetailRecord> => {
    if (index >= stages.length) return current;
    const stage = stages[index];
    const command = stage.build(current);

    try {
      const saved = await stage.execute(current, command, signal);
      return runFrom(index + 1, saved, [...confirmed, stage.key], signal);
    } catch (caught) {
      const outcomeUnknown = isCommandOutcomeUnknown(caught);
      throw new FamilyEditPlanError({
        stage: stage.key,
        confirmedStages: confirmed,
        cause: caught,
        outcomeUnknown,
      });
    }
  };

  return runFrom(0, input.baseline, [], input.signal);
}
