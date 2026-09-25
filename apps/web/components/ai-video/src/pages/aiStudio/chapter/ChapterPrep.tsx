import React, { useEffect, useMemo, useState } from 'react'
import {
  Badge,
  Button,
  Card,
  Collapse,
  Divider,
  Empty,
  Checkbox,
  Input,
  Layout,
  List,
  Modal,
  Skeleton,
  Space,
  Steps,
  Switch,
  Table,
  Tag,
  Tabs,
  Tooltip,
  message,
} from 'antd'
import type { TableColumnsType } from 'antd'
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  MergeCellsOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { StudioChaptersService } from '../../../services/generated'
import type { ChapterRead } from '../../../services/generated'
import type { Chapter } from '../../../mocks/data'
import { useAppStore } from '../../../store/useAppStore'
import { ChapterRawTextEditorModal } from './components/ChapterRawTextEditorModal'

const { Header, Content } = Layout

type ExtractKind = 'storyboards' | 'roles' | 'scenes' | 'props'

type StoryboardSuggestion = {
  id: string
  index: number
  title: string
  preview: string
  paragraphRange: string
  duration: string
  actions: string[]
  roles: string[]
  scenes: string[]
  props: string[]
  isTransition?: boolean
}

type RoleItem = {
  id: string
  name: string
  aliases: string[]
  firstSeen: string
  description: string
  primary: boolean
}

type SceneItem = {
  id: string
  name: string
  indoorOutdoor: '室内' | '室外' | '未知'
  time: '白天' | '夜晚' | '未知'
  keywords: string[]
}

type PropItem = {
  id: string
  name: string
  owner?: string
  count: number
  key: boolean
}

type SceneDraft = SceneItem & { description?: string; imageUrl?: string }
type PropDraft = PropItem & { description?: string; imageUrl?: string }
type RoleDraft = RoleItem & { imageUrl?: string }

type StoryboardDraft = StoryboardSuggestion

type ExtractResults = {
  storyboards: StoryboardSuggestion[]
  roles: RoleItem[]
  scenes: SceneItem[]
  props: PropItem[]
}

// TODO: 后续接入“章节草稿/版本历史/智能精简”等接口后，可移除当前页面的 Mock 逻辑与预置数据。

type EntityKind = 'roles' | 'scenes' | 'props'

type ExistingEntities = {
  roles: string[]
  scenes: string[]
  props: string[]
}

function entitiesStorageKey(projectId: string) {
  return `linglong_ai_video_project_entities_v1:${projectId}`
}

function extractMock(text: string, language: string): ExtractResults {
  const isChinese = language === 'zh-CN'
  const baseRoles = isChinese ? ['小雨', '阿川', '房东'] : ['Xiaoyu', 'Achuan', 'Landlord']
  const baseScenes = isChinese ? ['十平米出租屋', '城郊老旧小区走廊', '窗边'] : ['Ten-square-meter rental', 'Aging suburban corridor', 'By the window']
  const baseProps = isChinese ? ['欠条', '风扇', '手机', '钥匙'] : ['IOU', 'Fan', 'Phone', 'Keys']
  const hasText = text.trim().length > 0

  const storyboards: StoryboardSuggestion[] = (hasText ? Array.from({ length: 8 }) : []).map((_, i) => ({
    id: `sb-${i + 1}`,
    index: i + 1,
    title:
      i === 2 ? (isChinese ? '两人对峙' : 'Face-off') :
        i === 5 ? (isChinese ? '门口停顿' : 'A pause at the door') :
          (isChinese ? `段落推进 · ${i + 1}` : `Story beat ${i + 1}`),
    preview:
      i === 0 ? (isChinese ? '夜色下的老旧小区，路灯昏黄，情绪压着。' : 'Old buildings at night; muted streetlights carry the tension.') :
        i === 1 ? (isChinese ? '出租屋内风扇吱呀作响，欠条摊在桌上。' : 'A fan creaks in the rental room; an IOU lies on the table.') :
          i === 2 ? (isChinese ? '沉默持续，目光交锋，谁也不肯先开口。' : 'The silence lingers. Neither person looks away or speaks first.') :
            (isChinese ? '对话推进，情绪起伏，动作带出关系变化。' : 'The conversation advances as actions reveal a shifting relationship.'),
    paragraphRange: isChinese ? `第${i * 2 + 1}–${i * 2 + 2}段` : `Paragraphs ${i * 2 + 1}–${i * 2 + 2}`,
    duration: i % 3 === 0 ? (isChinese ? '8–12秒' : '8–12 sec') : (isChinese ? '5–9秒' : '5–9 sec'),
    actions: i % 2 === 0 ? (isChinese ? ['沉默', '转身'] : ['Silence', 'Turn away']) : (isChinese ? ['质问', '停顿'] : ['Question', 'Pause']),
    roles: i % 2 === 0 ? [baseRoles[0], baseRoles[1]] : [baseRoles[0]],
    scenes: i % 3 === 0 ? [baseScenes[0]] : [baseScenes[1]],
    props: i % 2 === 0 ? [baseProps[0]] : [baseProps[2]],
    isTransition: i === 5,
  }))

  const roles: RoleItem[] = (hasText ? baseRoles : []).map((name, i) => ({
    id: `r-${i + 1}`,
    name,
    aliases: name === baseRoles[0] ? (isChinese ? ['小雨儿'] : ['Rain']) : [],
    firstSeen: isChinese ? `第${i + 1}段` : `Paragraph ${i + 1}`,
    description: name === baseRoles[0] ? (isChinese ? '25岁互联网运营，疲惫但眼神坚定。' : 'A 25-year-old digital marketer, exhausted but determined.') : (isChinese ? '情绪克制，话少但带刺。' : 'Restrained and sparing with words, but sharp when speaking.'),
    primary: name !== baseRoles[2],
  }))

  const scenes: SceneItem[] = (hasText ? baseScenes : []).map((name, i) => ({
    id: `s-${i + 1}`,
    name,
    indoorOutdoor: i === 0 ? '室内' : i === 1 ? '室外' : '未知',
    time: i === 1 ? '夜晚' : '未知',
    keywords: i === 0 ? ['狭窄', '顶灯冷白'] : ['昏黄路灯', '潮湿'],
  }))

  const props: PropItem[] = (hasText ? baseProps : []).map((name, i) => ({
    id: `p-${i + 1}`,
    name,
    owner: name === baseProps[2] ? baseRoles[0] : undefined,
    count: 1 + (i % 3),
    key: name === baseProps[0],
  }))

  return { storyboards, roles, scenes, props }
}

function toUIChapter(c: ChapterRead): Chapter {
  return {
    id: c.id,
    projectId: c.project_id,
    index: c.index,
    title: c.title,
    summary: c.summary ?? '',
    storyboardCount: c.storyboard_count ?? 0,
    status: c.status ?? 'draft',
    updatedAt: new Date().toISOString(),
  }
}

const ChapterPrep: React.FC = () => {
  const { projectId, chapterId } = useParams<{ projectId?: string; chapterId?: string }>()
  const navigate = useNavigate()
  const language = useAppStore((state) => state.language)
  const copy = (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english)
  const sceneAttribute = (value: SceneItem['indoorOutdoor'] | SceneItem['time']) => {
    const labels: Record<string, string> = {
      室内: copy('Interior', '室内'),
      室外: copy('Exterior', '室外'),
      未知: copy('Unspecified', '未知'),
      白天: copy('Daytime', '白天'),
      夜晚: copy('Nighttime', '夜晚'),
    }
    return labels[value]
  }

  const [activeStep, setActiveStep] = useState(0)

  const [chapter, setChapter] = useState<Chapter | null>(null)
  const [titleEditing, setTitleEditing] = useState(false)
  const [titleValue, setTitleValue] = useState('')

  const [rawText, setRawText] = useState('')
  const [, setCondensedText] = useState('')

  const [editorModalOpen, setEditorModalOpen] = useState(false)

  const [extracting, setExtracting] = useState(false)
  const [results, setResults] = useState<ExtractResults>({ storyboards: [], roles: [], scenes: [], props: [] })
  const [extractReviewOpen, setExtractReviewOpen] = useState(false)
  const [extractReviewTab, setExtractReviewTab] = useState<EntityKind>('roles')
  const [existingEntities, setExistingEntities] = useState<ExistingEntities>({ roles: [], scenes: [], props: [] })
  const [selectedEntityKeys, setSelectedEntityKeys] = useState<Record<EntityKind, string[]>>({
    roles: [],
    scenes: [],
    props: [],
  })

  const [selectedKind, setSelectedKind] = useState<ExtractKind>('storyboards')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const [sceneDrafts, setSceneDrafts] = useState<SceneDraft[]>([])
  const [propDrafts, setPropDrafts] = useState<PropDraft[]>([])
  const [roleDrafts, setRoleDrafts] = useState<RoleDraft[]>([])
  const [storyboardDrafts, setStoryboardDrafts] = useState<StoryboardDraft[]>([])

  const [selectedSceneIds, setSelectedSceneIds] = useState<string[]>([])
  const [selectedPropIds, setSelectedPropIds] = useState<string[]>([])
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([])

  const [editEntityOpen, setEditEntityOpen] = useState(false)
  const [editEntityKind, setEditEntityKind] = useState<'scene' | 'prop' | 'role'>('scene')
  const [editEntityId, setEditEntityId] = useState<string | null>(null)
  const [editEntityName, setEditEntityName] = useState('')
  const [editEntityDesc, setEditEntityDesc] = useState('')

  const [addEntityOpen, setAddEntityOpen] = useState(false)
  const [addEntityKind, setAddEntityKind] = useState<'scene' | 'prop' | 'role'>('scene')
  const [addEntityName, setAddEntityName] = useState('')
  const [addEntityDesc, setAddEntityDesc] = useState('')

  const [pickFromAssetsOpen, setPickFromAssetsOpen] = useState(false)
  const [pickFromAssetsKind, setPickFromAssetsKind] = useState<'scene' | 'prop' | 'role'>('scene')
  const [pickFromAssetsSelected, setPickFromAssetsSelected] = useState<string[]>([])

  const [editStoryboardOpen, setEditStoryboardOpen] = useState(false)
  const [editingStoryboard, setEditingStoryboard] = useState<StoryboardDraft | null>(null)

  const handleFinishPrep = () => {
    if (!projectId) {
      navigate('/projects')
      return
    }
    navigate(`/projects/${projectId}?tab=chapters`)
  }

  // 预留：后续在 step 编辑区可展示字数/段落数

  useEffect(() => {
    if (!chapterId) return
    StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId })
      .then((res) => {
        const data = res.data
        if (!data) {
          setChapter(null)
          return
        }
        const ui = toUIChapter(data)
        setChapter(ui)
        setTitleValue(ui.title)

        const nextRaw = data.raw_text ?? ''
        const nextCondensed = data.condensed_text ?? ''
        setRawText(nextRaw)
        setCondensedText(nextCondensed)
        setResults(extractMock(nextRaw, language))
      })
      .catch(() => {
        setChapter(null)
      })
  }, [chapterId, language])

  useEffect(() => {
    // 将提取结果映射为各 step 的可编辑草稿（尽量保留用户编辑/生成状态）
    setSceneDrafts((prev) => {
      const prevMap = new Map(prev.map((x) => [x.id, x]))
      return results.scenes.map((s) => ({ ...s, ...(prevMap.get(s.id) ?? {}) }))
    })
    setPropDrafts((prev) => {
      const prevMap = new Map(prev.map((x) => [x.id, x]))
      return results.props.map((p) => ({ ...p, ...(prevMap.get(p.id) ?? {}) }))
    })
    setRoleDrafts((prev) => {
      const prevMap = new Map(prev.map((x) => [x.id, x]))
      return results.roles.map((r) => ({ ...r, ...(prevMap.get(r.id) ?? {}) }))
    })
    setStoryboardDrafts((prev) => {
      const prevMap = new Map(prev.map((x) => [x.id, x]))
      return results.storyboards.map((sb) => ({ ...sb, ...(prevMap.get(sb.id) ?? {}) }))
    })
  }, [results.scenes, results.props, results.roles, results.storyboards])

  useEffect(() => {
    if (!projectId) return
    try {
      const raw = window.localStorage.getItem(entitiesStorageKey(projectId))
      const parsed = raw ? (JSON.parse(raw) as ExistingEntities) : null
      if (parsed && typeof parsed === 'object') {
        setExistingEntities({
          roles: Array.isArray(parsed.roles) ? parsed.roles : [],
          scenes: Array.isArray(parsed.scenes) ? parsed.scenes : [],
          props: Array.isArray(parsed.props) ? parsed.props : [],
        })
      }
    } catch {
      // ignore
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    try {
      window.localStorage.setItem(entitiesStorageKey(projectId), JSON.stringify(existingEntities))
    } catch {
      // ignore
    }
  }, [projectId, existingEntities])

  // TODO: 后续可在此接入“章节草稿/版本历史”接口，替换掉当前预置数据与本地状态实现。

  const runExtract = async (kind: 'all' | ExtractKind) => {
    if (!rawText.trim()) {
      message.warning(copy('Paste or enter source text first.', '请先粘贴或输入原文'))
      return
    }
    setExtracting(true)
    try {
      await new Promise((r) => setTimeout(r, 900))
      const next = extractMock(rawText, language)
      setResults((prev) => {
        if (kind === 'all') return next
        switch (kind) {
          case 'storyboards':
            return { ...prev, storyboards: next.storyboards }
          case 'roles':
            return { ...prev, roles: next.roles }
          case 'scenes':
            return { ...prev, scenes: next.scenes }
          case 'props':
            return { ...prev, props: next.props }
          default:
            return prev
        }
      })
      message.success(copy('Extraction complete (mock).', '提取完成（Mock）'))

      // 打开提取回显浮窗
      if (kind === 'roles' || kind === 'scenes' || kind === 'props') {
        setExtractReviewTab(kind)
      } else {
        setExtractReviewTab('roles')
      }
      setSelectedEntityKeys({ roles: [], scenes: [], props: [] })
      setExtractReviewOpen(true)
    } finally {
      setExtracting(false)
    }
  }

  const existingSet = useMemo(() => {
    return {
      roles: new Set(existingEntities.roles),
      scenes: new Set(existingEntities.scenes),
      props: new Set(existingEntities.props),
    }
  }, [existingEntities])

  const addSelectedEntities = (kind: EntityKind) => {
    const selected = selectedEntityKeys[kind]
    if (selected.length === 0) {
      message.info(copy('Select content to add first.', '请先选择要添加的内容'))
      return
    }
    const duplicates = selected.filter((name) => existingSet[kind].has(name))
    const uniques = selected.filter((name) => !existingSet[kind].has(name))

    const doAdd = () => {
      if (uniques.length === 0) {
        message.info(copy('All selected items already exist.', '所选内容均已存在，无需添加'))
        return
      }
      setExistingEntities((prev) => ({
        ...prev,
        [kind]: Array.from(new Set([...(prev[kind] as string[]), ...uniques])),
      }))
      setSelectedEntityKeys((prev) => ({ ...prev, [kind]: [] }))
      message.success(copy(`Added ${uniques.length} item(s).`, `已添加 ${uniques.length} 项`))
    }

    if (duplicates.length > 0) {
      Modal.confirm({
        title: copy('Duplicate items', '存在重复内容'),
        content: copy(
          `${duplicates.length} selected item(s) already exist. Duplicates will be skipped. Continue adding the rest?`,
          `你选择的内容中有 ${duplicates.length} 项已存在，将自动跳过重复项，是否继续添加其余内容？`,
        ),
        okText: copy('Continue', '继续添加'),
        cancelText: copy('Cancel', '取消'),
        onOk: doAdd,
      })
      return
    }
    doAdd()
  }

  const toggleSelectAllNew = (kind: EntityKind) => {
    const items =
      kind === 'roles'
        ? results.roles.map((r) => r.name)
        : kind === 'scenes'
          ? results.scenes.map((s) => s.name)
          : results.props.map((p) => p.name)
    const newOnes = items.filter((name) => !existingSet[kind].has(name))
    setSelectedEntityKeys((prev) => ({ ...prev, [kind]: newOnes }))
  }

  const openEditEntity = (kind: 'scene' | 'prop' | 'role', id: string) => {
    setEditEntityKind(kind)
    setEditEntityId(id)
    if (kind === 'scene') {
      const it = sceneDrafts.find((x) => x.id === id)
      setEditEntityName(it?.name ?? '')
      setEditEntityDesc(it?.description ?? '')
    } else if (kind === 'prop') {
      const it = propDrafts.find((x) => x.id === id)
      setEditEntityName(it?.name ?? '')
      setEditEntityDesc(it?.description ?? '')
    } else {
      const it = roleDrafts.find((x) => x.id === id)
      setEditEntityName(it?.name ?? '')
      setEditEntityDesc(it?.description ?? it?.description ?? '')
    }
    setEditEntityOpen(true)
  }

  const saveEditEntity = () => {
    if (!editEntityId) return
    if (editEntityKind === 'scene') {
      setSceneDrafts((prev) =>
        prev.map((x) => (x.id === editEntityId ? { ...x, name: editEntityName, description: editEntityDesc } : x)),
      )
    } else if (editEntityKind === 'prop') {
      setPropDrafts((prev) =>
        prev.map((x) => (x.id === editEntityId ? { ...x, name: editEntityName, description: editEntityDesc } : x)),
      )
    } else {
      setRoleDrafts((prev) =>
        prev.map((x) => (x.id === editEntityId ? { ...x, name: editEntityName, description: editEntityDesc } : x)),
      )
    }
    setEditEntityOpen(false)
    setEditEntityId(null)
    message.success(copy('Saved (mock).', '已保存（Mock）'))
  }

  const openAddEntity = (kind: 'scene' | 'prop' | 'role') => {
    setAddEntityKind(kind)
    setAddEntityName('')
    setAddEntityDesc('')
    setAddEntityOpen(true)
  }

  const addEntity = () => {
    if (!addEntityName.trim()) {
      message.warning(copy('Enter a name.', '请输入名称'))
      return
    }
    const id = `${addEntityKind}-${Date.now()}`
    if (addEntityKind === 'scene') {
      setSceneDrafts((prev) => [
        ...prev,
        {
          id,
          name: addEntityName.trim(),
          indoorOutdoor: '未知' as const,
          time: '未知' as const,
          keywords: [] as string[],
          description: addEntityDesc,
        },
      ])
    } else if (addEntityKind === 'prop') {
      setPropDrafts((prev) => [
        ...prev,
        { id, name: addEntityName.trim(), count: 1, key: false, description: addEntityDesc },
      ])
    } else {
      setRoleDrafts((prev) => [
        ...prev,
        {
          id,
          name: addEntityName.trim(),
          aliases: [],
          firstSeen: '',
          description: addEntityDesc,
          primary: true,
        },
      ])
    }
    setAddEntityOpen(false)
    message.success(copy('Added (mock).', '已添加（Mock）'))
  }

  const openPickFromAssets = (kind: 'scene' | 'prop' | 'role') => {
    setPickFromAssetsKind(kind)
    setPickFromAssetsSelected([])
    setPickFromAssetsOpen(true)
  }

  const confirmPickFromAssets = () => {
    if (pickFromAssetsSelected.length === 0) {
      message.info(copy('Select content to add first.', '请先选择要添加的内容'))
      return
    }
    if (pickFromAssetsKind === 'scene') {
      setSceneDrafts((prev) => [
        ...prev,
        ...pickFromAssetsSelected.map((name) => ({
          id: `asset-scene-${name}`,
          name,
          indoorOutdoor: '未知' as const,
          time: '未知' as const,
          keywords: [] as string[],
          description: copy('Added from asset library (mock).', '来自资产库（Mock）'),
        })),
      ])
    } else if (pickFromAssetsKind === 'prop') {
      setPropDrafts((prev) => [
        ...prev,
        ...pickFromAssetsSelected.map((name) => ({
          id: `asset-prop-${name}`,
          name,
          count: 1,
          key: false,
          description: copy('Added from asset library (mock).', '来自资产库（Mock）'),
        })),
      ])
    } else {
      setRoleDrafts((prev) => [
        ...prev,
        ...pickFromAssetsSelected.map((name) => ({
          id: `asset-role-${name}`,
          name,
          aliases: [],
          firstSeen: '',
          description: copy('Added from asset library (mock).', '来自资产库（Mock）'),
          primary: true,
        })),
      ])
    }
    setPickFromAssetsOpen(false)
    message.success(copy('Added from asset library (mock).', '已从资产库添加（Mock）'))
  }

  const generateImages = (kind: 'scene' | 'prop' | 'role') => {
    const stamp = Date.now()
    const url = `mock://generated/${kind}/${stamp}`
    if (kind === 'scene') {
      setSceneDrafts((prev) =>
        prev.map((x) => (selectedSceneIds.includes(x.id) ? { ...x, imageUrl: url } : x)),
      )
      message.success(copy('Scene image generated (mock).', '已生成场景图片（Mock）'))
      return
    }
    if (kind === 'prop') {
      setPropDrafts((prev) =>
        prev.map((x) => (selectedPropIds.includes(x.id) ? { ...x, imageUrl: url } : x)),
      )
      message.success(copy('Prop image generated (mock).', '已生成道具图片（Mock）'))
      return
    }
    setRoleDrafts((prev) =>
      prev.map((x) => (selectedRoleIds.includes(x.id) ? { ...x, imageUrl: url } : x)),
    )
    message.success(copy('Character image generated (mock).', '已生成角色图片（Mock）'))
  }

  const openEditStoryboard = (sb: StoryboardDraft) => {
    setEditingStoryboard(sb)
    setEditStoryboardOpen(true)
  }

  const saveStoryboard = () => {
    if (!editingStoryboard) return
    setStoryboardDrafts((prev) => prev.map((x) => (x.id === editingStoryboard.id ? editingStoryboard : x)))
    setEditStoryboardOpen(false)
    setEditingStoryboard(null)
    message.success(copy('Storyboard saved (mock).', '已保存分镜（Mock）'))
  }

  const currentItemsCount = useMemo(() => {
    return {
      storyboards: results.storyboards.length,
      roles: results.roles.length,
      scenes: results.scenes.length,
      props: results.props.length,
    }
  }, [results])

  const selectedStoryboard = useMemo(
    () => results.storyboards.find((x) => x.id === selectedId) ?? null,
    [results.storyboards, selectedId],
  )

  const selectedRole = useMemo(
    () => results.roles.find((x) => x.id === selectedId) ?? null,
    [results.roles, selectedId],
  )

  const selectedScene = useMemo(
    () => results.scenes.find((x) => x.id === selectedId) ?? null,
    [results.scenes, selectedId],
  )

  const selectedProp = useMemo(
    () => results.props.find((x) => x.id === selectedId) ?? null,
    [results.props, selectedId],
  )

  return (
    <Layout style={{ height: '100%', minHeight: 0, background: '#eef2f7' }}>
      <Header
        style={{
          padding: '0 16px',
          background: '#fff',
          borderBottom: '1px solid #e2e8f0',
          boxShadow: '0 2px 4px rgba(0,0,0,0.04)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <Link
          to={projectId ? `/projects/${projectId}?tab=chapters` : '/projects'}
          className="text-gray-600 hover:text-blue-600 flex items-center gap-1"
        >
          <ArrowLeftOutlined /> {copy('Back to chapters', '返回章节列表')}
        </Link>
        <Divider type="vertical" />

        <div className="min-w-0 flex-1 flex items-center gap-2">
          {titleEditing ? (
            <Input
              value={titleValue}
              autoFocus
              onChange={(e) => setTitleValue(e.target.value)}
              onBlur={() => setTitleEditing(false)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') setTitleEditing(false)
                if (e.key === 'Escape') {
                  setTitleEditing(false)
                  setTitleValue(chapter?.title ?? titleValue)
                }
              }}
              style={{ maxWidth: 520 }}
            />
          ) : (
            <div
              className="font-medium text-gray-900 truncate cursor-pointer"
              title={copy('Double-click to edit title', '双击编辑标题')}
              onDoubleClick={() => setTitleEditing(true)}
            >
              {chapter ? copy(`Chapter ${chapter.index} · ${titleValue || chapter.title}`, `第${chapter.index}章 · ${titleValue || chapter.title}`) : copy('Chapter editor', '章节编辑')}
            </div>
          )}
          <div className="text-xs text-gray-500 flex items-center gap-1">
            <CheckCircleOutlined /> {copy('Loaded', '已加载')}
          </div>
        </div>
      </Header>

      <Content
        style={{
          padding: 16,
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Card size="small" className="mb-3">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <Steps
              current={activeStep}
              onChange={setActiveStep}
              className="flex-1 min-w-[520px]"
              items={[
                { title: copy('Extract', '智能提取') },
                { title: copy('Scenes', '场景生成') },
                { title: copy('Props', '道具生成') },
                { title: copy('Characters', '角色生成') },
                { title: copy('Storyboard', '分镜预览') },
              ]}
            />
            <Space>
              {activeStep > 0 && (
                <Button onClick={() => setActiveStep((s) => Math.max(0, s - 1))}>
                  {copy('Previous: ', '上一步：')}{[copy('Extract', '智能提取'), copy('Scenes', '场景生成'), copy('Props', '道具生成'), copy('Characters', '角色生成'), copy('Storyboard', '分镜预览')][activeStep - 1]}
                </Button>
              )}
              {activeStep < 4 ? (
                <Button type="primary" onClick={() => setActiveStep((s) => Math.min(4, s + 1))}>
                  {copy('Next: ', '下一步：')}{[copy('Extract', '智能提取'), copy('Scenes', '场景生成'), copy('Props', '道具生成'), copy('Characters', '角色生成'), copy('Storyboard', '分镜预览')][activeStep + 1]}
                </Button>
              ) : (
                <Button type="primary" onClick={handleFinishPrep}>
                  {copy('Finish setup', '准备结束')}
                </Button>
              )}
            </Space>
          </div>
        </Card>

        {activeStep === 0 && (
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12, overflow: 'hidden' }}>
            <Card size="small">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <Space>
                  <Button icon={<FileTextOutlined />} onClick={() => setEditorModalOpen(true)}>
                    {copy('Edit source', '编辑原文')}
                  </Button>
                  <Button type="primary" loading={extracting} icon={<ThunderboltOutlined />} onClick={() => void runExtract('all')}>
                    {copy('Extract all', '一键提取全部')}
                  </Button>
                  <span className="text-xs text-gray-500">
                    {currentItemsCount.roles + currentItemsCount.scenes + currentItemsCount.props > 0 ? copy('Extracted — ready to run again', '已提取，可重新提取') : copy('Not extracted yet', '尚未提取')}
                  </span>
                </Space>
              </div>
            </Card>

            {/* 左导航 + 右详情 */}
            <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 12, overflow: 'hidden' }}>
              {/* 左侧导航 */}
              <Card
                style={{ width: 340, minWidth: 280, maxWidth: 420, height: '100%', overflow: 'hidden', flexShrink: 0 }}
                styles={{ body: { padding: 12, height: '100%', minHeight: 0, overflow: 'auto' } }}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="font-medium">{copy('Extracted results', '提取结果导航')}</div>
                  <Badge status={extracting ? 'processing' : 'success'} text={extracting ? copy('Extracting…', '提取中…') : copy('Ready', '就绪')} />
                </div>
                <Collapse
                  defaultActiveKey={['storyboards']}
                  items={[
                    {
                      key: 'storyboards',
                      label: copy(`Storyboard suggestions (${currentItemsCount.storyboards})`, `原文分镜建议（${currentItemsCount.storyboards}）`),
                      extra: (
                        <Space size="small">
                          <Tooltip title={copy('Extract again', '重新提取')}>
                            <Button size="small" type="text" icon={<ReloadOutlined />} onClick={() => void runExtract('storyboards')} />
                          </Tooltip>
                        </Space>
                      ),
                      children: extracting ? (
                        <Skeleton active paragraph={{ rows: 4 }} />
                      ) : (
                        <List
                          size="small"
                          dataSource={results.storyboards}
                          locale={{ emptyText: <Empty description={copy('No storyboard suggestions', '暂无分镜建议')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                          renderItem={(it) => (
                            <List.Item
                              onClick={() => {
                                setSelectedKind('storyboards')
                                setSelectedId(it.id)
                              }}
                              style={{
                                cursor: 'pointer',
                                borderRadius: 10,
                                padding: '8px 10px',
                                background: selectedKind === 'storyboards' && selectedId === it.id ? 'rgba(59,130,246,0.10)' : undefined,
                              }}
                            >
                              <div className="min-w-0">
                                <div className="text-sm font-medium truncate">
                                  {String(it.index).padStart(2, '0')} · {it.title}
                                </div>
                                <div className="text-xs text-gray-500 truncate">{it.preview}</div>
                              </div>
                            </List.Item>
                          )}
                        />
                      ),
                    },
                    {
                      key: 'roles',
                      label: copy(`Characters (${currentItemsCount.roles})`, `角色（${currentItemsCount.roles}）`),
                      children: extracting ? (
                        <Skeleton active paragraph={{ rows: 3 }} />
                      ) : (
                        <List
                          size="small"
                          dataSource={results.roles}
                          locale={{ emptyText: <Empty description={copy('No characters', '暂无角色')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                          renderItem={(it) => (
                            <List.Item
                              onClick={() => {
                                setSelectedKind('roles')
                                setSelectedId(it.id)
                              }}
                              style={{
                                cursor: 'pointer',
                                borderRadius: 10,
                                padding: '8px 10px',
                                background: selectedKind === 'roles' && selectedId === it.id ? 'rgba(59,130,246,0.10)' : undefined,
                              }}
                            >
                              <div className="min-w-0">
                                <div className="text-sm font-medium truncate">{it.name}</div>
                                <div className="text-xs text-gray-500 truncate">{it.description}</div>
                              </div>
                            </List.Item>
                          )}
                        />
                      ),
                    },
                    {
                      key: 'scenes',
                      label: copy(`Scenes (${currentItemsCount.scenes})`, `场景（${currentItemsCount.scenes}）`),
                      children: extracting ? (
                        <Skeleton active paragraph={{ rows: 3 }} />
                      ) : (
                        <List
                          size="small"
                          dataSource={results.scenes}
                          locale={{ emptyText: <Empty description={copy('No scenes', '暂无场景')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                          renderItem={(it) => (
                            <List.Item
                              onClick={() => {
                                setSelectedKind('scenes')
                                setSelectedId(it.id)
                              }}
                              style={{
                                cursor: 'pointer',
                                borderRadius: 10,
                                padding: '8px 10px',
                                background: selectedKind === 'scenes' && selectedId === it.id ? 'rgba(59,130,246,0.10)' : undefined,
                              }}
                            >
                              <div className="min-w-0">
                                <div className="text-sm font-medium truncate">{it.name}</div>
                                <div className="text-xs text-gray-500 truncate">{sceneAttribute(it.indoorOutdoor)} · {sceneAttribute(it.time)}</div>
                              </div>
                            </List.Item>
                          )}
                        />
                      ),
                    },
                    {
                      key: 'props',
                      label: copy(`Props (${currentItemsCount.props})`, `道具（${currentItemsCount.props}）`),
                      children: extracting ? (
                        <Skeleton active paragraph={{ rows: 3 }} />
                      ) : (
                        <List
                          size="small"
                          dataSource={results.props}
                          locale={{ emptyText: <Empty description={copy('No props', '暂无道具')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                          renderItem={(it) => (
                            <List.Item
                              onClick={() => {
                                setSelectedKind('props')
                                setSelectedId(it.id)
                              }}
                              style={{
                                cursor: 'pointer',
                                borderRadius: 10,
                                padding: '8px 10px',
                                background: selectedKind === 'props' && selectedId === it.id ? 'rgba(59,130,246,0.10)' : undefined,
                              }}
                            >
                              <div className="min-w-0">
                                <div className="text-sm font-medium truncate">{it.name}</div>
                                <div className="text-xs text-gray-500 truncate">{copy(`Appears ${it.count} time(s)`, `出现 ${it.count} 次`)}{it.key ? copy(' · Key prop', ' · 关键道具') : ''}</div>
                              </div>
                            </List.Item>
                          )}
                        />
                      ),
                    },
                  ]}
                />
              </Card>

              {/* 右侧详情 */}
              <Card style={{ flex: 1, minWidth: 0, height: '100%', overflow: 'hidden' }} styles={{ body: { padding: 12, height: '100%', minHeight: 0, overflow: 'auto' } }}>
                {selectedKind === 'storyboards' && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="font-medium">{copy('Storyboard suggestion', '分镜建议')}</div>
                      <Space>
                        <Button icon={<MergeCellsOutlined />}>{copy('Bulk actions (mock)', '批量操作（Mock）')}</Button>
                        <Button icon={<PlayCircleOutlined />}>{copy('Preview (mock)', '预览（Mock）')}</Button>
                      </Space>
                    </div>
                    {selectedStoryboard ? (
                      <Card size="small">
                        <div className="text-base font-semibold">
                          {String(selectedStoryboard.index).padStart(2, '0')} · {selectedStoryboard.title}
                          {selectedStoryboard.isTransition && <Tag color="purple" className="ml-2">{copy('Transition', '转场点')}</Tag>}
                        </div>
                        <Divider />
                        <div className="grid grid-cols-2 gap-3 text-sm">
                          <div><span className="text-gray-500">{copy('Source paragraphs: ', '原文段落：')}</span>{selectedStoryboard.paragraphRange}</div>
                          <div><span className="text-gray-500">{copy('Suggested duration: ', '建议时长：')}</span>{selectedStoryboard.duration}</div>
                          <div><span className="text-gray-500">{copy('Key actions: ', '关键动作：')}</span>{selectedStoryboard.actions.join(' · ')}</div>
                          <div><span className="text-gray-500">{copy('Characters: ', '涉及角色：')}</span>{selectedStoryboard.roles.join(' · ')}</div>
                          <div><span className="text-gray-500">{copy('Scenes: ', '涉及场景：')}</span>{selectedStoryboard.scenes.join(' · ')}</div>
                          <div><span className="text-gray-500">{copy('Props: ', '涉及道具：')}</span>{selectedStoryboard.props.join(' · ')}</div>
                        </div>
                        <Divider />
                        <Space wrap>
                          <Button icon={<EditOutlined />}>{copy('Edit title (mock)', '编辑标题（Mock）')}</Button>
                          <Button icon={<MergeCellsOutlined />}>{copy('Merge with previous (mock)', '合并到上一条（Mock）')}</Button>
                          <Button icon={<DeleteOutlined />} danger>{copy('Delete (mock)', '删除（Mock）')}</Button>
                          <Button icon={<VideoCameraOutlined />}>{copy('Mark as transition (mock)', '标记为转场（Mock）')}</Button>
                        </Space>
                      </Card>
                    ) : (
                      <Empty description={copy('Choose a storyboard suggestion on the left.', '请从左侧选择一条分镜建议')} />
                    )}
                  </div>
                )}

                {selectedKind === 'roles' && (
                  <div className="space-y-3">
                    <div className="font-medium">{copy('Characters', '角色')}</div>
                    {selectedRole ? (
                      <Card size="small">
                        <div className="flex items-center justify-between">
                          <div className="text-base font-semibold">{selectedRole.name}</div>
                          <Space>
                            <span className="text-sm text-gray-500">{copy('Primary character', '主要角色')}</span>
                            <Switch checked={selectedRole.primary} />
                          </Space>
                        </div>
                        <div className="text-sm text-gray-500 mt-1">{copy('First appearance: ', '首次出现：')}{selectedRole.firstSeen}</div>
                        <Divider />
                        <div className="text-sm">{selectedRole.description}</div>
                        <div className="mt-2">
                          {selectedRole.aliases.map((a) => (
                            <Tag key={a}>{a}</Tag>
                          ))}
                        </div>
                        <Divider />
                        <Space wrap>
                          <Button>{copy('Link asset-library character (mock)', '关联资产库角色（Mock）')}</Button>
                          <Button type="primary">{copy('Create character asset (mock)', '创建新角色资产（Mock）')}</Button>
                          <Button danger icon={<DeleteOutlined />}>{copy('Delete (mock)', '删除（Mock）')}</Button>
                        </Space>
                      </Card>
                    ) : (
                      <Empty description={copy('Choose a character on the left.', '请从左侧选择一个角色')} />
                    )}
                  </div>
                )}

                {selectedKind === 'scenes' && (
                  <div className="space-y-3">
                    <div className="font-medium">{copy('Scenes', '场景')}</div>
                    {selectedScene ? (
                      <Card size="small">
                        <div className="text-base font-semibold">{selectedScene.name}</div>
                        <div className="text-sm text-gray-500 mt-1">{sceneAttribute(selectedScene.indoorOutdoor)} · {sceneAttribute(selectedScene.time)}</div>
                        <Divider />
                        <div className="flex flex-wrap gap-2">
                          {selectedScene.keywords.map((k) => <Tag key={k} color="blue">{k}</Tag>)}
                        </div>
                        <Divider />
                        <Space wrap>
                          <Button>{copy('Link asset-library scene (mock)', '关联资产库场景（Mock）')}</Button>
                          <Button type="primary">{copy('Create scene asset (mock)', '创建新场景资产（Mock）')}</Button>
                          <Button danger icon={<DeleteOutlined />}>{copy('Delete (mock)', '删除（Mock）')}</Button>
                        </Space>
                      </Card>
                    ) : (
                      <Empty description={copy('Choose a scene on the left.', '请从左侧选择一个场景')} />
                    )}
                  </div>
                )}

                {selectedKind === 'props' && (
                  <div className="space-y-3">
                    <div className="font-medium">{copy('Props', '道具')}</div>
                    {selectedProp ? (
                      <Card size="small">
                        <div className="flex items-center gap-2">
                          <div className="text-base font-semibold">{selectedProp.name}</div>
                          {selectedProp.key && <Tag color="gold">{copy('Key prop', '关键道具')}</Tag>}
                        </div>
                        <div className="text-sm text-gray-500 mt-1">{copy('Appearances: ', '出现次数：')}{selectedProp.count}</div>
                        <Divider />
                        <Space wrap>
                          <Button>{copy('Link asset-library prop (mock)', '关联资产库道具（Mock）')}</Button>
                          <Button type="primary">{copy('Create prop asset (mock)', '创建新道具资产（Mock）')}</Button>
                          <Button danger icon={<DeleteOutlined />}>{copy('Delete (mock)', '删除（Mock）')}</Button>
                        </Space>
                      </Card>
                    ) : (
                      <Empty description={copy('Choose a prop on the left.', '请从左侧选择一个道具')} />
                    )}
                  </div>
                )}
              </Card>
            </div>
          </div>
        )}

        {activeStep === 1 && (
          <Card title={copy('Scenes', '场景生成')} style={{ flex: 1, minHeight: 0, overflow: 'auto' }} styles={{ body: { padding: 12 } }}>
            <div className="flex items-center justify-between mb-3">
              <Space>
                <Button type="primary" disabled={selectedSceneIds.length === 0} onClick={() => generateImages('scene')}>
                  {copy('Generate selected images (mock)', '批量生成图片（Mock）')}
                </Button>
                <span className="text-xs text-gray-500">{copy(`${selectedSceneIds.length} selected`, `已选 ${selectedSceneIds.length} 项`)}</span>
              </Space>
              <Space>
                <Button onClick={() => openAddEntity('scene')}>{copy('Add manually', '手动添加')}</Button>
                <Button onClick={() => openPickFromAssets('scene')}>{copy('Add from assets', '从资产库添加')}</Button>
              </Space>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {sceneDrafts.map((s) => (
                <Card
                  key={s.id}
                  size="small"
                  title={
                    <div className="flex items-center gap-2">
                      <Checkbox
                        checked={selectedSceneIds.includes(s.id)}
                        onChange={(e) =>
                          setSelectedSceneIds((prev) =>
                            e.target.checked ? [...prev, s.id] : prev.filter((x) => x !== s.id),
                          )
                        }
                      />
                      <span className="truncate">{s.name}</span>
                    </div>
                  }
                  extra={
                    <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditEntity('scene', s.id)}>
                      {copy('Edit', '编辑')}
                    </Button>
                  }
                >
                  <div className="text-xs text-gray-500 mb-2 line-clamp-2">{s.description || copy('No description', '暂无描述')}</div>
                  <div className="h-32 rounded-md border border-gray-200 bg-gray-50 flex items-center justify-center text-gray-500 text-sm">
                    {s.imageUrl ? copy('Generated (mock)', '已生成（Mock）') : copy('Not generated', '未生成')}
                  </div>
                </Card>
              ))}
            </div>
          </Card>
        )}

        {activeStep === 2 && (
          <Card title={copy('Props', '道具生成')} style={{ flex: 1, minHeight: 0, overflow: 'auto' }} styles={{ body: { padding: 12 } }}>
            <div className="flex items-center justify-between mb-3">
              <Space>
                <Button type="primary" disabled={selectedPropIds.length === 0} onClick={() => generateImages('prop')}>
                  {copy('Generate selected images (mock)', '批量生成图片（Mock）')}
                </Button>
                <span className="text-xs text-gray-500">{copy(`${selectedPropIds.length} selected`, `已选 ${selectedPropIds.length} 项`)}</span>
              </Space>
              <Space>
                <Button onClick={() => openAddEntity('prop')}>{copy('Add manually', '手动添加')}</Button>
                <Button onClick={() => openPickFromAssets('prop')}>{copy('Add from assets', '从资产库添加')}</Button>
              </Space>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {propDrafts.map((p) => (
                <Card
                  key={p.id}
                  size="small"
                  title={
                    <div className="flex items-center gap-2">
                      <Checkbox
                        checked={selectedPropIds.includes(p.id)}
                        onChange={(e) =>
                          setSelectedPropIds((prev) =>
                            e.target.checked ? [...prev, p.id] : prev.filter((x) => x !== p.id),
                          )
                        }
                      />
                      <span className="truncate">{p.name}</span>
                    </div>
                  }
                  extra={
                    <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditEntity('prop', p.id)}>
                      {copy('Edit', '编辑')}
                    </Button>
                  }
                >
                  <div className="text-xs text-gray-500 mb-2 line-clamp-2">{p.description || copy('No description', '暂无描述')}</div>
                  <div className="h-32 rounded-md border border-gray-200 bg-gray-50 flex items-center justify-center text-gray-500 text-sm">
                    {p.imageUrl ? copy('Generated (mock)', '已生成（Mock）') : copy('Not generated', '未生成')}
                  </div>
                </Card>
              ))}
            </div>
          </Card>
        )}

        {activeStep === 3 && (
          <Card title={copy('Characters', '角色生成')} style={{ flex: 1, minHeight: 0, overflow: 'auto' }} styles={{ body: { padding: 12 } }}>
            <div className="flex items-center justify-between mb-3">
              <Space>
                <Button type="primary" disabled={selectedRoleIds.length === 0} onClick={() => generateImages('role')}>
                  {copy('Generate selected images (mock)', '批量生成图片（Mock）')}
                </Button>
                <span className="text-xs text-gray-500">{copy(`${selectedRoleIds.length} selected`, `已选 ${selectedRoleIds.length} 项`)}</span>
              </Space>
              <Space>
                <Button onClick={() => openAddEntity('role')}>{copy('Add manually', '手动添加')}</Button>
                <Button onClick={() => openPickFromAssets('role')}>{copy('Add from assets', '从资产库添加')}</Button>
              </Space>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {roleDrafts.map((r) => (
                <Card
                  key={r.id}
                  size="small"
                  title={
                    <div className="flex items-center gap-2">
                      <Checkbox
                        checked={selectedRoleIds.includes(r.id)}
                        onChange={(e) =>
                          setSelectedRoleIds((prev) =>
                            e.target.checked ? [...prev, r.id] : prev.filter((x) => x !== r.id),
                          )
                        }
                      />
                      <span className="truncate">{r.name}</span>
                    </div>
                  }
                  extra={
                    <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEditEntity('role', r.id)}>
                      {copy('Edit', '编辑')}
                    </Button>
                  }
                >
                  <div className="text-xs text-gray-500 mb-2 line-clamp-2">{r.description || copy('No description', '暂无描述')}</div>
                  <div className="h-32 rounded-md border border-gray-200 bg-gray-50 flex items-center justify-center text-gray-500 text-sm">
                    {r.imageUrl ? copy('Generated (mock)', '已生成（Mock）') : copy('Not generated', '未生成')}
                  </div>
                </Card>
              ))}
            </div>
          </Card>
        )}

        {activeStep === 4 && (
          <Card title={copy('Storyboard preview', '分镜预览')} style={{ flex: 1, minHeight: 0, overflow: 'auto' }} styles={{ body: { padding: 12 } }}>
            <Table<StoryboardDraft>
              rowKey="id"
              dataSource={storyboardDrafts}
              pagination={{ pageSize: 10 }}
              size="small"
              columns={[
                { title: copy('No.', '序号'), dataIndex: 'index', key: 'index', width: 80 },
                { title: copy('Title', '标题'), dataIndex: 'title', key: 'title', ellipsis: true },
                { title: copy('Preview', '预览'), dataIndex: 'preview', key: 'preview', ellipsis: true },
                { title: copy('Paragraphs', '段落'), dataIndex: 'paragraphRange', key: 'paragraphRange', width: 120 },
                {
                  title: copy('Actions', '操作'),
                  key: 'action',
                  width: 90,
                  render: (_, record) => (
                    <Button type="link" size="small" onClick={() => openEditStoryboard(record)}>
                      {copy('Edit', '编辑')}
                    </Button>
                  ),
                },
              ] as TableColumnsType<StoryboardDraft>}
            />
          </Card>
        )}
      </Content>

      <Modal
        title={copy('Edit details', '编辑信息')}
        open={editEntityOpen}
        onCancel={() => {
          setEditEntityOpen(false)
          setEditEntityId(null)
        }}
        onOk={saveEditEntity}
        okText={copy('Save', '保存')}
        width={560}
      >
        <div className="space-y-3">
          <div>
            <span className="text-gray-600 text-sm">{copy('Name', '名称')}</span>
            <Input value={editEntityName} onChange={(e) => setEditEntityName(e.target.value)} className="mt-1" />
          </div>
          <div>
            <span className="text-gray-600 text-sm">{copy('Description', '描述')}</span>
            <Input.TextArea
              value={editEntityDesc}
              onChange={(e) => setEditEntityDesc(e.target.value)}
              rows={6}
              className="mt-1"
            />
          </div>
        </div>
      </Modal>

      <Modal
        title={copy('Add manually', '手动添加')}
        open={addEntityOpen}
        onCancel={() => setAddEntityOpen(false)}
        onOk={addEntity}
        okText={copy('Add', '添加')}
        width={560}
      >
        <div className="space-y-3">
          <div>
            <span className="text-gray-600 text-sm">{copy('Name', '名称')}</span>
            <Input value={addEntityName} onChange={(e) => setAddEntityName(e.target.value)} className="mt-1" />
          </div>
          <div>
            <span className="text-gray-600 text-sm">{copy('Description', '描述')}</span>
            <Input.TextArea
              value={addEntityDesc}
              onChange={(e) => setAddEntityDesc(e.target.value)}
              rows={6}
              className="mt-1"
            />
          </div>
        </div>
      </Modal>

      <Modal
        title={copy('Add from asset library (mock)', '从资产库添加（Mock）')}
        open={pickFromAssetsOpen}
        onCancel={() => setPickFromAssetsOpen(false)}
        onOk={confirmPickFromAssets}
        okText={copy('Add selected', '添加所选')}
        width={560}
      >
        <div className="text-xs text-gray-500 mb-2">{copy('This mock uses the locally saved existing-items set.', '当前数据来自本地“已存在集合”的 Mock。')}</div>
        <Checkbox.Group
          value={pickFromAssetsSelected}
          onChange={(vals) => setPickFromAssetsSelected(vals as string[])}
          className="w-full"
        >
          <div className="space-y-2">
            {(pickFromAssetsKind === 'scene'
              ? existingEntities.scenes
              : pickFromAssetsKind === 'prop'
                ? existingEntities.props
                : existingEntities.roles
            ).map((name) => (
              <div key={name} className="flex items-center justify-between">
                <Checkbox value={name}>{name}</Checkbox>
              </div>
            ))}
          </div>
        </Checkbox.Group>
        {((pickFromAssetsKind === 'scene'
          ? existingEntities.scenes
          : pickFromAssetsKind === 'prop'
            ? existingEntities.props
            : existingEntities.roles
        ).length === 0) && <Empty description={copy('No asset-library items (mock)', '资产库暂无内容（Mock）')} image={Empty.PRESENTED_IMAGE_SIMPLE} />}
      </Modal>

      <Modal
        title={editingStoryboard ? copy(`Edit storyboard: ${editingStoryboard.title}`, `编辑分镜：${editingStoryboard.title}`) : copy('Edit storyboard', '编辑分镜')}
        open={editStoryboardOpen}
        onCancel={() => {
          setEditStoryboardOpen(false)
          setEditingStoryboard(null)
        }}
        onOk={saveStoryboard}
        okText={copy('Save', '保存')}
        width={640}
      >
        <div className="space-y-3">
          <div>
            <span className="text-gray-600 text-sm">{copy('Title', '标题')}</span>
            <Input
              value={editingStoryboard?.title ?? ''}
              onChange={(e) =>
                setEditingStoryboard((prev) => (prev ? { ...prev, title: e.target.value } : prev))
              }
              className="mt-1"
            />
          </div>
          <div>
            <span className="text-gray-600 text-sm">{copy('Preview', '预览')}</span>
            <Input.TextArea
              value={editingStoryboard?.preview ?? ''}
              onChange={(e) =>
                setEditingStoryboard((prev) => (prev ? { ...prev, preview: e.target.value } : prev))
              }
              rows={5}
              className="mt-1"
            />
          </div>
          <div>
            <span className="text-gray-600 text-sm">{copy('Paragraph range', '段落范围')}</span>
            <Input
              value={editingStoryboard?.paragraphRange ?? ''}
              onChange={(e) =>
                setEditingStoryboard((prev) => (prev ? { ...prev, paragraphRange: e.target.value } : prev))
              }
              className="mt-1"
            />
          </div>
        </div>
      </Modal>

      <ChapterRawTextEditorModal
        open={editorModalOpen}
        onClose={() => setEditorModalOpen(false)}
        chapterId={chapterId}
        onSaved={(next) => {
          if (typeof next.rawText === 'string') setRawText(next.rawText)
          if (typeof next.condensedText === 'string') setCondensedText(next.condensedText)
        }}
      />

      {/* 提取结果回显浮窗 */}
      <Modal
        title={copy('Extracted results', '提取结果')}
        open={extractReviewOpen}
        onCancel={() => setExtractReviewOpen(false)}
        width={860}
        footer={
          <Space>
            <Button onClick={() => setExtractReviewOpen(false)}>{copy('Close', '关闭')}</Button>
          </Space>
        }
        styles={{ body: { maxHeight: '70vh', overflow: 'auto' } }}
      >
        <Tabs
          activeKey={extractReviewTab}
          onChange={(k) => setExtractReviewTab(k as EntityKind)}
          items={[
            {
              key: 'roles',
              label: copy(`Characters (${results.roles.length})`, `角色（${results.roles.length})`),
              children: (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-gray-500">{copy('Selected items can be added to the local existing-items set (mock).', '勾选后可添加到“已存在”集合（本地 Mock）。')}</div>
                    <Space size="small">
                      <Button size="small" onClick={() => toggleSelectAllNew('roles')}>
                        {copy('Select all new', '全选新项')}
                      </Button>
                      <Button size="small" type="primary" onClick={() => addSelectedEntities('roles')}>
                        {copy('Add selected', '添加所选')}
                      </Button>
                    </Space>
                  </div>
                  <Checkbox.Group
                    value={selectedEntityKeys.roles}
                    onChange={(vals) => setSelectedEntityKeys((prev) => ({ ...prev, roles: vals as string[] }))}
                    className="w-full"
                  >
                    <List
                      dataSource={results.roles}
                      locale={{ emptyText: <Empty description={copy('No characters', '暂无角色')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                      renderItem={(it) => {
                        const existed = existingSet.roles.has(it.name)
                        return (
                          <List.Item>
                            <div className="flex items-center justify-between w-full">
                              <Checkbox value={it.name}>
                                <span className="font-medium">{it.name}</span>
                                {it.aliases?.length ? (
                                  <span className="text-xs text-gray-500 ml-2">{copy('Aliases: ', '别名：')}{it.aliases.join(' · ')}</span>
                                ) : null}
                              </Checkbox>
                              {existed ? <Tag color="default">{copy('Existing', '已存在')}</Tag> : <Tag color="green">{copy('New', '新')}</Tag>}
                            </div>
                          </List.Item>
                        )
                      }}
                    />
                  </Checkbox.Group>
                </div>
              ),
            },
            {
              key: 'scenes',
              label: copy(`Scenes (${results.scenes.length})`, `场景（${results.scenes.length})`),
              children: (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-gray-500">{copy('Selected items can be added to the local existing-items set (mock).', '勾选后可添加到“已存在”集合（本地 Mock）。')}</div>
                    <Space size="small">
                      <Button size="small" onClick={() => toggleSelectAllNew('scenes')}>
                        {copy('Select all new', '全选新项')}
                      </Button>
                      <Button size="small" type="primary" onClick={() => addSelectedEntities('scenes')}>
                        {copy('Add selected', '添加所选')}
                      </Button>
                    </Space>
                  </div>
                  <Checkbox.Group
                    value={selectedEntityKeys.scenes}
                    onChange={(vals) => setSelectedEntityKeys((prev) => ({ ...prev, scenes: vals as string[] }))}
                    className="w-full"
                  >
                    <List
                      dataSource={results.scenes}
                      locale={{ emptyText: <Empty description={copy('No scenes', '暂无场景')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                      renderItem={(it) => {
                        const existed = existingSet.scenes.has(it.name)
                        return (
                          <List.Item>
                            <div className="flex items-center justify-between w-full">
                              <Checkbox value={it.name}>
                                <span className="font-medium">{it.name}</span>
                                <span className="text-xs text-gray-500 ml-2">
                                  {sceneAttribute(it.indoorOutdoor)} · {sceneAttribute(it.time)}
                                </span>
                              </Checkbox>
                              {existed ? <Tag color="default">{copy('Existing', '已存在')}</Tag> : <Tag color="green">{copy('New', '新')}</Tag>}
                            </div>
                          </List.Item>
                        )
                      }}
                    />
                  </Checkbox.Group>
                </div>
              ),
            },
            {
              key: 'props',
              label: copy(`Props (${results.props.length})`, `道具（${results.props.length})`),
              children: (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="text-xs text-gray-500">{copy('Selected items can be added to the local existing-items set (mock).', '勾选后可添加到“已存在”集合（本地 Mock）。')}</div>
                    <Space size="small">
                      <Button size="small" onClick={() => toggleSelectAllNew('props')}>
                        {copy('Select all new', '全选新项')}
                      </Button>
                      <Button size="small" type="primary" onClick={() => addSelectedEntities('props')}>
                        {copy('Add selected', '添加所选')}
                      </Button>
                    </Space>
                  </div>
                  <Checkbox.Group
                    value={selectedEntityKeys.props}
                    onChange={(vals) => setSelectedEntityKeys((prev) => ({ ...prev, props: vals as string[] }))}
                    className="w-full"
                  >
                    <List
                      dataSource={results.props}
                      locale={{ emptyText: <Empty description={copy('No props', '暂无道具')} image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                      renderItem={(it) => {
                        const existed = existingSet.props.has(it.name)
                        return (
                          <List.Item>
                            <div className="flex items-center justify-between w-full">
                              <Checkbox value={it.name}>
                                <span className="font-medium">{it.name}</span>
                                <span className="text-xs text-gray-500 ml-2">
                                  {copy(`Appears ${it.count} time(s)`, `出现 ${it.count} 次`)}{it.key ? copy(' · Key prop', ' · 关键道具') : ''}
                                </span>
                              </Checkbox>
                              {existed ? <Tag color="default">{copy('Existing', '已存在')}</Tag> : <Tag color="green">{copy('New', '新')}</Tag>}
                            </div>
                          </List.Item>
                        )
                      }}
                    />
                  </Checkbox.Group>
                </div>
              ),
            },
          ]}
        />
      </Modal>
    </Layout>
  )
}

export default ChapterPrep
