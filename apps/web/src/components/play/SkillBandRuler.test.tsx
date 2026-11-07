import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SkillBandRuler } from './SkillBandRuler';

describe('SkillBandRuler', () => {
  it('shades ±100 of ±800 at the start and the whole ruler once capped', () => {
    const { rerender } = render(<SkillBandRuler rating={1712} seconds={0} />);
    expect(screen.getByTestId('skill-band')).toHaveStyle({
      left: '43.75%',
      width: '12.5%',
    });
    expect(screen.getByText('912')).toBeInTheDocument();
    expect(screen.getByText('2512')).toBeInTheDocument();
    rerender(<SkillBandRuler rating={1712} seconds={120} />);
    expect(screen.getByTestId('skill-band')).toHaveStyle({ left: '0%', width: '100%' });
  });

  it('labels relative to you when the rating is unknown', () => {
    render(<SkillBandRuler rating={null} seconds={0} />);
    expect(screen.getByText('You')).toBeInTheDocument();
    expect(screen.getByText('+800')).toBeInTheDocument();
  });
});
