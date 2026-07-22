import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { TopNav } from '../top-nav'

// Mock the i18n hook
vi.mock('@/lib/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    locale: 'en',
    setLocale: vi.fn(),
  }),
}))

describe('TopNav Component', () => {
  const defaultProps = {
    activeCampaign: 'jenex' as const,
    onCampaignChange: vi.fn(),
    darkMode: false,
    onToggleDarkMode: vi.fn(),
    onLogout: vi.fn(),
    onSettingsOpen: vi.fn(),
  }

  it('renders correctly', () => {
    render(<TopNav {...defaultProps} />)
    expect(screen.getByText('nav.title')).toBeInTheDocument()
  })

  it('calls onHelpOpen when Help icon is clicked', async () => {
    const onHelpOpen = vi.fn()
    render(<TopNav {...defaultProps} onHelpOpen={onHelpOpen} />)
    
    const helpButton = screen.getByLabelText('Help & Documentation')
    await userEvent.click(helpButton)
    
    expect(onHelpOpen).toHaveBeenCalledTimes(1)
  })

  it('calls onN8nOpen when N8n icon is clicked', async () => {
    const onN8nOpen = vi.fn()
    render(<TopNav {...defaultProps} onN8nOpen={onN8nOpen} />)
    
    const n8nButton = screen.getByLabelText('nav.n8n')
    await userEvent.click(n8nButton)
    
    expect(onN8nOpen).toHaveBeenCalledTimes(1)
  })

  it('calls onKbOpen when Knowledge Base icon is clicked', async () => {
    const onKbOpen = vi.fn()
    render(<TopNav {...defaultProps} onKbOpen={onKbOpen} />)
    
    const kbButton = screen.getByLabelText('Knowledge Base')
    await userEvent.click(kbButton)
    
    expect(onKbOpen).toHaveBeenCalledTimes(1)
  })

  it('calls onSettingsOpen when Settings icon is clicked', async () => {
    const onSettingsOpen = vi.fn()
    render(<TopNav {...defaultProps} onSettingsOpen={onSettingsOpen} />)
    
    const settingsButton = screen.getByLabelText('Campaign settings')
    await userEvent.click(settingsButton)
    
    expect(onSettingsOpen).toHaveBeenCalledTimes(1)
  })
})
