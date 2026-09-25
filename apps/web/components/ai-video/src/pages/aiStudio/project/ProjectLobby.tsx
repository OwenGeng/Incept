import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Card,
  Input,
  Button,
  Progress,
  Statistic,
  Row,
  Col,
  Modal,
  Form,
  Select,
  App as AntApp,
  Upload,
  Space,
  Tag,
  Popconfirm,
  Empty,
  Result,
} from 'antd'
import type { UploadFile } from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  EnterOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  BarsOutlined,
  SearchOutlined,
  InboxOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { useAppStore } from '../../../store/useAppStore'
import { chapters as mockChapters, projects as mockProjects, type Project } from '../../../mocks/data'
import { StudioChaptersService, StudioProjectsService } from '../../../services/generated'
import type { ChapterRead, ProjectRead, ProjectStyle } from '../../../services/generated'
import { getChapterPreparationState } from './ProjectWorkbench/chapterPreparation'
import { ensureHasShotsBeforeShooting } from './ProjectWorkbench/ensureHasShotsBeforeShooting'
import { getChapterShotsPath, getChapterStudioPath } from './ProjectWorkbench/routes'
import { loadProjectFlowStatsForChapters, type ProjectFlowStats } from './ProjectWorkbench/projectFlowStats'
import { isAiVideoMockEnabled } from '../../../runtime'
import { saveProjectResearch, uploadResearchFile } from '../../../services/projectResearch'

type ViewMode = 'grid' | 'compact' | 'large'
type FilterTab = 'all' | 'editRaw' | 'extractShots' | 'prepareShots' | 'generating' | 'ready'
type SortKey = 'updatedAt' | 'name' | 'createdAt' | 'chapters'
type ChapterPreparationInput = Parameters<typeof getChapterPreparationState>[0]
type ProjectStageSummary = {
  key: ReturnType<typeof getChapterPreparationState>['key'] | 'create_first_chapter'
  stageText: string
  stageColor: string
  nextActionLabel: string
  nextActionHint: string
  chapterId?: string
  storyboardCount?: number
}
type ProjectFlowStatsMap = Record<string, ProjectFlowStats>
type ProjectView = Project & {
  visualStyle?: string
  defaultVideoRatio?: string | null
}

const ProjectLobby: React.FC = () => {
  const { message: messageApi } = AntApp.useApp()
  const navigate = useNavigate()
  const language = useAppStore((state) => state.language)
  const copy = useCallback(
    (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english),
    [language],
  )
  const [projects, setProjects] = useState<ProjectView[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [search, setSearch] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [filterTab, setFilterTab] = useState<FilterTab>('all')
  const [sortKey, setSortKey] = useState<SortKey>('updatedAt')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [multiSelectMode, setMultiSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [creatingProject, setCreatingProject] = useState(false)
  const [updatingProject, setUpdatingProject] = useState(false)
  const [editingProject, setEditingProject] = useState<ProjectView | null>(null)
  const [createProductFile, setCreateProductFile] = useState<File | null>(null)
  const [projectStageMap, setProjectStageMap] = useState<Record<string, ProjectStageSummary>>({})
  const [projectFlowStatsMap, setProjectFlowStatsMap] = useState<ProjectFlowStatsMap>({})
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()

  const advertiserVerticalOptions = [
    { value: 'Gaming', label: copy('Gaming', '游戏') },
    { value: 'Social & Community', label: copy('Social & Community', '社交与社区') },
    { value: 'E-commerce / DTC', label: copy('E-commerce / DTC', '电商 / DTC') },
    { value: 'Utility / Productivity', label: copy('Utility / Productivity', '工具 / 效率') },
    { value: 'Other app', label: copy('Other app', '其他应用') },
    { value: 'Brand', label: copy('Brand', '品牌') },
  ]
  const deliveryChannelOptions = [
    { value: 'Mobile in-app', label: copy('Mobile in-app', '移动端应用内') },
    { value: 'CTV', label: copy('CTV', '联网电视（CTV）') },
    { value: 'Cross-channel', label: copy('Cross-channel', '跨渠道') },
  ]

  const useMock = isAiVideoMockEnabled

  const toUIProject = (p: ProjectRead): ProjectView => {
    const stats = (p.stats ?? {}) as Record<string, unknown>
    const getNum = (key: string) => {
      const v = stats[key]
      return typeof v === 'number' && Number.isFinite(v) ? v : 0
    }

    const updatedAt =
      (typeof stats.updated_at === 'string' && stats.updated_at) ||
      (typeof stats.updatedAt === 'string' && stats.updatedAt) ||
      new Date().toISOString()

    return {
      id: p.id,
      name: p.name,
      description: p.description ?? '',
      style: (p.style as Project['style']) ?? '现实主义',
      seed: p.seed ?? 0,
      unifyStyle: p.unify_style ?? true,
      progress: p.progress ?? 0,
      stats: {
        chapters: getNum('chapters'),
        roles: getNum('roles'),
        scenes: getNum('scenes'),
        props: getNum('props'),
      },
      updatedAt,
      visualStyle: p.visual_style ?? '现实',
      defaultVideoRatio: p.default_video_ratio ?? null,
    }
  }

  const newProjectId = () => {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID()
    }
    return `p_${Date.now()}_${Math.random().toString(16).slice(2)}`
  }

  const load = async () => {
    setLoading(true)
    setLoadError(false)
    try {
      if (useMock) {
        setProjects(mockProjects)
      } else {
        const res = await StudioProjectsService.listProjectsApiV1StudioProjectsGet({
          page: 1,
          pageSize: 10,
        })
        const items = res.data?.items ?? []
        setProjects(items.map(toUIProject))
      }
    } catch {
      setProjects(useMock ? mockProjects : [])
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const getProjectStatus = (p: ProjectView): 'draft' | 'inProgress' | 'completed' => {
    if (p.progress >= 90) return 'completed'
    if (p.progress <= 5) return 'draft'
    return 'inProgress'
  }

  useEffect(() => {
    const list = Array.isArray(projects) ? projects : []
    if (!list.length) {
      setProjectStageMap({})
      setProjectFlowStatsMap({})
      return
    }

    const summarizeProjectChapters = (chapters: ChapterPreparationInput[]): ProjectStageSummary => {
      const chaptersByIndex = [...chapters].sort((a, b) => a.index - b.index)
      if (!chaptersByIndex.length) {
        return {
          key: 'create_first_chapter',
          stageText: copy('Needs first chapter', '待创建章节'),
          stageColor: 'default',
          nextActionLabel: copy('Create first chapter', '创建第一章'),
          nextActionHint: copy('No chapters yet. Create the first chapter to start the workflow.', '项目还没有章节，建议先创建第一章'),
        }
      }
      const findByState = (key: ReturnType<typeof getChapterPreparationState>['key']) =>
        chaptersByIndex.find((chapter) => getChapterPreparationState(chapter).key === key)
      const chapter =
        findByState('edit_raw') ??
        findByState('extract_shots') ??
        findByState('prepare_shots') ??
        findByState('shoot') ??
        chaptersByIndex[0]
      const state = getChapterPreparationState(chapter)
      const stageCopy = {
        edit_raw: {
          text: copy('Needs source', state.text),
          hint: copy('Add the chapter source before starting shot work.', state.hint),
          action: copy('Edit source', state.primaryAction),
        },
        extract_shots: {
          text: copy('Needs shot extraction', state.text),
          hint: copy('The source is ready. Extract shots next.', state.hint),
          action: copy('Extract shots', state.primaryAction),
        },
        prepare_shots: {
          text: copy('Needs shot prep', state.text),
          hint: copy('Shots are ready. Complete shot preparation in the studio.', state.hint),
          action: copy('Open shot studio', state.primaryAction),
        },
        shoot: {
          text: copy('Ready for shooting', state.text),
          hint: copy('This chapter is ready to continue into shooting.', state.hint),
          action: copy('Start shooting', state.primaryAction),
        },
      }[state.key]
      return {
        key: state.key,
        stageText: stageCopy.text,
        stageColor: state.color,
        nextActionLabel: stageCopy.action,
        nextActionHint: copy(`Chapter ${chapter.index} · ${stageCopy.hint}`, `第${chapter.index}章 · ${stageCopy.hint}`),
        chapterId: chapter.id,
        storyboardCount: chapter.storyboardCount,
      }
    }

    const loadSummaries = async () => {
      try {
        if (useMock) {
          const chapterGroups = Object.fromEntries(
            list.map((project) => [
              project.id,
              mockChapters
                .filter((chapter) => chapter.projectId === project.id)
                .map((chapter) => ({
                  id: chapter.id,
                  projectId: chapter.projectId,
                  index: chapter.index,
                  title: chapter.title,
                  summary: chapter.summary ?? '',
                  rawText: chapter.summary ?? '',
                  storyboardCount: chapter.storyboardCount,
                  status: chapter.status,
                  updatedAt: chapter.updatedAt,
                })),
            ]),
          )
          setProjectStageMap(
            Object.fromEntries(
              Object.entries(chapterGroups).map(([projectId, chapters]) => [
                projectId,
                summarizeProjectChapters(chapters),
              ]),
            ),
          )
          const flowStatsEntries = await Promise.all(
            Object.entries(chapterGroups).map(async ([projectId, chapters]) => [
              projectId,
              await loadProjectFlowStatsForChapters(chapters),
            ] as const),
          )
          setProjectFlowStatsMap(Object.fromEntries(flowStatsEntries))
          return
        }

        const chapterResponses = await Promise.all(
          list.map(async (project) => {
            const res = await StudioChaptersService.listChaptersApiV1StudioChaptersGet({
              projectId: project.id,
              page: 1,
              pageSize: 100,
            })
            const items: ChapterRead[] = res.data?.items ?? []
            return [
              project.id,
              summarizeProjectChapters(
                items.map((chapter) => ({
                  id: chapter.id,
                  projectId: chapter.project_id,
                  index: chapter.index,
                  title: chapter.title,
                  summary: chapter.summary ?? '',
                  rawText: chapter.raw_text ?? '',
                  storyboardCount: chapter.shot_count ?? chapter.storyboard_count ?? 0,
                  status: chapter.status ?? 'draft',
                  updatedAt: new Date().toISOString(),
                })),
              ),
              items.map((chapter) => ({
                id: chapter.id,
                projectId: chapter.project_id,
                index: chapter.index,
                title: chapter.title,
                summary: chapter.summary ?? '',
                rawText: chapter.raw_text ?? '',
                storyboardCount: chapter.shot_count ?? chapter.storyboard_count ?? 0,
                status: chapter.status ?? 'draft',
                updatedAt: new Date().toISOString(),
              })),
            ] as const
          }),
        )
        setProjectStageMap(
          Object.fromEntries(chapterResponses.map(([projectId, summary]) => [projectId, summary])),
        )
        const flowStatsEntries = await Promise.all(
          chapterResponses.map(async ([projectId, _summary, chapters]) => [
            projectId,
            await loadProjectFlowStatsForChapters(chapters),
          ] as const),
        )
        setProjectFlowStatsMap(Object.fromEntries(flowStatsEntries))
      } catch {
        setProjectStageMap({})
        setProjectFlowStatsMap({})
      }
    }

    void loadSummaries()
  }, [copy, projects, useMock])

  const filteredSorted = useMemo(() => {
    const list = Array.isArray(projects) ? projects : []
    const keyword = search.trim().toLowerCase()

    let next = list.filter((p) => {
      if (keyword) {
        const inText =
          p.name.toLowerCase().includes(keyword) ||
          p.description.toLowerCase().includes(keyword)
        if (!inText) return false
      }

      if (filterTab === 'all') return true
      const stage = projectStageMap[p.id]
      const flowStats = projectFlowStatsMap[p.id]
      if (filterTab === 'editRaw') return stage?.key === 'edit_raw' || stage?.key === 'create_first_chapter'
      if (filterTab === 'extractShots') return stage?.key === 'extract_shots'
      if (filterTab === 'prepareShots') return stage?.key === 'prepare_shots'
      if (filterTab === 'generating') return (flowStats?.generatingShots ?? 0) > 0
      if (filterTab === 'ready') return (flowStats?.readyShots ?? 0) > 0
      return true
    })

    next.sort((a, b) => {
      let av: string | number = ''
      let bv: string | number = ''
      if (sortKey === 'name') {
        av = a.name
        bv = b.name
      } else if (sortKey === 'chapters') {
        av = a.stats.chapters
        bv = b.stats.chapters
      } else if (sortKey === 'createdAt') {
        av = a.id
        bv = b.id
      } else {
        av = a.updatedAt
        bv = b.updatedAt
      }

      if (typeof av === 'number' && typeof bv === 'number') {
        return sortOrder === 'asc' ? av - bv : bv - av
      }
      const res = String(av).localeCompare(String(bv))
      return sortOrder === 'asc' ? res : -res
    })

    return next
  }, [projects, search, filterTab, sortKey, sortOrder, projectStageMap, projectFlowStatsMap])

  const handleSelectProject = (id: string) => {
    setSelectedProjectId(id)
  }

  const handleToggleSelect = (id: string, checked: boolean) => {
    setSelectedIds((prev) =>
      checked ? Array.from(new Set([...prev, id])) : prev.filter((x) => x !== id)
    )
  }

  const handleBatchDelete = async () => {
    if (!selectedIds.length) return
    try {
      await Promise.all(
        selectedIds.map((id) =>
          StudioProjectsService.deleteProjectApiV1StudioProjectsProjectIdDelete({ projectId: id }),
        ),
      )
      setProjects((prev) =>
        Array.isArray(prev) ? prev.filter((p) => !selectedIds.includes(p.id)) : prev
      )
      setSelectedIds([])
      messageApi.success(copy('Selected projects deleted', '已批量删除选中项目'))
    } catch {
      messageApi.error(copy('Could not delete selected projects', '批量删除失败'))
    }
  }

  const handleOpenCreate = () => {
    form.resetFields()
    setCreateProductFile(null)
    setCreateModalOpen(true)
  }

  const handleCreateSubmit = async (values: {
    name: string
    description?: string
    advertiser_vertical: string
    delivery_channel: string
    product_url?: string
    market?: string
  }) => {
    if (creatingProject) return
    if (!values.product_url?.trim() && !createProductFile) {
      messageApi.error(copy('Add a product webpage or upload a product asset.', '请填写产品网页或上传产品素材。'))
      return
    }
    setCreatingProject(true)
    try {
      const createdId = newProjectId()
      const res = await StudioProjectsService.createProjectApiV1StudioProjectsPost({
        requestBody: {
          id: createdId,
          name: values.name,
          description: values.description ?? '',
          style: '广告通用' as ProjectStyle,
          visual_style: '现实',
          seed: 0,
          unify_style: true,
          default_video_ratio: null,
          progress: 0,
        },
      })
      const created = res.data
      if (!created) throw new Error('empty project')
      const productAssetIds = createProductFile
        ? [await uploadResearchFile(created.id, createProductFile)]
        : []
      await saveProjectResearch(created.id, {
        entry_mode: 'research',
        status: 'draft',
        brief: {
          advertiser_vertical: values.advertiser_vertical,
          delivery_channel: values.delivery_channel,
          product_name: values.name,
          product_description: values.description ?? '',
          product_url: values.product_url?.trim() || null,
          product_asset_file_ids: productAssetIds,
          market: values.market?.trim() || null,
          target_audience: '',
          conversion_goal: '',
          key_messages: [],
          cta: '',
          legal: '',
          prohibited_claims: [],
          claim_evidence: [],
          aspect_ratios: [],
          language: 'en',
          required_overlays: [],
          brand_colors: [],
          brand_font_family: 'Arial',
          safe_area_percent: 5,
        },
        sources: [
          ...(values.product_url?.trim()
            ? [{ id: `source_${created.id}_url`, type: 'product_page' as const, title: values.name, url: values.product_url.trim(), notes: '', rights_confirmed: true }]
            : []),
          ...(productAssetIds.length
            ? [{ id: `source_${created.id}_asset`, type: 'product_asset' as const, title: createProductFile?.name ?? 'Product asset', file_id: productAssetIds[0], notes: '', rights_confirmed: true }]
            : []),
        ],
        findings: [],
        creative_directions: [],
        approved_direction_id: null,
      })
      const ui = toUIProject(created)
      messageApi.success(copy('Project created', '项目创建成功'))
      setCreateModalOpen(false)
      setProjects((prev) => (Array.isArray(prev) ? [...prev, ui] : [ui]))
      navigate(`/projects/${ui.id}?tab=research`)
    } catch {
      messageApi.error(copy('Could not create project', '创建失败'))
    } finally {
      setCreatingProject(false)
    }
  }

  const handleOpenEdit = (e: React.MouseEvent, p: ProjectView) => {
    e.stopPropagation()
    setEditingProject(p)
    editForm.setFieldsValue({
      name: p.name,
      description: p.description,
    })
    setEditModalOpen(true)
  }

  const handleEditSubmit = async (values: {
    name: string
    description?: string
  }) => {
    if (!editingProject) return
    if (updatingProject) return
    setUpdatingProject(true)
    try {
      const res = await StudioProjectsService.updateProjectApiV1StudioProjectsProjectIdPatch({
        projectId: editingProject.id,
        requestBody: {
          name: values.name,
          description: values.description ?? '',
        },
      })
      const updated = res.data
      if (!updated) throw new Error('empty project')
      const ui = toUIProject(updated)
      messageApi.success(copy('Project updated', '项目已更新'))
      setEditModalOpen(false)
      setEditingProject(null)
      setProjects((prev) =>
        Array.isArray(prev) ? prev.map((x) => (x.id === ui.id ? ui : x)) : prev
      )
    } catch {
      messageApi.error(copy('Could not update project', '更新失败'))
    } finally {
      setUpdatingProject(false)
    }
  }

  const handleDelete = async (projectId: string) => {
    try {
      await StudioProjectsService.deleteProjectApiV1StudioProjectsProjectIdDelete({ projectId })
      messageApi.success(copy('Project deleted', '已删除'))
      setProjects((prev) => (Array.isArray(prev) ? prev.filter((p) => p.id !== projectId) : []))
    } catch {
      messageApi.error(copy('Could not delete project', '删除失败'))
    }
  }

  const renderStatusTag = (p: ProjectView) => {
    const status = getProjectStatus(p)
    if (status === 'completed') return <Tag color="green" className="mr-0 text-[11px] leading-4">{copy('Completed', '已完成')}</Tag>
    if (status === 'draft') return <Tag color="default" className="mr-0 text-[11px] leading-4">{copy('Draft', '草稿')}</Tag>
    return <Tag color="orange" className="mr-0 text-[11px] leading-4">{copy('In progress', '进行中')}</Tag>
  }

  const handlePrimaryAction = (project: ProjectView, stageSummary?: ProjectStageSummary) => {
    if (!stageSummary) {
      navigate(`/projects/${project.id}`)
      return
    }
    if (stageSummary.key === 'create_first_chapter') {
      navigate(`/projects/${project.id}?tab=chapters&create=1`)
      return
    }
    if (!stageSummary.chapterId) {
      navigate(`/projects/${project.id}`)
      return
    }
    if (stageSummary.key === 'edit_raw') {
      navigate(`/projects/${project.id}?tab=chapters&edit=${stageSummary.chapterId}`)
      return
    }
    if (stageSummary.key === 'extract_shots') {
      navigate(getChapterShotsPath(project.id, stageSummary.chapterId))
      return
    }
    if (stageSummary.key === 'prepare_shots') {
      navigate(getChapterStudioPath(project.id, stageSummary.chapterId))
      return
    }
    void ensureHasShotsBeforeShooting({
      projectId: project.id,
      chapterId: stageSummary.chapterId,
      storyboardCount: stageSummary.storyboardCount,
      navigate,
    })
  }

  const selectedProject = filteredSorted.find((p) => p.id === selectedProjectId) ?? filteredSorted[0]

  const renderCard = (p: ProjectView) => {
    const status = getProjectStatus(p)
    const stageSummary = projectStageMap[p.id]
    const flowStats = projectFlowStatsMap[p.id]
    const isCompact = viewMode === 'compact'
    const isLarge = viewMode === 'large'
    const mainActionLabel = stageSummary?.nextActionLabel ?? (status === 'completed' ? copy('Continue editing', '继续剪辑') : p.progress > 0 ? copy('Continue shooting', '继续拍摄') : copy('Open project', '进入项目'))

    const isChecked = selectedIds.includes(p.id)

    return (
      <Card
        key={p.id}
        hoverable
        loading={loading}
        size="small"
        className="project-card h-full cursor-pointer"
        styles={{ body: { padding: '10px' } }}
        tabIndex={0}
        aria-label={copy(`Project: ${p.name}. Press Enter to open.`, `项目：${p.name}。按 Enter 进入。`)}
        onClick={() => {
          handleSelectProject(p.id)
          if (!multiSelectMode) {
            navigate(`/projects/${p.id}`)
          }
        }}
        onFocus={() => handleSelectProject(p.id)}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            if (!multiSelectMode) handlePrimaryAction(p, stageSummary)
          }
        }}
      >
        <div className="project-card-meta">
          <div className="flex justify-between items-start gap-2">
            <div className="min-w-0">
              <div className="project-card-style">{p.style}</div>
            </div>
            <div className="flex flex-col items-end gap-2">
              {renderStatusTag(p)}
              {multiSelectMode && (
                <input
                  type="checkbox"
                  className="cursor-pointer"
                  checked={isChecked}
                  aria-label={copy(`Select ${p.name} for bulk actions`, `选择${p.name}进行批量操作`)}
                  onChange={(e) => {
                    e.stopPropagation()
                    handleToggleSelect(p.id, e.target.checked)
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              )}
            </div>
          </div>
        </div>

        <div className={`project-card-title ${isCompact ? 'text-sm' : 'text-base'} truncate`}>
          {p.name}
        </div>

        {!isCompact && (
          <p className={`text-gray-600 text-xs mb-1.5 ${isLarge ? 'line-clamp-2 min-h-[2rem]' : 'line-clamp-1 min-h-0'}`}>
            {p.description}
          </p>
        )}

        <div className={`mb-1.5 rounded border border-gray-100 bg-gray-50 ${isCompact ? 'px-2 py-1' : 'px-2 py-1.5'}`}>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] text-gray-500">{copy('Current stage', '当前阶段')}</span>
            <Tag color={stageSummary?.stageColor ?? 'default'} className="mr-0 text-[11px] leading-4">
              {stageSummary?.stageText ?? copy('Ready to continue', '待推进')}
            </Tag>
          </div>
          <div className={`mt-1 text-[11px] text-gray-600 ${isLarge ? 'line-clamp-2 min-h-[2rem]' : 'line-clamp-1 min-h-0'}`}>
            {stageSummary?.nextActionHint ?? copy('Open the project workspace to continue the main workflow.', '进入项目工作台后继续推进主流程')}
          </div>
          {isCompact ? (
            <div className="mt-1 text-[11px] text-gray-500 truncate">
              {copy('Next:', '下一步：')}{stageSummary?.nextActionLabel ?? copy('Open project', '进入项目')}
            </div>
          ) : (
            <div className="mt-1.5 flex flex-wrap gap-1">
              <Tag bordered={false} color="gold" className="mr-0 text-[11px]">
                {copy(`Awaiting review ${flowStats?.pendingConfirmShots ?? 0}`, `待确认 ${flowStats?.pendingConfirmShots ?? 0}`)}
              </Tag>
              <Tag bordered={false} color="green" className="mr-0 text-[11px]">
                {copy(`Ready ${flowStats?.readyShots ?? 0}`, `已就绪 ${flowStats?.readyShots ?? 0}`)}
              </Tag>
              <Tag bordered={false} color="processing" className="mr-0 text-[11px]">
                {copy(`Generating ${flowStats?.generatingShots ?? 0}`, `生成中 ${flowStats?.generatingShots ?? 0}`)}
              </Tag>
            </div>
          )}
        </div>

        {!isCompact && (
          <div className="mb-1.5">
            <div className="flex justify-between text-[11px] mb-0.5 text-gray-500">
              <span>{copy('Progress', '进度')}</span>
              <span>{p.progress}%</span>
            </div>
            <Progress
              percent={p.progress}
              size="small"
              showInfo={false}
              strokeColor="#3a5c6d"
            />
          </div>
        )}

        {isLarge ? (
          <Row gutter={6} className="mb-1.5">
            <Col span={6}>
              <Statistic title={<span className="text-[11px]">{copy('Chapters', '章节')}</span>} value={p.stats.chapters} valueStyle={{ fontSize: '13px' }} />
            </Col>
            <Col span={6}>
              <Statistic title={<span className="text-[11px]">{copy('Roles', '角色')}</span>} value={p.stats.roles} valueStyle={{ fontSize: '13px' }} />
            </Col>
            <Col span={6}>
              <Statistic title={<span className="text-[11px]">{copy('Scenes', '场景')}</span>} value={p.stats.scenes} valueStyle={{ fontSize: '13px' }} />
            </Col>
            <Col span={6}>
              <Statistic title={<span className="text-[11px]">{copy('Props', '道具')}</span>} value={p.stats.props} valueStyle={{ fontSize: '13px' }} />
            </Col>
          </Row>
        ) : (
          <div className="mb-1.5 text-[11px] text-gray-500 truncate">
            {copy(`Chapters ${p.stats.chapters} · Roles ${p.stats.roles} · Scenes ${p.stats.scenes} · Props ${p.stats.props}`, `章 ${p.stats.chapters} · 角 ${p.stats.roles} · 场 ${p.stats.scenes} · 道 ${p.stats.props}`)}
          </div>
        )}

        <div className={`mt-1 border-t border-gray-100 flex items-center justify-between gap-1 ${isCompact ? 'pt-1' : 'pt-1.5'}`}>
          <span className="text-[11px] text-gray-500 truncate">{p.updatedAt}</span>
          <Space size="small" onClick={(e) => e.stopPropagation()}>
            <Button
              type="default"
              size="small"
              icon={<EnterOutlined />}
              onClick={() => handlePrimaryAction(p, stageSummary)}
              className="text-[11px]"
            >
              {isCompact ? copy('Open', '进入') : mainActionLabel}
            </Button>
            {!isCompact && (
              <>
                <Button
                  type="text"
                  size="small"
                  icon={<EditOutlined />}
                  aria-label={copy(`Edit ${p.name}`, `编辑${p.name}`)}
                  title={copy(`Edit ${p.name}`, `编辑${p.name}`)}
                  onClick={(e) => handleOpenEdit(e, p)}
                  className="text-[11px]"
                />
                <Popconfirm
                  title={copy('Delete this project?', '确定删除该项目？')}
                  description={copy('This cannot be undone. Related chapters and assets will no longer be linked.', '删除后无法恢复，相关章节与素材将不再关联。')}
                  onConfirm={() => handleDelete(p.id)}
                  okText={copy('Delete', '删除')}
                  cancelText={copy('Cancel', '取消')}
                  okButtonProps={{ danger: true }}
                >
                  <Button
                    type="text"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    className="text-[11px]"
                    aria-label={copy(`Delete ${p.name}`, `删除${p.name}`)}
                    title={copy(`Delete ${p.name}`, `删除${p.name}`)}
                  />
                </Popconfirm>
              </>
            )}
          </Space>
        </div>
      </Card>
    )
  }

  return (
    <div className="project-lobby min-h-0 flex-1 flex flex-col overflow-hidden">
      <section className="project-lobby-masthead">
        <h1>{copy('Projects', '项目列表')}</h1>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenCreate}>
          {copy('New project', '新建项目')}
        </Button>
      </section>
      <div className="flex-shrink-0 space-y-2 pb-2">
      <div className="project-lobby-toolbar-shell sticky top-0 z-10 pb-1.5">
        <div className="project-lobby-toolbar">
          <div className="project-lobby-toolbar-main">
            <div className="project-lobby-search">
              <Input
                placeholder={copy('Search project names or descriptions', '搜索项目名称或描述')}
                aria-label={copy('Search project names or descriptions', '搜索项目名称或描述')}
                allowClear
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onPressEnter={(e) => setSearch(e.currentTarget.value)}
              />
              <Button
                type="default"
                icon={<SearchOutlined />}
                aria-label={copy('Search projects', '搜索项目')}
                title={copy('Search projects', '搜索项目')}
                onClick={() => setSearch(search)}
              />
            </div>

            <div className="project-lobby-actions">
              <Space size="small" className="project-lobby-sort">
                <span className="text-xs text-gray-500">{copy('Sort', '排序')}</span>
                <Select
                  size="small"
                  value={sortKey}
                  style={{ width: 128 }}
                  onChange={(value: SortKey) => setSortKey(value)}
                  options={[
                    { label: copy('Recently updated', '最近更新'), value: 'updatedAt' },
                    { label: copy('Name A–Z', '名称 A-Z'), value: 'name' },
                    { label: copy('Chapter count', '章节数量'), value: 'chapters' },
                  ]}
                />
                <Button
                  size="small"
                  type="text"
                  className="text-[11px]"
                  onClick={() => setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'))}
                  aria-label={copy(
                    sortOrder === 'asc' ? 'Sort descending' : 'Sort ascending',
                    sortOrder === 'asc' ? '按降序排序' : '按升序排序',
                  )}
                  title={copy(
                    sortOrder === 'asc' ? 'Sort descending' : 'Sort ascending',
                    sortOrder === 'asc' ? '按降序排序' : '按升序排序',
                  )}
                >
                  {sortOrder === 'asc' ? '↑' : '↓'}
                </Button>
              </Space>

              <Space size="small">
                <span className="text-xs text-gray-500">{copy('View', '视图')}</span>
                <Button
                  size="small"
                  type={viewMode === 'grid' ? 'primary' : 'text'}
                  icon={<AppstoreOutlined />}
                  onClick={() => setViewMode('grid')}
                  aria-label={copy('Grid view', '网格视图')}
                  title={copy('Grid view', '网格视图')}
                  aria-pressed={viewMode === 'grid'}
                />
                <Button
                  size="small"
                  type={viewMode === 'compact' ? 'primary' : 'text'}
                  icon={<BarsOutlined />}
                  onClick={() => setViewMode('compact')}
                  aria-label={copy('Compact view', '紧凑视图')}
                  title={copy('Compact view', '紧凑视图')}
                  aria-pressed={viewMode === 'compact'}
                />
                <Button
                  size="small"
                  type={viewMode === 'large' ? 'primary' : 'text'}
                  icon={<UnorderedListOutlined />}
                  onClick={() => setViewMode('large')}
                  aria-label={copy('Detail view', '详情视图')}
                  title={copy('Detail view', '详情视图')}
                  aria-pressed={viewMode === 'large'}
                />
              </Space>

              <Space size="small">
                <Button
                  size="small"
                  type={multiSelectMode ? 'primary' : 'text'}
                  className="text-[11px]"
                  onClick={() => {
                    setMultiSelectMode((prev) => !prev)
                    setSelectedIds([])
                  }}
                >
                  {multiSelectMode
                    ? copy(`Selected ${selectedIds.length}`, `已选 ${selectedIds.length}`)
                    : copy('Bulk', '批量')}
                </Button>
                {multiSelectMode && (
                  <Popconfirm
                    title={copy('Delete selected projects?', '批量删除项目')}
                    description={copy('Delete every selected project? This cannot be undone.', '确定删除选中的所有项目？该操作不可恢复。')}
                    onConfirm={handleBatchDelete}
                    okText={copy('Delete', '删除')}
                    cancelText={copy('Cancel', '取消')}
                    okButtonProps={{ danger: true }}
                    disabled={!selectedIds.length}
                  >
                    <Button size="small" danger disabled={!selectedIds.length} className="text-[11px]">
                      {copy('Delete selected', '删除选中')}
                    </Button>
                  </Popconfirm>
                )}
              </Space>
            </div>
          </div>

          <div className="project-lobby-filter-row">
            <Space size="small" className="project-lobby-filters" aria-label={copy('Project status filters', '项目状态筛选')}>
              <Button
                type={filterTab === 'all' ? 'primary' : 'text'}
                size="small"
                className="text-[11px]"
                onClick={() => setFilterTab('all')}
                aria-pressed={filterTab === 'all'}
              >
                {copy('All', '全部')}
              </Button>
              <Button
                type={filterTab === 'editRaw' ? 'primary' : 'text'}
                size="small"
                className="text-[11px]"
                onClick={() => setFilterTab('editRaw')}
                aria-pressed={filterTab === 'editRaw'}
              >
                {copy('Needs source', '待补原文')}
              </Button>
              <Button
                type={filterTab === 'extractShots' ? 'primary' : 'text'}
                size="small"
                className="text-[11px]"
                onClick={() => setFilterTab('extractShots')}
                aria-pressed={filterTab === 'extractShots'}
              >
                {copy('Needs shot extraction', '待提取分镜')}
              </Button>
              <Button
                type={filterTab === 'prepareShots' ? 'primary' : 'text'}
                size="small"
                className="text-[11px]"
                onClick={() => setFilterTab('prepareShots')}
                aria-pressed={filterTab === 'prepareShots'}
              >
                {copy('Needs shot prep', '待准备镜头')}
              </Button>
              <Button
                type={filterTab === 'generating' ? 'primary' : 'text'}
                size="small"
                className="text-[11px]"
                onClick={() => setFilterTab('generating')}
                aria-pressed={filterTab === 'generating'}
              >
                {copy('Generating', '生成中')}
              </Button>
              <Button
                type={filterTab === 'ready' ? 'primary' : 'text'}
                size="small"
                className="text-[11px]"
                onClick={() => setFilterTab('ready')}
                aria-pressed={filterTab === 'ready'}
              >
                {copy('Ready to continue', '可继续推进')}
              </Button>
            </Space>
          </div>
        </div>
      </div>
      </div>

      <div className="project-lobby-content min-h-0 flex-1 overflow-auto">
      <Row gutter={12}>
        <Col xs={24} lg={18}>
          <Row gutter={viewMode === 'compact' ? [8, 8] : viewMode === 'large' ? [14, 14] : [12, 12]}>
            {!loading && loadError && filteredSorted.length === 0 && (
              <Col span={24}>
                <Card>
                  <Result
                    status="error"
                    title={copy('Projects could not be loaded', '项目无法加载')}
                    subTitle={copy('Check your connection, then try again.', '请检查连接后重试。')}
                    extra={<Button type="primary" onClick={() => void load()}>{copy('Try again', '重试')}</Button>}
                  />
                </Card>
              </Col>
            )}
            {!loading && !loadError && filteredSorted.length === 0 && (
              <Col span={24}>
                <Card>
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={search ? copy('No matching projects', '没有匹配的项目') : copy('No projects yet', '暂无项目')}
                  >
                    {search ? (
                      <Button onClick={() => setSearch('')}>{copy('Clear search', '清除搜索')}</Button>
                    ) : (
                      <Button type="primary" icon={<PlusOutlined />} onClick={handleOpenCreate}>
                        {copy('New project', '新建项目')}
                      </Button>
                    )}
                  </Empty>
                </Card>
              </Col>
            )}
            {loading && projects.length === 0 && (
              <Col span={24}>
                <Card loading aria-label={copy('Loading projects', '正在加载项目')} />
              </Col>
            )}
            {filteredSorted.map((p) => (
              <Col
                key={p.id}
                xs={24}
                sm={viewMode === 'compact' ? 12 : viewMode === 'grid' ? 12 : 24}
                md={viewMode === 'compact' ? 8 : viewMode === 'grid' ? 8 : 24}
                lg={viewMode === 'compact' ? 6 : viewMode === 'grid' ? 6 : 24}
                xl={viewMode === 'compact' ? 4 : viewMode === 'grid' ? 6 : 24}
              >
                {renderCard(p)}
              </Col>
            ))}
          </Row>
        </Col>

        {filteredSorted.length > 0 && (
        <Col xs={24} lg={6} className="flex-shrink-0">
          <div className="h-full">
            <Card
              size="small"
              title={copy('Project overview', '项目速览')}
              className="project-overview mb-1.5"
              styles={{
                body: { padding: '10px' },
                header: { minHeight: 36, paddingInline: 10 },
              }}
            >
              {selectedProject ? (
                <div className="space-y-2">
                  <div>
                    <div className="text-[11px] text-gray-500 mb-0.5">{copy('Project name', '项目名称')}</div>
                    <div className="font-medium">{selectedProject.name}</div>
                  </div>
                  <div>
                    <div className="text-[11px] text-gray-500 mb-0.5">{copy('Description', '简介')}</div>
                    <div className="text-xs text-gray-600 line-clamp-2">
                      {selectedProject.description || copy('No description', '暂无描述')}
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] text-gray-500 mb-0.5">{copy('Progress', '进度')}</div>
                    <Progress
                      percent={selectedProject.progress}
                      size="small"
                      strokeColor="#3a5c6d"
                    />
                  </div>
                  <div className="text-[11px] text-gray-500">
                    {copy(`Chapters ${selectedProject.stats.chapters} · Roles ${selectedProject.stats.roles} · Scenes ${selectedProject.stats.scenes} · Props ${selectedProject.stats.props}`, `章 ${selectedProject.stats.chapters} · 角 ${selectedProject.stats.roles} · 场 ${selectedProject.stats.scenes} · 道 ${selectedProject.stats.props}`)}
                  </div>
                  <Button
                    type="default"
                    block
                    size="small"
                    icon={<EnterOutlined />}
                    onClick={() => navigate(`/projects/${selectedProject.id}`)}
                    className="text-[11px]"
                  >
                    {copy('Open chapter workspace', '进入章节工作台')}
                  </Button>
                </div>
              ) : (
                <div className="text-gray-500 text-sm py-6 text-center">
                  {copy('Hover or focus a project card to preview details', '悬停或聚焦项目卡片以预览详情')}
                </div>
              )}
            </Card>
          </div>
        </Col>
        )}
      </Row>
      </div>

      <Modal
        title={copy('New advertising video project', '新建广告视频项目')}
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={null}
        width={640}
        forceRender
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateSubmit}
          initialValues={{ advertiser_vertical: 'E-commerce / DTC', delivery_channel: 'Cross-channel' }}
        >
          <Form.Item
            name="name"
            label={copy('Project name', '项目名称')}
            rules={[{ required: true, message: copy('Enter a project name', '请输入项目名称') }]}
          >
            <Input placeholder={copy('For example: Summer product launch', '例如：夏季产品发布广告')} />
          </Form.Item>
          <Form.Item name="description" label={copy('Description (optional)', '项目简介（选填）')}>
            <Input.TextArea rows={3} placeholder={copy('Describe the product and intended campaign context.', '描述产品和计划投放场景。')} />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="advertiser_vertical" label={copy('Advertiser vertical', '广告主行业')} rules={[{ required: true }]}>
                <Select options={advertiserVerticalOptions} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="delivery_channel" label={copy('Delivery channel', '投放渠道')} rules={[{ required: true }]}>
                <Select options={deliveryChannelOptions} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="product_url" label={copy('Product webpage', '产品网页')}>
            <Input placeholder="https://" />
          </Form.Item>
          <Form.Item label={copy('Product asset', '产品素材')} extra={copy('A product webpage or one product asset is required.', '产品网页和产品素材至少提供一项。')}>
            <Upload.Dragger
              maxCount={1}
              beforeUpload={(file) => { setCreateProductFile(file); return false }}
              onRemove={() => { setCreateProductFile(null); return true }}
              fileList={createProductFile ? [{
                uid: createProductFile.name,
                name: createProductFile.name,
                status: 'done',
              } satisfies UploadFile] : []}
            >
              <p className="ant-upload-drag-icon"><InboxOutlined /></p>
              <p>{copy('Drop a product image, video, or brand asset here', '拖入产品图片、视频或品牌素材')}</p>
            </Upload.Dragger>
          </Form.Item>
          <Form.Item name="market" label={copy('Market (optional)', '市场（选填）')}>
            <Input placeholder={copy('For example: US, Japan, Global', '例如：美国、日本、全球')} />
          </Form.Item>
          <Form.Item className="mb-0">
            <Space>
              <Button onClick={() => setCreateModalOpen(false)}>{copy('Cancel', '取消')}</Button>
              <Button type="primary" htmlType="submit" loading={creatingProject}>
                {creatingProject ? copy('Creating project', '正在创建项目') : copy('Create and open', '创建并进入')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={copy('Edit project', '编辑项目')}
        open={editModalOpen}
        onCancel={() => { setEditModalOpen(false); setEditingProject(null) }}
        footer={null}
        width={520}
        forceRender
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleEditSubmit}
        >
          <Form.Item name="name" label={copy('Project name', '项目名称')} rules={[{ required: true, message: copy('Enter a project name', '请输入项目名称') }]}>
            <Input placeholder={copy('Project name', '项目名称')} />
          </Form.Item>
          <Form.Item name="description" label={copy('Description', '描述')}>
            <Input.TextArea rows={3} placeholder={copy('Project summary and visual direction', '项目简介与风格说明')} />
          </Form.Item>
          <Form.Item className="mb-0">
            <Space>
              <Button onClick={() => { setEditModalOpen(false); setEditingProject(null) }}>{copy('Cancel', '取消')}</Button>
              <Button type="primary" htmlType="submit" loading={updatingProject}>
                {updatingProject ? copy('Saving', '正在保存') : copy('Save', '保存')}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default ProjectLobby
