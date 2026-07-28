import { describe, expect, it } from 'vitest';
import dialogSource from './WorkforceDialog.tsx?raw';
import rotaSource from '../StaffRotaPage.tsx?raw';
import planningSource from '../WorkforcePlanningPanel.tsx?raw';

describe('staff-rota modal viewport boundary', () => {
  it('portals workforce dialogs outside backdrop-filter containing blocks', () => {
    expect(dialogSource).toContain("createPortal(children, document.body)");
    expect(rotaSource).toContain('<WorkforceModalPortal>');
    expect(planningSource).toContain('<WorkforceModalPortal>');
  });

  it('bounds the scrolling dialog surface between safe top and bottom insets', () => {
    expect(dialogSource).toContain('height:100dvh');
    expect(dialogSource).toContain('max-height:100%');
    expect(dialogSource).toContain('overflow-y:auto');
    expect(dialogSource).toContain('overscroll-behavior:contain');
    expect(dialogSource).toContain('env(safe-area-inset-top)');
    expect(dialogSource).toContain('env(safe-area-inset-bottom)');
    expect(dialogSource).toContain('margin-block:auto');
    expect(dialogSource).toContain("document.body.style.overflow = 'hidden'");
  });

  it('moves focus without scrolling the underlying rota page', () => {
    expect(dialogSource.match(/preventScroll: true/g)).toHaveLength(2);
    expect(dialogSource).toContain('input:not(:disabled)');
  });
});
