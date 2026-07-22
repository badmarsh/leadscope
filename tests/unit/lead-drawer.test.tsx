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
  
  it('renders images from evidence.photos correctly', () => {
    const leadWithImages = {
      ...pendingLead,
      evidence: {
        kind: "photos",
        photos: [
          { src: 'https://example.com/img1.png', label: 'Photo 1' },
          { src: 'https://example.com/img2.png', label: 'Photo 2' }
        ]
      }
    };
    
    render(
      <LeadDrawer
        lead={leadWithImages as any}
        onClose={vi.fn()}
        onDecision={vi.fn()}
        onReopen={vi.fn()}
      />
    );

    expect(screen.getByText(/Evidence|Dôkazy/i)).toBeInTheDocument();
    
    // Check if images are rendered
    const images = screen.getAllByRole('img');
    const evidenceImages = images.filter(img => img.getAttribute('src')?.includes('example.com'));
    expect(evidenceImages.length).toBe(2);
    expect(evidenceImages[0].getAttribute('src')).toContain('img1.png');
    expect(evidenceImages[1].getAttribute('src')).toContain('img2.png');
  });
});
