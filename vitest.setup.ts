import '@testing-library/jest-dom'
import { vi } from 'vitest'

vi.mock('@/lib/i18n', () => ({
  useTranslation: () => ({
    locale: 'en',
    setLocale: vi.fn(),
    t: (key: string) => key,
  }),
  I18nProvider: ({ children }: { children: React.ReactNode }) => children,
}))
