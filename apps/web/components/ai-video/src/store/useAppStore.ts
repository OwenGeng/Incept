import { create } from 'zustand'
import type { SupportedLanguage } from '../i18n'

interface UserInfo {
  name: string
  role: string
}

interface AppState {
  siderCollapsed: boolean
  user: UserInfo
  language: SupportedLanguage
  setUser: (user: Partial<UserInfo>) => void
  setLanguage: (lang: SupportedLanguage) => void
  toggleSider: () => void
}

/** Reads only the scoped AI Video preference so the host app's locale is untouched. */
const getInitialLanguage = (): SupportedLanguage => {
  if (typeof window === 'undefined') return 'en-US'
  return window.localStorage.getItem('linglong_ai_video_language') === 'zh-CN' ? 'zh-CN' : 'en-US'
}

export const useAppStore = create<AppState>((set) => ({
  siderCollapsed: false,
  user: {
    name: 'Admin',
    role: 'System administrator',
  },
  language: getInitialLanguage(),
  setUser: (user) =>
    set((state) => ({
      user: {
        ...state.user,
        ...user,
      },
    })),
  setLanguage: (lang) => set(() => ({ language: lang })),
  toggleSider: () =>
    set((state) => ({
      siderCollapsed: !state.siderCollapsed,
    })),
}))
