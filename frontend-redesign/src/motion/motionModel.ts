export const CARESYNC_MOTION_STORAGE_KEY = 'caresync-redesign-motion-v1';

export type MotionMode = 'system' | 'full' | 'off';
export type ResolvedMotionMode = 'full' | 'reduced' | 'off';
export type MotionDataValue = ResolvedMotionMode | 'paused';

export interface MotionEnvironment {
  mode: MotionMode;
  prefersReducedMotion: boolean;
  documentVisible: boolean;
  finePointer: boolean;
}

export interface MotionSnapshot extends MotionEnvironment {
  resolvedMode: ResolvedMotionMode;
  dataValue: MotionDataValue;
  motionAllowed: boolean;
  autonomousAllowed: boolean;
}

export function parseMotionMode(value: string | null | undefined): MotionMode {
  return value === 'full' || value === 'off' || value === 'system' ? value : 'system';
}

export function resolveMotionPreference(environment: MotionEnvironment): MotionSnapshot {
  const resolvedMode: ResolvedMotionMode = environment.mode === 'off'
    ? 'off'
    : environment.mode === 'full'
      ? 'full'
      : environment.prefersReducedMotion
        ? 'reduced'
        : 'full';

  const motionAllowed = resolvedMode === 'full';
  const autonomousAllowed = motionAllowed && environment.documentVisible;
  const dataValue: MotionDataValue = motionAllowed && !environment.documentVisible
    ? 'paused'
    : resolvedMode;

  return {
    ...environment,
    resolvedMode,
    dataValue,
    motionAllowed,
    autonomousAllowed,
  };
}
