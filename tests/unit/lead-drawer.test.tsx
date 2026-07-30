import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { LeadDrawer } from '@/components/lead-drawer';
import { leads } from '@/lib/leads-data';

// Mock translation hook
vi.mock('@/lib/i18n', () => ({
  useTranslation: () => ({ t: (key: string, opts?: any) => opts?.defaultValue || key })
}))

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
    expect(screen.getAllByText(pendingLead.domain).length).toBeGreaterThanOrEqual(1);
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

describe('Campaign-specific sidebar sections', () => {
  const pendingLead = leads.find(l => l.status === 'pending')!;

  it('shows PDF Brochure section for jenex lead with brochure URL', () => {
    const jenexLead = {
      ...pendingLead,
      campaignId: 'jenex' as const,
      evidence_data: { pdf_brochure_url: 'https://example.com/catalogue.pdf' }
    };
    render(<LeadDrawer lead={jenexLead as any} onClose={vi.fn()} onDecision={vi.fn()} onReopen={vi.fn()} />);
    expect(screen.getByText(/PDF Brochure|Katalóg/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /catalogue.pdf/i })).toBeInTheDocument();
  });

  it('shows "no brochure" message for jenex lead without URL', () => {
    const jenexLead = { ...pendingLead, campaignId: 'jenex' as const, evidence_data: {} };
    render(<LeadDrawer lead={jenexLead as any} onClose={vi.fn()} onDecision={vi.fn()} onReopen={vi.fn()} />);
    expect(screen.getByText(/No brochure URL found|Nenašla sa žiadna URL/i)).toBeInTheDocument();
  });

  it('shows Product List section for shoe-photo lead', () => {
    const shoeLead = {
      ...pendingLead,
      campaignId: 'shoe-photo' as const,
      evidence_data: {
        products_url: 'https://shoes.sk/products',
        product_count: 142,
        product_categories: ['Running', 'Casual']
      }
    };
    render(<LeadDrawer lead={shoeLead as any} onClose={vi.fn()} onDecision={vi.fn()} onReopen={vi.fn()} />);
    expect(screen.getByText(/Product List|Zoznam produktov/i)).toBeInTheDocument();
    expect(screen.getByText('142')).toBeInTheDocument();
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('Casual')).toBeInTheDocument();
  });

  it('shows Threat Intel for wp-remediation lead with proof data', () => {
    const wpLead = {
      ...pendingLead,
      campaignId: 'wp-remediation' as const,
      evidence: { kind: 'malware', malwareFamily: 'Blackhat', sourcePost: { title: 'Post', url: 'https://x.com' }, lastConfirmed: '2026-07-01' },
      proof_data: { proof_type: 'google_serp_spam', evidence_text: 'Spam indexed', indexed_spam_pages: 5 }
    };
    render(<LeadDrawer lead={wpLead as any} onClose={vi.fn()} onDecision={vi.fn()} onReopen={vi.fn()} />);
    expect(screen.getByText(/Threat Intelligence/i)).toBeInTheDocument();
    expect(screen.getByText(/SEO Spam Indexed/i)).toBeInTheDocument();
  });

  it('screenshot figcaption domain link opens in _blank', () => {
    const leadWithScreenshot = { ...pendingLead, screenshot_url: 'https://ss.example.com/img.jpg' };
    render(<LeadDrawer lead={leadWithScreenshot} onClose={vi.fn()} onDecision={vi.fn()} onReopen={vi.fn()} />);
    const domainLinks = screen.getAllByRole('link', { name: new RegExp(pendingLead.domain) });
    const figLink = domainLinks.find(link => link.getAttribute('target') === '_blank');
    expect(figLink).toBeDefined();
    expect(figLink?.getAttribute('target')).toBe('_blank');
  });
});
