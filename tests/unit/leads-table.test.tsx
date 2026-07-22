import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { LeadsTable } from '@/components/leads-table';
import { leads } from '@/lib/leads-data';

describe('LeadsTable Component', () => {
  it('renders all leads initially', () => {
    render(<LeadsTable leads={leads} selectedId={null} onSelect={() => {}} onFilteredChange={() => {}} onBulkAction={() => {}} />);
    expect(screen.getByText('Budapesti Klíma Kft.')).toBeInTheDocument();
    expect(screen.getByText('Pannon Hűtéstechnika')).toBeInTheDocument();
  });

  it('filters leads by search text', () => {
    render(<LeadsTable leads={leads} selectedId={null} onSelect={() => {}} onFilteredChange={() => {}} onBulkAction={() => {}} />);
    expect(screen.getByText('Pannon Hűtéstechnika')).toBeInTheDocument();
    const searchInput = screen.getByPlaceholderText('Search by company or domain…');
    fireEvent.change(searchInput, { target: { value: 'Budapesti' } });
    expect(screen.queryByText('Pannon Hűtéstechnika')).not.toBeInTheDocument();
    expect(screen.getByText('Budapesti Klíma Kft.')).toBeInTheDocument();
  });

  it('filters leads by score presets', () => {
    render(<LeadsTable leads={leads} selectedId={null} onSelect={() => {}} onFilteredChange={() => {}} onBulkAction={() => {}} />);
    const highBtn = screen.getByText('High 80+');
    fireEvent.click(highBtn);
    expect(screen.getByText('Budapesti Klíma Kft.')).toBeInTheDocument();
    expect(screen.queryByText('Alföld Klíma és Fűtés')).not.toBeInTheDocument();

    const medBtn = screen.getByText('Med 60–79');
    fireEvent.click(medBtn);
    expect(screen.getByText('Alföld Klíma és Fűtés')).toBeInTheDocument();
    expect(screen.queryByText('Budapesti Klíma Kft.')).not.toBeInTheDocument();
  });
});
