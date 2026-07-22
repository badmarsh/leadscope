import { describe, it, expect } from 'vitest';
import { statusLabels, statusBadgeClasses, scoreColorClasses, formatDate, formatTimestamp } from '@/lib/status';

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
      // Use a fixed date
      expect(formatDate('2026-07-18')).toMatch(/Jul 18, 2026/);
    });

    it('formats timestamp properly', () => {
      expect(formatTimestamp('2026-07-18T10:00:00Z')).toMatch(/Jul 18, 2026, 10:00/);
    });
  });
});
