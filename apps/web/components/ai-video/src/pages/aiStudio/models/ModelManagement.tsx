import { useState } from 'react'
import { Layout, Tabs } from 'antd'
import { useTranslation } from 'react-i18next'
import ProvidersTab from './ProvidersTab'
import ModelsTab from './ModelsTab'
import SettingsTab from './SettingsTab'
import IntegrationsTab from './IntegrationsTab'

export default function ModelManagement() {
  const { i18n } = useTranslation()
  const copy = (english: string, chinese: string) => (i18n.language === 'zh-CN' ? chinese : english)
  const [activeTab, setActiveTab] = useState<string>('providers')

  return (
    <Layout className="h-full flex flex-col" style={{ minHeight: 0 }}>
      <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 bg-white space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-semibold text-gray-800">{copy('Model management', '模型管理')}</span>
        </div>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          size="small"
          items={[
            { key: 'providers', label: copy('Providers', '供应商') },
            { key: 'models', label: copy('Models', '模型') },
            { key: 'settings', label: copy('Settings', '设置') },
            { key: 'integrations', label: copy('Integrations & agents', '集成与 Agent') },
          ]}
        />
      </div>

      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {activeTab === 'providers' && <ProvidersTab />}
        {activeTab === 'models' && <ModelsTab />}
        {activeTab === 'settings' && <SettingsTab />}
        {activeTab === 'integrations' && <IntegrationsTab />}
      </div>
    </Layout>
  )
}
