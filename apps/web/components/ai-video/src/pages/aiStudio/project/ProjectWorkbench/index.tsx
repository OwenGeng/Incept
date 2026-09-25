import React, { useCallback, useEffect, useState } from 'react'
import { Card, Button, Tabs, Space, Dropdown, Empty } from 'antd'
import type { MenuProps } from 'antd'
import {
  PlusOutlined,
  EllipsisOutlined,
  ArrowLeftOutlined,
  VideoCameraFilled,
  RobotOutlined,
} from '@ant-design/icons'
import { Link, useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { TAB_CONFIG, type TabKey, isTabKey, DEFAULT_TAB } from './constants'
import { DashboardTab } from './tabs/DashboardTab'
import { ChaptersTab } from './tabs/ChaptersTab'
import { ActorsTab } from './tabs/ActorsTab'
import { RolesTab } from './tabs/RolesTab'
import { ScenesTab } from './tabs/ScenesTab'
import { CostumesTab, PropsTab } from './tabs/PropsTab'
import { FilesTab } from './tabs/FilesTab'
import { EditTab } from './tabs/EditTab'
import { SettingsTab } from './tabs/SettingsTab'
import { ResearchTab } from './tabs/ResearchTab'
import { ProductionTab } from './tabs/ProductionTab'
import { ProductsTab } from './tabs/ProductsTab'
import { getChapterShotsPath, getChapterStudioPath, getProjectEditorPath } from './routes'
import { useProject, useChapters } from './hooks/useProjectData'
import { ensureHasShotsBeforeShooting } from './ensureHasShotsBeforeShooting'
import { getChapterPreparationState } from './chapterPreparation'
import { useAppStore } from '../../../../store/useAppStore'
import { CreativeAgentPanel } from './CreativeAgentPanel'
import { getProjectResearch, type ProjectResearch } from '../../../../services/projectResearch'

const TAB_PARAM = 'tab'
const CREATE_PARAM = 'create'
const EDIT_PARAM = 'edit'

const ProjectWorkbench: React.FC = () => {
  const language = useAppStore((state) => state.language)
  const copy = (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english)
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabFromUrl = searchParams.get(TAB_PARAM)
  const resolvedTab: TabKey =
    tabFromUrl !== null && isTabKey(tabFromUrl) ? tabFromUrl : DEFAULT_TAB

  const { project, loading: projectLoading } = useProject(projectId)
  const { chapters } = useChapters(projectId)
  const [activeTab, setActiveTab] = useState<TabKey>(() => resolvedTab)
  const [research, setResearch] = useState<ProjectResearch | null>(null)
  const [researchChecked, setResearchChecked] = useState(false)
  const [agentOpen, setAgentOpen] = useState(false)

  useEffect(() => {
    if (!projectId) return
    setResearchChecked(false)
    getProjectResearch(projectId)
      .then(setResearch)
      .catch(() => setResearch(null))
      .finally(() => setResearchChecked(true))
  }, [projectId])

  const productionUnlocked = research?.entry_mode === 'preset' || research?.status === 'approved'

  const chaptersByIndex = [...chapters].sort((a, b) => a.index - b.index)

  const recommendedChapter = (() => {
    const findByState = (key: ReturnType<typeof getChapterPreparationState>['key']) =>
      chaptersByIndex.find((chapter) => getChapterPreparationState(chapter).key === key)
    return (
      findByState('edit_raw') ??
      findByState('extract_shots') ??
      findByState('prepare_shots') ??
      findByState('shoot') ??
      chaptersByIndex[0] ??
      null
    )
  })()

  const primaryCta = (() => {
    if (!projectId) {
      return {
        label: copy('Create first chapter', '创建第一章'),
        hint: copy('Create a chapter before starting storyboard preparation.', '先创建章节，再进入分镜准备流程'),
        icon: <PlusOutlined />,
        onClick: () => {},
      }
    }
    if (researchChecked && !productionUnlocked) {
      return {
        label: copy('Complete research brief', '完成研究简报'),
        hint: copy('Approve a creative direction before script, storyboard, or generation work.', '批准创意方向后，才能进入脚本、分镜和生成。'),
        icon: <PlusOutlined />,
        onClick: () => setTabInUrl('research'),
      }
    }
    if (!recommendedChapter) {
      return {
        label: copy('Create first chapter', '创建第一章'),
        hint: copy('Create a chapter before starting storyboard preparation.', '先创建章节，再进入分镜准备流程'),
        icon: <PlusOutlined />,
        onClick: () => {
          setTabInUrl('chapters')
          setSearchParams(
            (prev) => {
              const next = new URLSearchParams(prev)
              next.set(CREATE_PARAM, '1')
              return next
            },
            { replace: true }
          )
        },
      }
    }
    const state = getChapterPreparationState(recommendedChapter)
    const chapterLabel = copy(`Chapter ${recommendedChapter.index}`, `第${recommendedChapter.index}章`)
    if (state.key === 'edit_raw') {
      return {
        label: copy(`Edit ${chapterLabel} source`, `编辑${chapterLabel}原文`),
        hint: copy(`${chapterLabel} has no source text yet. Add it before continuing.`, `${chapterLabel}还没有原文内容，建议先补章节原文`),
        icon: state.primaryIcon,
        onClick: () => {
          setTabInUrl('chapters')
          setSearchParams(
            (prev) => {
              const next = new URLSearchParams(prev)
              next.set(TAB_PARAM, 'chapters')
              next.set(EDIT_PARAM, recommendedChapter.id)
              return next
            },
            { replace: true }
          )
        },
      }
    }
    if (state.key === 'extract_shots') {
      return {
        label: copy(`Extract ${chapterLabel} storyboards`, `提取${chapterLabel}分镜`),
        hint: copy(`${chapterLabel} has source text. Extract storyboards next.`, `${chapterLabel}已有原文，下一步更适合先提取分镜`),
        icon: state.primaryIcon,
        onClick: () => navigate(getChapterShotsPath(projectId, recommendedChapter.id)),
      }
    }
    if (state.key === 'prepare_shots') {
      return {
        label: copy(`Open ${chapterLabel} storyboard studio`, `进入${chapterLabel}分镜工作室`),
        hint: copy(`${chapterLabel} has storyboards. Continue preparing shots.`, `${chapterLabel}已有分镜，建议继续补齐镜头准备`),
        icon: state.primaryIcon,
        onClick: () => navigate(getChapterStudioPath(projectId, recommendedChapter.id)),
      }
    }
    return {
      label: copy(`Start ${chapterLabel} production`, `进入${chapterLabel}拍摄`),
      hint: copy(`${chapterLabel} is ready to continue production.`, `${chapterLabel}已具备分镜，可继续进入拍摄流程`),
      icon: state.primaryIcon,
      onClick: () =>
        ensureHasShotsBeforeShooting({
          projectId,
          chapterId: recommendedChapter.id,
          storyboardCount: recommendedChapter.storyboardCount,
          navigate,
        }),
    }
  })()

  // 与 URL 中的 tab 同步：URL 变化时更新 activeTab；初次或无效 tab 时写回 URL
  useEffect(() => {
    if (tabFromUrl !== null && isTabKey(tabFromUrl)) {
      setActiveTab(tabFromUrl)
    } else if (tabFromUrl === null || tabFromUrl === '') {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set(TAB_PARAM, DEFAULT_TAB)
          return next
        },
        { replace: true }
      )
    }
  }, [tabFromUrl, setSearchParams])

  const setTabInUrl = useCallback((tab: TabKey) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.set(TAB_PARAM, tab)
        return next
      },
      { replace: true }
    )
  }, [setSearchParams])

  useEffect(() => {
    if (researchChecked && !productionUnlocked && activeTab !== 'research') {
      setTabInUrl('research')
    }
  }, [activeTab, productionUnlocked, researchChecked, setTabInUrl])

  const moreMenuItems: MenuProps['items'] = [
    { key: 'newActor', label: copy('Link actors', '关联演员'), onClick: () => setTabInUrl('actors') },
    { key: 'newRole', label: copy('New character', '新建角色'), onClick: () => setTabInUrl('roles') },
    { key: 'upload', label: copy('Upload assets', '上传素材'), onClick: () => navigate('/assets') },
    { key: 'newScene', label: copy('New scene', '新建场景'), onClick: () => setTabInUrl('scenes') },
    { key: 'newProp', label: copy('New prop', '新建道具'), onClick: () => setTabInUrl('props') },
    { key: 'newCostume', label: copy('New costume', '新建服装'), onClick: () => setTabInUrl('costumes') },
  ]

  if (!project && !projectLoading) {
    return (
      <Card>
        <Empty description={copy('Project not found', '项目不存在')} />
        <Link to="/projects">
          <Button type="link" icon={<ArrowLeftOutlined />}>
            {copy('Back to projects', '返回项目列表')}
          </Button>
        </Link>
      </Card>
    )
  }

  return (
    <div className="h-full min-h-0 flex flex-col">
      <div
        className="project-workbench-header sticky top-0 z-20"
        style={{ margin: -5, marginBottom: 0, padding: '16px 24px' }}
      >
        <div className="project-workbench-header-content flex flex-wrap items-center justify-between gap-3 pt-2">
          <Tabs
            activeKey={activeTab}
            onChange={(k) => {
              const next = k as TabKey
              setTabInUrl(next === 'research' || productionUnlocked ? next : 'research')
            }}
            size="middle"
            className="project-workbench-tabs flex-1 min-w-0"
            items={TAB_CONFIG.map(({ key, icon }) => ({
              key,
              disabled: key !== 'research' && researchChecked && !productionUnlocked,
              label: (
                <span className="flex items-center gap-1.5">
                  {icon}
                  {copy(
                    { research: 'Research', production: 'Production', products: 'Products', dashboard: 'Dashboard', chapters: 'Chapters', actors: 'Actors', roles: 'Characters', scenes: 'Scenes', props: 'Props', costumes: 'Costumes', files: 'Files', edit: 'Edit', settings: 'Settings' }[key],
                    TAB_CONFIG.find((item) => item.key === key)?.label ?? key,
                  )}
                </span>
              ),
            }))}
          />
          <Space size="small" wrap className="shrink-0">
            <Button icon={<RobotOutlined />} onClick={() => setAgentOpen(true)}>
              {copy('Creative agent', '创意 Agent')}
            </Button>
            <Button
              type="primary"
              icon={primaryCta.icon}
              onClick={primaryCta.onClick}
            >
              {primaryCta.label}
            </Button>
            <Button disabled={!productionUnlocked} icon={<VideoCameraFilled />} onClick={() => projectId && navigate(getProjectEditorPath(projectId))}>
              {copy('Open post-production', '进入后期剪辑')}
            </Button>
            <Dropdown disabled={!productionUnlocked} menu={{ items: moreMenuItems }} placement="bottomRight">
              <Button icon={<EllipsisOutlined />}>{copy('More', '更多')}</Button>
            </Dropdown>
          </Space>
        </div>
        <div className="mt-2 text-xs text-gray-500">
          {primaryCta.hint}
        </div>
      </div>

      <div
        className="pt-4 animate-fadeIn flex-1 min-h-0 overflow-hidden"
        style={{ animation: 'fadeIn 0.25s ease-out' }}
      >
        {activeTab === 'research' && <ResearchTab onResearchChange={setResearch} />}

        {activeTab === 'production' && productionUnlocked && <ProductionTab />}

        {activeTab === 'products' && productionUnlocked && <ProductsTab />}

        {activeTab === 'dashboard' && productionUnlocked && <DashboardTab onSelectTab={setTabInUrl} />}

        {activeTab === 'chapters' && productionUnlocked && <ChaptersTab />}

        {activeTab === 'actors' && productionUnlocked && <ActorsTab />}
        {activeTab === 'roles' && productionUnlocked && <RolesTab />}
        {activeTab === 'scenes' && productionUnlocked && <ScenesTab />}
        {activeTab === 'props' && productionUnlocked && <PropsTab />}
        {activeTab === 'costumes' && productionUnlocked && <CostumesTab />}
        {activeTab === 'files' && productionUnlocked && <FilesTab />}
        {activeTab === 'edit' && productionUnlocked && <EditTab />}
        {activeTab === 'settings' && productionUnlocked && <SettingsTab />}
      </div>
      {projectId ? <CreativeAgentPanel projectId={projectId} open={agentOpen} onClose={() => setAgentOpen(false)} /> : null}
    </div>
  )
}

export default ProjectWorkbench
