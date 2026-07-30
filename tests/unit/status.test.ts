import { describe, it, expect } from 'vitest';
import { statusLabels, statusBadgeClasses, scoreColorClasses, formatDate, formatTimestamp, getLeadMissingFields, isLeadComplete } from '@/lib/status';
import type { Lead } from '@/lib/leads-data';

function makeCompleteLead(overrides: Partial<Lead> = {}): Lead {
  return {
    id: '1',
    campaignId: 'jenex',
    company: 'Test Co',
    domain: 'test.com',
    score: 80,
    status: 'pending',
    dateFound: '2026-07-30',
    rationale: 'Good fit',
    evidence: { kind: 'urls', urls: ['https://test.com/products'] },
    enrichment_report: 'Company overview text',
    screenshot_url: 'https://ss.example.com/test.jpg',
    contact_email: 'ceo@test.com',
    contact_phone: '+421900000000',
    products_sold: ['Product A'],
    ...overrides,
  };
}

describe('status utility', () => {
  describe('statusLabels', () => {
    it('maps statuses correctly', () => {
      expect(statusLabels.pending).toBe('Pending');
      expect(statusLabels.approved).toBe('Approved');
      expect(statusLabels.rejected).toBe('Rejected');
      expect(statusLabels.enrichment_failed).toBe('Enrich failed');
    });
  });

  describe('scoreColorClasses', () => {
    it('returns muted colors when score is 0', () => {
      expect(scoreColorClasses(0)).toEqual({
        text: 'text-muted-foreground',
        bar: 'bg-muted-foreground/40'
      });
    });

    it('returns emerald for high scores (>= 80)', () => {
      expect(scoreColorClasses(85)).toEqual({
        text: 'text-emerald-700 dark:text-emerald-400',
        bar: 'bg-emerald-500'
      });
      expect(scoreColorClasses(80)).toEqual({
        text: 'text-emerald-700 dark:text-emerald-400',
        bar: 'bg-emerald-500'
      });
    });

    it('returns amber for medium scores (60 - 79)', () => {
      expect(scoreColorClasses(70)).toEqual({
        text: 'text-amber-700 dark:text-amber-400',
        bar: 'bg-amber-500'
      });
      expect(scoreColorClasses(60)).toEqual({
        text: 'text-amber-700 dark:text-amber-400',
        bar: 'bg-amber-500'
      });
    });

    it('returns red for low scores (> 0 and < 60)', () => {
      expect(scoreColorClasses(59)).toEqual({
        text: 'text-red-700 dark:text-red-400',
        bar: 'bg-red-500'
      });
      expect(scoreColorClasses(1)).toEqual({
        text: 'text-red-700 dark:text-red-400',
        bar: 'bg-red-500'
      });
    });
  });

  describe('Date formatting', () => {
    it('formats date string properly', () => {
      expect(formatDate('2026-07-18')).toMatch(/Jul 18, 2026/);
    });

    it('formats timestamp properly', () => {
      expect(formatTimestamp('2026-07-18T10:00:00Z')).toMatch(/Jul 18, 2026, 10:00/);
    });
  });

  describe('getLeadMissingFields', () => {
    it('returns empty array for fully complete jenex lead', () => {
      expect(getLeadMissingFields(makeCompleteLead())).toEqual([]);
    });

    it('flags missing rationale', () => {
      const missing = getLeadMissingFields(makeCompleteLead({ rationale: '' }));
      expect(missing).toContain('Rationale');
    });

    it('flags missing enrichment_report (Company overview)', () => {
      const missing = getLeadMissingFields(makeCompleteLead({ enrichment_report: undefined }));
      expect(missing).toContain('Company overview');
    });

    it('flags missing screenshot', () => {
      const missing = getLeadMissingFields(makeCompleteLead({ screenshot_url: undefined }));
      expect(missing).toContain('Screenshot');
    });

    it('flags missing email', () => {
      const missing = getLeadMissingFields(makeCompleteLead({ contact_email: undefined }));
      expect(missing).toContain('Email');
    });

    it('flags missing phone', () => {
      const missing = getLeadMissingFields(makeCompleteLead({ contact_phone: undefined }));
      expect(missing).toContain('Phone');
    });

    it('flags empty products_sold', () => {
      const missing = getLeadMissingFields(makeCompleteLead({ products_sold: [] }));
      expect(missing).toContain('Products/Services');
    });

    it('flags missing jenex evidence URLs', () => {
      const missing = getLeadMissingFields(makeCompleteLead({
        evidence: { kind: 'urls', urls: [] }
      }));
      expect(missing).toContain('Evidence URLs');
    });

    it('flags missing shoe-photo product images', () => {
      const missing = getLeadMissingFields(makeCompleteLead({
        campaignId: 'shoe-photo',
        evidence: { kind: 'photos', photos: [] }
      }));
      expect(missing).toContain('Product images');
    });

    it('flags wp-remediation lead with wrong evidence kind', () => {
      const missing = getLeadMissingFields(makeCompleteLead({
        campaignId: 'wp-remediation',
        evidence: { kind: 'urls', urls: ['x'] } as any
      }));
      expect(missing).toContain('Malware evidence');
    });

    it('returns multiple missing fields at once', () => {
      const missing = getLeadMissingFields(makeCompleteLead({
        contact_email: undefined,
        screenshot_url: undefined,
      }));
      expect(missing).toContain('Email');
      expect(missing).toContain('Screenshot');
      expect(missing.length).toBe(2);
    });
  });

  describe('isLeadComplete', () => {
    it('returns true for fully complete lead', () => {
      expect(isLeadComplete(makeCompleteLead())).toBe(true);
    });

    it('returns false when any field is missing', () => {
      expect(isLeadComplete(makeCompleteLead({ contact_email: undefined }))).toBe(false);
    });
  });
});
