import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@tidemark-security/ux';
import { describe, expect, it, vi } from 'vitest';
import type { ProcessTreeNode } from '@/types/generated/models/ProcessTreeNode';
import { ProcessTreeSnapshot } from './ProcessTreeSnapshot';

const root = { id: 'desktop', process_name: 'explorer.exe', process_id: 4120 };
const independentRoot = { id: 'services', process_name: 'services.exe', process_id: 624 };
const shell = { id: 'shell', parent_id: 'desktop', process_name: 'shell.exe', process_id: 7312 };
const workerCommand = 'worker.exe --report summary.txt';
const capture: ProcessTreeNode[] = [
  root,
  { ...shell, is_alert_source: true, verdict: 'suspicious', is_signed: false, file_writes: 2, network_connections: 0 },
  { id: 'child', parent_id: 'shell', process_name: 'worker.exe', process_id: 1504, command_line: workerCommand },
  { id: 'peer', parent_id: 'desktop', process_name: 'editor.exe', process_id: 7312 },
  independentRoot,
];

function setup(processes = capture) {
  const user = userEvent.setup();
  render(<ProcessTreeSnapshot hostname="WS-014" timestamp="2026-11-26T09:42:18Z" processes={processes} />, { wrapper: ThemeProvider });
  return user;
}

describe('ProcessTreeSnapshot', () => {
  it('opens a process from the keyboard and restores focus to its preview row on Escape', async () => {
    const user = setup([shell, root, independentRoot]);
    const preview = within(screen.getByRole('treegrid', { name: 'Process tree' }));
    const parent = preview.getByRole('row', { name: /explorer.exe/ });
    expect(screen.queryByRole('switch', { name: 'Attack path only' })).not.toBeInTheDocument();
    expect(parent).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText(/09:42:18 UTC/)).toBeVisible();
    expect(screen.queryByRole('region', { name: 'Process details' })).not.toBeInTheDocument();

    await user.tab();
    await user.tab();
    await user.tab();
    await user.tab();
    expect(parent).toHaveFocus();
    await user.keyboard('{ArrowRight}{ArrowRight}');
    const child = preview.getByRole('row', { name: /shell.exe/ });
    expect(child).toHaveFocus();
    expect(child).toHaveAttribute('aria-level', '2');
    await user.keyboard('{Enter}');

    const dialog = await screen.findByRole('dialog', { name: 'Process tree · WS-014' });
    const viewer = within(dialog);
    expect(viewer.getByRole('row', { name: /shell.exe/ })).toHaveAttribute('aria-selected', 'true');
    expect(viewer.getByRole('region', { name: 'Process details' })).toHaveTextContent('explorer.exe (4120)');
    expect(viewer.queryByRole('button', { name: 'Zoom in' })).not.toBeInTheDocument();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await waitFor(() => expect(child).toHaveFocus());

    await user.keyboard('{ArrowLeft}{ArrowLeft}');
    expect(parent).toHaveFocus();
    expect(child).not.toBeInTheDocument();
    await user.keyboard('{End}');
    expect(preview.getByRole('row', { name: /services.exe/ })).toHaveFocus();
  });

  it('defaults to the attack path and shares filtering and display switches with the viewer', async () => {
    const user = setup();
    const preview = within(screen.getByRole('treegrid', { name: 'Process tree' }));
    const query = screen.getByRole('searchbox', { name: 'Filter processes' });
    const attackPath = screen.getByRole('switch', { name: 'Attack path only' });
    const commandLines = screen.getByRole('switch', { name: 'Command lines' });

    expect(attackPath).toBeChecked();
    expect(commandLines).not.toBeChecked();
    expect(preview.getByRole('row', { name: /explorer.exe/ })).toBeVisible();
    expect(preview.getByRole('row', { name: /shell.exe.*Alert source.*Suspicious/ })).toBeVisible();
    expect(preview.getByRole('row', { name: /worker.exe/ })).toBeVisible();
    expect(preview.queryByRole('row', { name: /editor.exe|services.exe/ })).not.toBeInTheDocument();
    expect(preview.queryByText(workerCommand)).not.toBeInTheDocument();

    await user.type(query, 'SUMMARY.TXT');
    expect(preview.getByRole('row', { name: /explorer.exe/ })).toBeVisible();
    expect(preview.getByRole('row', { name: /shell.exe/ })).toBeVisible();
    expect(preview.getByRole('row', { name: /worker.exe/ })).toBeVisible();
    await user.clear(query);
    await user.type(query, '7312');
    expect(preview.getByRole('row', { name: /shell.exe/ })).toBeVisible();
    expect(preview.queryByRole('row', { name: /editor.exe|worker.exe/ })).not.toBeInTheDocument();
    await user.clear(query);
    await user.type(query, 'editor.exe');
    expect(screen.getByText('No process matches “editor.exe”.')).toBeVisible();
    await user.click(attackPath);
    expect(screen.getByRole('row', { name: /editor.exe/ })).toBeVisible();

    const maximize = screen.getByRole('button', { name: 'Maximize process tree' });
    await user.click(maximize);
    const dialog = await screen.findByRole('dialog', { name: 'Process tree · WS-014' });
    const viewer = within(dialog);
    expect(viewer.getByRole('searchbox', { name: 'Filter processes' })).toHaveValue('editor.exe');
    expect(viewer.getByRole('switch', { name: 'Attack path only' })).not.toBeChecked();
    await user.click(viewer.getByRole('button', { name: 'Clear filter' }));
    await user.click(viewer.getByRole('switch', { name: 'Command lines' }));
    await user.click(viewer.getByRole('button', { name: 'Close viewer' }));
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await waitFor(() => expect(maximize).toHaveFocus());
    expect(query).toHaveValue('');
    expect(commandLines).toBeChecked();
    expect(within(screen.getByRole('treegrid', { name: 'Process tree' })).getByText(workerCommand)).toBeVisible();
  });

  it('maximizes to the alert source and keeps the full command line copyable with previews off', async () => {
    const user = setup();
    const copy = vi.spyOn(navigator.clipboard, 'writeText');
    await user.click(screen.getByRole('button', { name: 'Maximize process tree' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Process tree · WS-014' }));
    const inspector = within(dialog.getByRole('region', { name: 'Process details' }));
    expect(inspector.getByText('Unsigned image')).toBeVisible();
    expect(inspector.getByText('0', { exact: true })).toBeVisible();

    const worker = dialog.getByRole('row', { name: /worker.exe/ });
    await user.click(worker);
    const workerDetails = within(dialog.getByRole('region', { name: 'Process details' }));
    expect(workerDetails.getByText(workerCommand)).toBeVisible();
    await user.click(workerDetails.getByRole('button', { name: 'Copy command line' }));
    expect(copy).toHaveBeenCalledWith(workerCommand);
    expect(screen.getByText('Command line copied.')).toBeInTheDocument();
    await user.click(workerDetails.getByRole('button', { name: 'Close process details' }));
    expect(dialog.getByText('Select a process to view its details.')).toBeVisible();
    expect(worker).toHaveFocus();
  });

  it('reports an empty capture and hides the preview controls', () => {
    setup([]);
    expect(screen.getByText('No process telemetry for this snapshot.')).toBeVisible();
    expect(screen.queryByRole('treegrid')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Maximize process tree' })).not.toBeInTheDocument();
  });
});
