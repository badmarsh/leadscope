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
    expect(screen.getByText('Status')).toBeInTheDocument();
  });

  it('renders only pending leads by default', () => {
    render(
      <LeadsTable
        leads={leads}
        selectedId={null}
        onSelect={vi.fn()}
      />
    );

    // Budapesti Klíma Kft. is pending
    expect(screen.getByText('Budapesti Klíma Kft.')).toBeInTheDocument();
    
    // Duna Épületgépészet Zrt. is approved (reviewed tab)
    expect(screen.queryByText('Duna Épületgépészet Zrt.')).not.toBeInTheDocument();
  });

  it('calls onSelect when a row is clicked', () => {
    const handleSelect = vi.fn();
    render(
      <LeadsTable
        leads={leads}
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
    render(
      <LeadsTable
        leads={leads}
        selectedId={null}
        onSelect={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText(/Search by company or domain/i);
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

    const reviewedTab = screen.getByRole('tab', { name: /Reviewed/i });
    fireEvent.click(reviewedTab);

    // Now pending leads shouldn't be there
    expect(screen.queryByText('Budapesti Klíma Kft.')).not.toBeInTheDocument();
    
    // But approved leads should
    expect(screen.getByText('Duna Épületgépészet Zrt.')).toBeInTheDocument();
  });
});
