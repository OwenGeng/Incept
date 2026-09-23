import { useEffect, useState } from 'react'
import { Button, Card, Tabs } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ActorsTab } from './tabs/ActorsTab'
import { ScenesTab } from './tabs/ScenesTab'
import { PropsTab } from './tabs/PropsTab'
import { CostumesTab } from './tabs/CostumesTab'

const TAB_PARAM = 'tab'
type AssetTabKey = 'actor' | 'scene' | 'prop' | 'costume'

function isValidTab(tab: string | null): tab is AssetTabKey {
  return tab === 'actor' || tab === 'scene' || tab === 'prop' || tab === 'costume'
}

const AssetManager = () => {
  const { i18n } = useTranslation()
  const copy = (english: string, chinese: string) => (i18n.language === 'zh-CN' ? chinese : english)
  const [searchParams, setSearchParams] = useSearchParams()
  const tabFromUrl = searchParams.get(TAB_PARAM)

  const [activeTab, setActiveTab] = useState<AssetTabKey>(() => (isValidTab(tabFromUrl) ? tabFromUrl : 'actor'))

  useEffect(() => {
    if (isValidTab(tabFromUrl)) {
      setActiveTab(tabFromUrl)
    } else if (tabFromUrl === null || tabFromUrl === '') {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set(TAB_PARAM, 'actor')
          return next
        },
        { replace: true },
      )
    }
  }, [tabFromUrl, setSearchParams])

  const setTabInUrl = (tab: AssetTabKey) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set(TAB_PARAM, tab)
        return next
      },
      { replace: true },
    )
  }

  return (
    <div className="asset-manager space-y-4">
      <div className="asset-manager-heading">
        <h1>{copy('Assets', '资产管理')}</h1>
        <Link to="/files">
          <Button type="primary" icon={<UploadOutlined />}>{copy('Upload files', '上传素材')}</Button>
        </Link>
      </div>
      <Card className="asset-manager-surface">
        <Tabs
          activeKey={activeTab}
          onChange={(k) => {
            if (isValidTab(k)) setTabInUrl(k)
          }}
          items={[
            { key: 'actor', label: copy('Actors', '演员'), children: <ActorsTab /> },
            { key: 'scene', label: copy('Scenes', '场景'), children: <ScenesTab /> },
            { key: 'prop', label: copy('Props', '道具'), children: <PropsTab /> },
            { key: 'costume', label: copy('Costumes', '服装'), children: <CostumesTab /> },
          ]}
        />
      </Card>
    </div>
  )
}

export default AssetManager
