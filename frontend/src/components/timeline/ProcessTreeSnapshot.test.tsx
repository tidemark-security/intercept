import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@tidemark-security/ux';
import { describe, expect, it, vi } from 'vitest';
import type { ProcessTreeNode } from '@/types/generated/models/ProcessTreeNode';
import { ProcessTreeSnapshot } from './ProcessTreeSnapshot';

const root = { id: 'desktop', process_name: 'explorer.exe', process_id: 4120 };
const independentRoot = { id: 'services', process_name: 'services.exe', process_id: 624 };
const shell = { id: 'shell', parent_id: 'desktop', process_name: 'shell.exe', process_id: 7312 };
const capture: ProcessTreeNode[] = [
  root,
  { ...shell, is_alert_source: true, verdict: 'suspicious', is_signed: false, file_writes: 2, network_connections: 0 },
  { id: 'child', parent_id: 'shell', process_name: 'worker.exe', process_id: 1504, command_line: 'worker.exe --report summary.txt' },
  { id: 'peer', parent_id: 'desktop', process_name: 'editor.exe', process_id: 7312 },
  independentRoot,
];

function setup(processes = capture) {
  const user = userEvent.setup();
  render(<ProcessTreeSnapshot timestamp="2026-11-26T09:42:18Z" processes={processes} />, { wrapper: ThemeProvider });
  const disclosure = screen.getByRole('button', { name: 'View process tree' });
  return { user, disclosure };
}

describe('ProcessTreeSnapshot', () => {
  it('uses arrow keys to move across the hierarchy and Enter to inspect a process', async () => {
    const { user, disclosure } = setup([shell, root, independentRoot]);
    expect(screen.queryByRole('treegrid')).not.toBeInTheDocument();
    await user.click(disclosure);

    const tree = screen.getByRole('treegrid', { name: 'Process tree' });
    const parent = within(tree).getByRole('row', { name: /explorer.exe/ });
    expect(parent).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText(/09:42:18 UTC/)).toBeVisible();

    await user.tab();
    await user.tab();
    await user.tab();
    expect(parent).toHaveFocus();
    await user.keyboard('{ArrowRight}{ArrowRight}');
    const child = within(tree).getByRole('row', { name: /shell.exe/ });
    expect(child).toHaveFocus();
    expect(child).toHaveAttribute('aria-level', '2');
    await user.keyboard('{Enter}');
    expect(child).toHaveAttribute('aria-selected', 'true');
    const inspector = screen.getByRole('region', { name: 'Process details' });
    expect(inspector).toHaveTextContent('explorer.exe (4120)');
    expect(inspector).toHaveTextContent('7312');

    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(parent).toHaveFocus();
    expect(child).not.toBeInTheDocument();
    expect(inspector).toHaveTextContent('shell.exe');
    await user.keyboard('{End}');
    expect(within(tree).getByRole('row', { name: /services.exe/ })).toHaveFocus();
  });

  it('combines name, PID, or command-line search with attack-path filtering', async () => {
    const { user, disclosure } = setup();
    await user.click(disclosure);
    const query = screen.getByRole('searchbox', { name: 'Filter processes' });
    const attackPath = screen.getByRole('button', { name: 'Attack path' });
    const commandLines = screen.getByRole('button', { name: 'Command lines' });

    await user.click(attackPath);
    expect(attackPath).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('row', { name: /explorer.exe/ })).toBeVisible();
    expect(screen.getByRole('row', { name: /shell.exe.*Alert source.*Suspicious/ })).toBeVisible();
    expect(screen.getByRole('row', { name: /worker.exe/ })).toBeVisible();
    expect(screen.queryByRole('row', { name: /editor.exe|services.exe/ })).not.toBeInTheDocument();

    await user.click(commandLines);
    expect(screen.queryByText('worker.exe --report summary.txt')).not.toBeInTheDocument();
    await user.type(query, 'SUMMARY.TXT');
    expect(screen.getByRole('row', { name: /explorer.exe/ })).toBeVisible();
    expect(screen.getByRole('row', { name: /shell.exe/ })).toBeVisible();
    expect(screen.getByRole('row', { name: /worker.exe/ })).toBeVisible();
    await user.clear(query);
    await user.type(query, '7312');
    expect(screen.getByRole('row', { name: /shell.exe/ })).toBeVisible();
    expect(screen.queryByRole('row', { name: /editor.exe|worker.exe/ })).not.toBeInTheDocument();
    await user.clear(query);
    await user.type(query, 'WORKER.EXE');
    expect(screen.getByRole('row', { name: /worker.exe/ })).toBeVisible();
    await user.clear(query);
    await user.type(query, 'editor.exe');
    expect(screen.getByText('No process matches “editor.exe”.')).toBeVisible();
    await user.click(attackPath);
    expect(screen.getByRole('row', { name: /editor.exe/ })).toBeVisible();
  });

  it('shows available signals and copies the command line independently of the row toggle', async () => {
    const { user, disclosure } = setup();
    const copy = vi.spyOn(navigator.clipboard, 'writeText');
    await user.click(disclosure);
    const inspector = screen.getByRole('region', { name: 'Process details' });
    expect(within(inspector).getByText('Unsigned image')).toBeVisible();
    expect(within(inspector).getByText('0', { exact: true })).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Command lines' }));
    await user.click(screen.getByRole('row', { name: /worker.exe/ }));
    const workerDetails = within(screen.getByRole('region', { name: 'Process details' }));
    expect(workerDetails.getByText('worker.exe --report summary.txt')).toBeVisible();
    await user.click(workerDetails.getByRole('button', { name: 'Copy command line' }));
    expect(copy).toHaveBeenCalledWith('worker.exe --report summary.txt');
    expect(screen.getByText('Command line copied.')).toBeInTheDocument();
  });

  it('reports an empty capture distinctly from a search with no results', async () => {
    const { user, disclosure } = setup([]);
    await user.click(disclosure);
    expect(screen.getByText('No process telemetry for this snapshot.')).toBeVisible();
    expect(screen.queryByRole('treegrid')).not.toBeInTheDocument();
  });
});
