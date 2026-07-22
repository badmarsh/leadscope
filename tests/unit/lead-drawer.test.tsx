import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { LeadDrawer } from '@/components/lead-drawer';
import { leads } from '@/lib/leads-data';

// Mock next/image without passing boolean attributes to DOM img tag
vi.mock('next/image', () => ({
  __esModule: true,
  default: ({ fill, unoptimized, priority, ...props }: any) => {
    return <img {...props} />
  },
}));

describe('LeadDrawer Component', () => {
  const pendingLead = leads.find(l => l.status === 'pending')!;
  const approvedLead = leads.find(l => l.status === 'approved')!;

  it('renders nothing when lead is null', () => {
    const { container } = render(
      <LeadDrawer
        lead={null}
        onClose={vi.fn()}
        onDecision={vi.fn()}
        onReopen={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders lead details correctly', () => {
    render(
      <LeadDrawer
        lead={pendingLead}
        onClose={vi.fn()}
        onDecision={vi.fn()}
        onReopen={vi.fn()}
      />
    );

    expect(screen.getByText(pendingLead.company)).toBeInTheDocument();
    expect(screen.getByText(pendingLead.domain)).toBeInTheDocument();
    expect(screen.getByText(pendingLead.rationale)).toBeInTheDocument();
  });

  it('calls onDecision when Approve is clicked', () => {
    const handleDecision = vi.fn();
    render(
      <LeadDrawer
        lead={pendingLead}
        onClose={vi.fn()}
        onDecision={handleDecision}
        onReopen={vi.fn()}
      />
    );

    const approveBtn = screen.getByRole('button', { name: /Approve/i });
    fireEvent.click(approveBtn);

    expect(handleDecision).toHaveBeenCalledWith(pendingLead.id, 'approved', '');
  });

  it('shows Reopen button for decided leads', () => {
    const handleReopen = vi.fn();
    render(
      <LeadDrawer
        lead={approvedLead}
        onClose={vi.fn()}
        onDecision={vi.fn()}
        onReopen={handleReopen}
      />
    );

    const reopenBtn = screen.getByRole('button', { name: /Reopen/i });
    fireEvent.click(reopenBtn);

    expect(handleReopen).toHaveBeenCalledWith(approvedLead.id);
  });
});
