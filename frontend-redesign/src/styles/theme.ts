export interface CareSyncTheme {
  mode: 'public' | 'workspace';
  color: {
    canvas: string;
    canvasElevated: string;
    surface: string;
    surfaceStrong: string;
    surfaceHover: string;
    glass: string;
    control: string;
    controlBorder: string;
    overlay: string;
    border: string;
    borderStrong: string;
    divider: string;
    text: string;
    textSoft: string;
    textMuted: string;
    plasma: string;
    plasmaBright: string;
    cyan: string;
    mint: string;
    amber: string;
    coral: string;
    ink: string;
  };
  effect: {
    panelHighlight: string;
    panelSheen: string;
    panelSheenOpacity: number;
    panelBlur: string;
    panelSaturation: string;
    accentGlow: string;
    statusGlow: string;
    primaryGradient: string;
    primaryShadow: string;
    overlayBlur: string;
  };
  space: {
    xs: string;
    sm: string;
    md: string;
    lg: string;
    xl: string;
    xxl: string;
    giant: string;
  };
  radius: {
    sm: string;
    md: string;
    lg: string;
    xl: string;
    pill: string;
  };
  shadow: {
    panel: string;
    glow: string;
    cyan: string;
  };
  motion: {
    fast: string;
    normal: string;
    slow: string;
    ease: string;
  };
  layout: {
    rail: string;
    railCollapsed: string;
    header: string;
    content: string;
  };
  breakpoint: {
    mobile: string;
    tablet: string;
    desktop: string;
  };
}

const shared = {
  space: {
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '24px',
    xxl: '32px',
    giant: '48px',
  },
  radius: {
    sm: '8px',
    md: '13px',
    lg: '20px',
    xl: '28px',
    pill: '999px',
  },
  layout: {
    rail: '278px',
    railCollapsed: '88px',
    header: '76px',
    content: '1680px',
  },
  breakpoint: {
    mobile: '720px',
    tablet: '1080px',
    desktop: '1280px',
  },
} as const;

export const publicTheme: CareSyncTheme = {
  mode: 'public',
  color: {
    canvas: '#060812',
    canvasElevated: '#0b1020',
    surface: 'rgba(15, 20, 39, 0.78)',
    surfaceStrong: '#11182d',
    surfaceHover: 'rgba(28, 35, 62, 0.88)',
    glass: 'rgba(13, 18, 34, 0.66)',
    control: '#11182d',
    controlBorder: 'rgba(173, 151, 255, 0.34)',
    overlay: 'rgba(2, 4, 12, 0.72)',
    border: 'rgba(164, 180, 255, 0.14)',
    borderStrong: 'rgba(173, 151, 255, 0.34)',
    divider: 'rgba(164, 180, 255, 0.14)',
    text: '#f5f6ff',
    textSoft: '#c2c8dc',
    textMuted: '#7f89a6',
    plasma: '#a978ff',
    plasmaBright: '#c6a8ff',
    cyan: '#53e6ff',
    mint: '#63f4be',
    amber: '#ffca72',
    coral: '#ff7d90',
    ink: '#070914',
  },
  effect: {
    panelHighlight: 'linear-gradient(145deg, rgba(255,255,255,.035), transparent 42%)',
    panelSheen: 'linear-gradient(110deg, transparent 25%, rgba(255,255,255,.035), transparent 67%)',
    panelSheenOpacity: 1,
    panelBlur: '22px',
    panelSaturation: '125%',
    accentGlow: '15px',
    statusGlow: '10px',
    primaryGradient: 'linear-gradient(135deg, rgba(169,120,255,.92), rgba(106,88,220,.88))',
    primaryShadow: '0 10px 28px rgba(120,83,221,.24)',
    overlayBlur: '12px',
  },
  shadow: {
    panel: '0 24px 70px rgba(0, 0, 0, 0.34)',
    glow: '0 0 36px rgba(169, 120, 255, 0.20)',
    cyan: '0 0 30px rgba(83, 230, 255, 0.17)',
  },
  motion: {
    fast: '120ms',
    normal: '190ms',
    slow: '320ms',
    ease: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
  },
  ...shared,
};

export const workspaceTheme: CareSyncTheme = {
  mode: 'workspace',
  color: {
    canvas: '#121826',
    canvasElevated: '#171f30',
    surface: '#202c3e',
    surfaceStrong: '#29374b',
    surfaceHover: '#394b63',
    glass: 'rgba(32, 44, 62, 0.92)',
    control: '#314157',
    controlBorder: '#455a72',
    overlay: 'rgba(8, 13, 24, 0.72)',
    border: 'rgba(181, 217, 232, 0.14)',
    borderStrong: '#455a72',
    divider: 'rgba(181, 217, 232, 0.10)',
    text: '#f4f0e8',
    textSoft: '#d3d5d2',
    textMuted: '#b3bdc9',
    plasma: '#a88cf2',
    plasmaBright: '#c7f0fc',
    cyan: '#7bd3f0',
    mint: '#8ed8b0',
    amber: '#f2be74',
    coral: '#ee9187',
    ink: '#101724',
  },
  effect: {
    panelHighlight: 'linear-gradient(115deg, rgba(199,240,252,.07), transparent 30%, rgba(168,140,242,.04) 66%, transparent)',
    panelSheen: 'linear-gradient(110deg, transparent 24%, rgba(199,240,252,.045), transparent 68%)',
    panelSheenOpacity: 0.45,
    panelBlur: '4px',
    panelSaturation: '104%',
    accentGlow: '6px',
    statusGlow: '3px',
    primaryGradient: 'linear-gradient(135deg, #7bd3f0, #a88cf2)',
    primaryShadow: '0 6px 16px rgba(73, 121, 166, 0.18)',
    overlayBlur: '6px',
  },
  shadow: {
    panel: '0 16px 38px rgba(4, 10, 20, 0.18), inset 0 1px 0 rgba(199, 240, 252, 0.035)',
    glow: '0 0 12px rgba(168, 140, 242, 0.11)',
    cyan: '0 0 10px rgba(123, 211, 240, 0.09)',
  },
  motion: {
    fast: '120ms',
    normal: '180ms',
    slow: '260ms',
    ease: 'cubic-bezier(0.2, 0.8, 0.2, 1)',
  },
  ...shared,
};

// Compatibility export for the existing public root provider.
export const theme = publicTheme;
