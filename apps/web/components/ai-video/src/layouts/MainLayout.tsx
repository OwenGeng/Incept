import React, { useMemo } from 'react'
import {
  ApiOutlined,
  FileTextOutlined,
  FolderOutlined,
  PictureOutlined,
  LeftOutlined,
  RightOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Select } from 'antd'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAppStore } from '../store/useAppStore'
import { TaskCenter } from '../pages/aiStudio/components/TaskCenter'
import { TaskRuntimeProvider } from '../pages/aiStudio/components/TaskRuntimeProvider'

type NavigationItem = {
  key: string
  href: string
  labelKey: string
  icon: React.ReactNode
}

const navigation: NavigationItem[] = [
  { key: 'projects', href: '/projects', labelKey: 'nav.projects', icon: <FolderOutlined /> },
  { key: 'assets', href: '/assets', labelKey: 'nav.assets', icon: <PictureOutlined /> },
  { key: 'prompts', href: '/prompts', labelKey: 'nav.prompts', icon: <FileTextOutlined /> },
  { key: 'models', href: '/models', labelKey: 'nav.models', icon: <ApiOutlined /> },
  { key: 'settings', href: '/settings', labelKey: 'nav.settings', icon: <SettingOutlined /> },
]

const MainLayout: React.FC = () => {
  const { t, i18n } = useTranslation('layout')
  const location = useLocation()
  const collapsed = useAppStore((state) => state.siderCollapsed)
  const toggleCollapsed = useAppStore((state) => state.toggleSider)
  const user = useAppStore((state) => state.user)
  const language = useAppStore((state) => state.language)
  const setLanguage = useAppStore((state) => state.setLanguage)

  const selectedKey = useMemo(() => {
    if (location.pathname === '/projects' || location.pathname.startsWith('/projects/')) return 'projects'
    if (location.pathname.startsWith('/assets')) return 'assets'
    if (location.pathname.startsWith('/files')) return 'assets'
    if (location.pathname.startsWith('/prompts')) return 'prompts'
    if (location.pathname.startsWith('/models')) return 'models'
    if (location.pathname.startsWith('/settings')) return 'settings'
    return undefined
  }, [location.pathname])

  const pageTitle = useMemo(() => {
    const currentItem = navigation.find((item) => item.key === selectedKey)
    return currentItem ? t(currentItem.labelKey) : t('product')
  }, [selectedKey, t])

  /** Keeps the application language and the browser locale in sync. */
  const handleLanguageChange = (nextLanguage: 'en-US' | 'zh-CN') => {
    setLanguage(nextLanguage)
    void i18n.changeLanguage(nextLanguage)
    window.localStorage.setItem('linglong_ai_video_language', nextLanguage)
    document.documentElement.lang = nextLanguage === 'en-US' ? 'en' : 'zh-CN'
  }

  return (
    <div className="linglong-ai-video-shell">
      <aside className={`linglong-ai-video-sidebar ${collapsed ? 'is-collapsed' : ''}`}>
        <button
          type="button"
          className="linglong-ai-video-sidebar-toggle"
          onClick={toggleCollapsed}
          aria-label={collapsed ? t('expandSidebar') : t('collapseSidebar')}
          title={collapsed ? t('expandSidebar') : t('collapseSidebar')}
        >
          {collapsed ? <RightOutlined /> : <LeftOutlined />}
        </button>
        <Link to="/projects" className="linglong-ai-video-brand" aria-label="Linglong Lab AI Video">
          <img
            src="/ai-video/linglong-lab-logo.png"
            alt="Linglong Lab"
            className="linglong-ai-video-brand-logo"
          />
          {!collapsed && (
            <span className="linglong-ai-video-brand-copy">
              <strong>{t('title')}</strong>
              <small>{t('subtitle')}</small>
            </span>
          )}
        </Link>

        <nav className="linglong-ai-video-nav" aria-label={t('navLabel')}>
          {navigation.map((item) => (
            <Link
              key={item.key}
              to={item.href}
              className={`linglong-ai-video-nav-link ${selectedKey === item.key ? 'is-active' : ''}`}
              title={collapsed ? t(item.labelKey) : undefined}
              aria-label={t(item.labelKey)}
              aria-current={selectedKey === item.key ? 'page' : undefined}
            >
              <span className="linglong-ai-video-nav-icon" aria-hidden="true">{item.icon}</span>
              {!collapsed && <span>{t(item.labelKey)}</span>}
            </Link>
          ))}
        </nav>

      </aside>

      <div className="linglong-ai-video-workspace">
        <header className="linglong-ai-video-header">
          <div className="linglong-ai-video-header-left">
            <div className="linglong-ai-video-heading">
              <span>{t('product')}</span>
              <span className="linglong-ai-video-heading-separator">/</span>
              <strong>{pageTitle}</strong>
            </div>
          </div>

          <div className="linglong-ai-video-header-actions">
            <div className="linglong-ai-video-language">
              <Select
                value={language}
                onChange={(nextLanguage) => handleLanguageChange(nextLanguage as 'en-US' | 'zh-CN')}
                aria-label={t('languageLabel')}
                popupClassName="linglong-language-menu"
                options={[
                  { value: 'en-US', label: t('lang.en') },
                  { value: 'zh-CN', label: t('lang.zh') },
                ]}
              />
            </div>
            <Link to="/settings" className="linglong-ai-video-user" aria-label={t('user.accountSettings')}>
              <span className="linglong-ai-video-avatar" aria-hidden="true"><UserOutlined /></span>
              <span className="linglong-ai-video-user-copy">
                <strong>{user.name}</strong>
                <span>{t('user.role')}</span>
              </span>
            </Link>
          </div>
        </header>

        <TaskRuntimeProvider>
          <main className="linglong-ai-video-content">
            <Outlet />
          </main>
          <TaskCenter />
        </TaskRuntimeProvider>
      </div>
    </div>
  )
}

export default MainLayout
