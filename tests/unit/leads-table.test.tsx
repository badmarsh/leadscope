import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { LeadsTable } from '@/components/leads-table';
import { leads } from '@/lib/leads-data';

// Wrap translation hook to avoid errors
vi.mock('@/lib/i18n', () => ({
  useTranslation: () => ({ t: (key: string, opts?: any) => opts?.defaultValue || key })
}));

describe('LeadsTable Component', () => {
  it('renders table headers', () => {
    render(
      <LeadsTable
        leads={leads}
        selectedId={null}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByText('Company')).toBeInTheDocument();
    expect(screen.getByText('Domain')).toBeInTheDocument();
    expect(screen.getByText('Score')).toBeInTheDocument();
    expect(screen.getAllByText('Status')[0]).toBeInTheDocument();
  });

  it('renders only pending leads by default', () => {
    const reviewLeads = leads.map(l => l.id === 'jx-001' ? { ...l, status: 'enriched' as const, rationale: 'R', enrichment_report: 'R', screenshot_url: 'http://s', contact_email: 'e@a.com', contact_phone: '123', products_sold: ['P'], evidence: { kind: 'urls' as const, urls: ['u'] } } : l)
    render(
      <LeadsTable
        leads={reviewLeads}
        selectedId={null}
        onSelect={vi.fn()}
      />
    );

    // Budapesti Klíma Kft. is for review (enriched + complete)
    expect(screen.getByText('Budapesti Klíma Kft.')).toBeInTheDocument();
    
    // Duna Épületgépészet Zrt. is approved (approved tab)
    expect(screen.queryByText('Duna Épületgépészet Zrt.')).not.toBeInTheDocument();
  });

  it('calls onSelect when a row is clicked', () => {
    const handleSelect = vi.fn();
    const reviewLeads = leads.map(l => l.id === 'jx-001' ? { ...l, status: 'enriched' as const, rationale: 'R', enrichment_report: 'R', screenshot_url: 'http://s', contact_email: 'e@a.com', contact_phone: '123', products_sold: ['P'], evidence: { kind: 'urls' as const, urls: ['u'] } } : l)
    render(
      <LeadsTable
        leads={reviewLeads}
        selectedId={null}
        onSelect={handleSelect}
      />
    );

    // Click the first lead row
    const row = screen.getByText('Budapesti Klíma Kft.').closest('tr');
    fireEvent.click(row!);

    expect(handleSelect).toHaveBeenCalledWith(expect.objectContaining({
      company: 'Budapesti Klíma Kft.'
    }));
  });

  it('filters by search query', () => {
    const reviewLeads = leads.map(l => (l.id === 'jx-001' || l.id === 'jx-002') ? { ...l, status: 'enriched' as const, rationale: 'R', enrichment_report: 'R', screenshot_url: 'http://s', contact_email: 'e@a.com', contact_phone: '123', products_sold: ['P'], evidence: { kind: 'urls' as const, urls: ['u'] } } : l)
    render(
      <LeadsTable
        leads={reviewLeads}
        selectedId={null}
        onSelect={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText('Search by company or domain…');
    fireEvent.change(searchInput, { target: { value: 'Pannon' } });

    expect(screen.getByText('Pannon Hűtéstechnika')).toBeInTheDocument();
    expect(screen.queryByText('Budapesti Klíma Kft.')).not.toBeInTheDocument();
  });

  it('switches to reviewed tab', () => {
    render(
      <LeadsTable
        leads={leads}
        selectedId={null}
        onSelect={vi.fn()}
      />
    );

    const reviewedTab = screen.getByRole('tab', { name: /Approved/i });
    fireEvent.click(reviewedTab);

    // Now pending leads shouldn't be there
    expect(screen.queryByText('Budapesti Klíma Kft.')).not.toBeInTheDocument();
    
    // But approved leads should
    expect(screen.getByText('Duna Épületgépészet Zrt.')).toBeInTheDocument();
  });

  it('hides incomplete pending leads from Pending Review tab', () => {
    const incompletePendingLead = {
      ...leads[0],
      id: 'jx-inc',
      company: 'Incomplete Corp',
      status: 'pending' as const,
      contact_email: undefined,
    };
    render(
      <LeadsTable
        leads={[incompletePendingLead]}
        selectedId={null}
        onSelect={vi.fn()}
      />
    );
    expect(screen.queryByText('Incomplete Corp')).not.toBeInTheDocument();
  });
});

describe('Pipeline tab', () => {
  const rawCandidates = [
    { id: 1, domain: 'pipelinesite.sk', company_name: 'Pipeline Co', source: 'publicwww', 
      status: 'new', created_at: '2026-07-01T00:00:00Z', enrichment_attempt_count: 0 },
    { id: 2, domain: 'failed.sk', company_name: null, source: 'manual',
      status: 'enrichment_failed', created_at: '2026-07-02T00:00:00Z', enrichment_attempt_count: 3 },
  ];

  it('shows Pipeline tab with count badge', () => {
    render(
      <LeadsTable leads={leads} selectedId={null} onSelect={vi.fn()} rawCandidates={rawCandidates} />
    );
    expect(screen.getByRole('tab', { name: /Pipeline/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Pipeline/i }).textContent).toContain('2');
  });

  it('renders pipeline candidates when tab is clicked', () => {
    render(
      <LeadsTable leads={leads} selectedId={null} onSelect={vi.fn()} rawCandidates={rawCandidates} />
    );
    fireEvent.click(screen.getByRole('tab', { name: /Pipeline/i }));
    expect(screen.getByText('Pipeline Co')).toBeInTheDocument();
  });

  it('shows empty state when no rawCandidates', () => {
    render(
      <LeadsTable leads={leads} selectedId={null} onSelect={vi.fn()} rawCandidates={[]} />
    );
    fireEvent.click(screen.getByRole('tab', { name: /Pipeline/i }));
    expect(screen.getByText(/No candidates in pipeline/i)).toBeInTheDocument();
  });

  it('shows attempt count for enrichment_failed candidates', () => {
    render(
      <LeadsTable leads={leads} selectedId={null} onSelect={vi.fn()} rawCandidates={rawCandidates} />
    );
    fireEvent.click(screen.getByRole('tab', { name: /Pipeline/i }));
    expect(screen.getAllByText(/\(3\)/).length).toBeGreaterThanOrEqual(1);
  });
});

describe('Completeness dot', () => {
  it('renders a dot cell for each lead row', () => {
    const reviewLeads = leads.map(l => ({ ...l, status: 'enriched' as const, rationale: 'R', enrichment_report: 'R', screenshot_url: 'http://s', contact_email: 'e@a.com', contact_phone: '123', products_sold: ['P'], evidence: { kind: 'urls' as const, urls: ['u'] } }))
    render(<LeadsTable leads={reviewLeads} selectedId={null} onSelect={vi.fn()} />);
    const dots = document.querySelectorAll('.bg-emerald-500, .bg-red-500');
    expect(dots.length).toBeGreaterThan(0);
  });

  it('dot is green for complete lead', () => {
    const completeLead = {
      ...leads[0],
      status: 'enriched' as const,
      rationale: 'Good fit',
      enrichment_report: 'Overview',
      screenshot_url: 'https://ss.example.com/img.jpg',
      contact_email: 'a@b.com',
      contact_phone: '+421900000000',
      products_sold: ['Product'],
      evidence: { kind: 'urls' as const, urls: ['https://example.com'] },
      campaignId: 'jenex' as const,
    };
    render(<LeadsTable leads={[completeLead]} selectedId={null} onSelect={vi.fn()} />);
    const greenDot = document.querySelector('.bg-emerald-500');
    expect(greenDot).toBeTruthy();
  });

  it('dot is red for incomplete lead', () => {
    const incompleteLead = {
      ...leads[0],
      status: 'approved' as const,
      contact_email: undefined,
      screenshot_url: undefined,
    };
    render(<LeadsTable leads={[incompleteLead]} selectedId={null} onSelect={vi.fn()} />);
    fireEvent.click(screen.getByRole('tab', { name: /Approved/i }));
    const redDot = document.querySelector('.bg-red-500');
    expect(redDot).toBeTruthy();
  });

  it('dot tooltip lists missing fields', () => {
    const incompleteLead = { ...leads[0], status: 'approved' as const, contact_email: undefined };
    render(<LeadsTable leads={[incompleteLead]} selectedId={null} onSelect={vi.fn()} />);
    fireEvent.click(screen.getByRole('tab', { name: /Approved/i }));
    const redDot = document.querySelector('.bg-red-500');
    expect(redDot?.getAttribute('title')).toContain('Email');
  });
});
