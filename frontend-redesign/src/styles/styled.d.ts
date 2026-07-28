import 'styled-components';
import type { CareSyncTheme } from './theme';

declare module 'styled-components' {
  export interface DefaultTheme extends CareSyncTheme {}
}
