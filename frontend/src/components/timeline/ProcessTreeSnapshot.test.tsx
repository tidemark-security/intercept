import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@tidemark-security/ux';
import { describe, expect, it } from 'vitest';
import { ProcessTreeSnapshot } from './ProcessTreeSnapshot';

describe('ProcessTreeSnapshot', () => {
  it('expands ancestry and inspects a process independently of its branch', async () => {
    const user = userEvent.setup();
    render(<ProcessTreeSnapshot timestamp="2026-11-26T09:42:18Z" processes={[
      { id: 'shell', parent_id: 'desktop', process_name: 'powershell.exe', process_id: 7312, status: 'running' },
      { id: 'desktop', process_name: 'explorer.exe', process_id: 4120, status: 'running' },
      { id: 'services', process_name: 'services.exe', process_id: 624 },
    ]} />, { wrapper: ThemeProvider });

    const disclosure = screen.getByRole('button', { name: 'View process tree' });
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    await user.click(disclosure);
    const table = screen.getByRole('table', { name: 'Processes in snapshot' });
    const inspector = screen.getByRole('region', { name: 'Process details' });
    expect(within(table).getByRole('button', { name: /Inspect services.exe/ })).toBeVisible();
    expect(within(table).queryByRole('button', { name: /Inspect powershell.exe/ })).not.toBeInTheDocument();
    expect(screen.getByText(/09:42:18 UTC/)).toBeVisible();
    expect(screen.queryByRole('slider')).not.toBeInTheDocument();

    await user.click(within(table).getByRole('button', { name: /Expand explorer.exe/ }));
    const shell = within(table).getByRole('button', { name: /Inspect powershell.exe/ });
    shell.focus();
    await user.keyboard('{Enter}');
    expect(shell).toHaveAttribute('aria-pressed', 'true');
    expect(inspector).toHaveTextContent('explorer.exe (4120)');
    expect(inspector).toHaveTextContent('7312');

    await user.click(within(table).getByRole('button', { name: /Collapse explorer.exe/ }));
    expect(shell).not.toBeInTheDocument();
    expect(inspector).toHaveTextContent('powershell.exe');
  });
});
