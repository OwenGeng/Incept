import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert, Button, Card, Checkbox, Empty, Input, InputNumber, List, Select, Space, Spin, Tabs, Tag, message,
} from 'antd'
import {
  ArrowDownOutlined, ArrowLeftOutlined, ArrowUpOutlined, CheckCircleOutlined, DeleteOutlined,
  PlusOutlined, ReloadOutlined, SaveOutlined, VideoCameraOutlined,
} from '@ant-design/icons'
import { Link, useParams } from 'react-router-dom'
import { useAppStore } from '../../../store/useAppStore'
import {
  approveProductionRevision,
  createEditRevision,
  getDefaultEditDocument,
  listProductionRevisions,
  renderEditRevision,
  type EditDocument,
  type ProductionRevision,
} from '../../../services/productionControl'

const newId = (prefix: string) => `${prefix}-${globalThis.crypto?.randomUUID?.() ?? Date.now().toString(36)}`

const isEditDocument = (value: unknown): value is EditDocument => {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<EditDocument>
  return candidate.schema_version === 1 && Array.isArray(candidate.video_clips) && Boolean(candidate.canvas)
}

const cloneDocument = (value: EditDocument): EditDocument => JSON.parse(JSON.stringify(value)) as EditDocument

const VideoEditor = () => {
  const { projectId } = useParams<{ projectId: string }>()
  const language = useAppStore((state) => state.language)
  const copy = (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english)
  const [document, setDocument] = useState<EditDocument | null>(null)
  const [revision, setRevision] = useState<ProductionRevision | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [renderTaskId, setRenderTaskId] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    setLoadError('')
    try {
      const revisions = await listProductionRevisions(projectId)
      const latestEdit = revisions.find((item) => item.kind === 'edit') ?? null
      const storedTimeline = latestEdit?.payload?.timeline
      if (latestEdit && isEditDocument(storedTimeline)) {
        setDocument(cloneDocument(storedTimeline))
        setRevision(latestEdit)
      } else {
        setDocument(await getDefaultEditDocument(projectId))
        setRevision(null)
      }
      setDirty(false)
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : copy('Could not load the edit.', '无法加载剪辑'))
      setDocument(null)
    } finally {
      setLoading(false)
    }
  }, [language, projectId])

  useEffect(() => { void load() }, [load])

  const mutate = (recipe: (draft: EditDocument) => void) => {
    setDocument((current) => {
      if (!current) return current
      const next = cloneDocument(current)
      recipe(next)
      return next
    })
    setDirty(true)
    setRenderTaskId(null)
  }

  const durationMs = useMemo(() => {
    if (!document) return 0
    const clips = document.video_clips.reduce((total, clip) => total + clip.source_out_ms - clip.source_in_ms, 0)
    const transitions = document.video_clips.slice(0, -1).reduce((total, clip) => total + clip.transition_to_next.duration_ms, 0)
    return clips - transitions
  }, [document])

  const saveDraft = async () => {
    if (!projectId || !document) return
    setSaving(true)
    try {
      const saved = await createEditRevision(projectId, document)
      setRevision(saved)
      setDirty(false)
      message.success(copy(`Edit revision v${saved.revision_number} saved.`, `剪辑版本 v${saved.revision_number} 已保存`))
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not save edit revision.', '无法保存剪辑版本'))
    } finally {
      setSaving(false)
    }
  }

  const approve = async () => {
    if (!projectId || !revision || dirty) return
    setSaving(true)
    try {
      setRevision(await approveProductionRevision(projectId, revision.id))
      message.success(copy('Edit revision approved.', '剪辑版本已批准'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not approve edit.', '无法批准剪辑'))
    } finally {
      setSaving(false)
    }
  }

  const render = async () => {
    if (!projectId || !revision || revision.state !== 'approved' || dirty) return
    setSaving(true)
    try {
      const created = await renderEditRevision(projectId, revision.id)
      setRenderTaskId(created.task_id)
      message.success(copy('Deterministic render queued.', '确定性渲染任务已提交'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not queue render.', '无法提交渲染任务'))
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Spin className="m-8" />

  if (!document) {
    return (
      <ResultCard
        title={copy('The edit cannot be opened', '无法打开剪辑')}
        detail={loadError || copy('Select a take for every shot first.', '请先为每个镜头选择正式视频版本')}
        projectId={projectId}
        onRetry={() => void load()}
      />
    )
  }

  const videoTab = (
    <div className="space-y-3">
      <Alert type="info" showIcon message={copy(
        'Every clip is locked to the explicitly selected take. Change the selected take in the shot workspace.',
        '每个片段都绑定镜头中明确采用的视频版本；如需换片，请回到镜头工作台选择。',
      )} />
      <List
        dataSource={document.video_clips}
        locale={{ emptyText: <Empty description={copy('No selected takes.', '暂无已选视频版本')} /> }}
        renderItem={(clip, index) => (
          <Card key={clip.id} size="small" className="mb-3">
            <div className="flex flex-col xl:flex-row xl:items-center gap-3">
              <div className="min-w-0 flex-1">
                <Space wrap><Tag color="blue">#{index + 1}</Tag><strong>{clip.shot_id}</strong><code>{clip.file_id}</code></Space>
              </div>
              <Space wrap>
                <span>{copy('In', '入点')}</span>
                <InputNumber min={0} step={100} addonAfter="ms" value={clip.source_in_ms} onChange={(value) => mutate((draft) => { draft.video_clips[index].source_in_ms = Number(value ?? 0) })} />
                <span>{copy('Out', '出点')}</span>
                <InputNumber min={1} step={100} addonAfter="ms" value={clip.source_out_ms} onChange={(value) => mutate((draft) => { draft.video_clips[index].source_out_ms = Number(value ?? 1) })} />
                <Checkbox checked={clip.use_source_audio} onChange={(event) => mutate((draft) => { draft.video_clips[index].use_source_audio = event.target.checked })}>{copy('Native audio', '原生音轨')}</Checkbox>
                {clip.use_source_audio ? <InputNumber min={-60} max={12} addonAfter="dB" value={clip.source_audio_volume_db} onChange={(value) => mutate((draft) => { draft.video_clips[index].source_audio_volume_db = Number(value ?? 0) })} /> : null}
                {index < document.video_clips.length - 1 ? (
                  <>
                    <Select
                      value={clip.transition_to_next.type}
                      style={{ width: 130 }}
                      options={['cut', 'fade', 'dissolve', 'wipeleft', 'wiperight', 'slideleft', 'slideright'].map((value) => ({ value, label: value }))}
                      onChange={(value) => mutate((draft) => {
                        draft.video_clips[index].transition_to_next.type = value
                        draft.video_clips[index].transition_to_next.duration_ms = value === 'cut' ? 0 : Math.max(300, draft.video_clips[index].transition_to_next.duration_ms)
                      })}
                    />
                    {clip.transition_to_next.type !== 'cut' ? (
                      <InputNumber min={100} max={3000} step={100} addonAfter="ms" value={clip.transition_to_next.duration_ms} onChange={(value) => mutate((draft) => { draft.video_clips[index].transition_to_next.duration_ms = Number(value ?? 300) })} />
                    ) : null}
                  </>
                ) : null}
                <Button icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => mutate((draft) => {
                  const [item] = draft.video_clips.splice(index, 1); draft.video_clips.splice(index - 1, 0, item)
                })} />
                <Button icon={<ArrowDownOutlined />} disabled={index === document.video_clips.length - 1} onClick={() => mutate((draft) => {
                  const [item] = draft.video_clips.splice(index, 1); draft.video_clips.splice(index + 1, 0, item)
                })} />
              </Space>
            </div>
          </Card>
        )}
      />
    </div>
  )

  const audioTab = (
    <div className="space-y-3">
      <Button icon={<PlusOutlined />} onClick={() => mutate((draft) => draft.audio_clips.push({
        id: newId('audio'), file_id: '', role: 'music', timeline_start_ms: 0,
        source_in_ms: 0, source_out_ms: Math.max(1000, durationMs), volume_db: -6, duck_under_dialogue: false,
      }))}>{copy('Add audio clip', '添加音轨')}</Button>
      {document.audio_clips.map((clip, index) => (
        <Card key={clip.id} size="small">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
            <Input value={clip.file_id} placeholder={copy('Audio file ID', '音频文件 ID')} onChange={(event) => mutate((draft) => { draft.audio_clips[index].file_id = event.target.value })} />
            <Select value={clip.role} options={['dialogue', 'voice_over', 'music', 'sfx'].map((value) => ({ value, label: value }))} onChange={(value) => mutate((draft) => { draft.audio_clips[index].role = value })} />
            <InputNumber className="w-full" min={0} addonAfter={copy('start ms', '开始 ms')} value={clip.timeline_start_ms} onChange={(value) => mutate((draft) => { draft.audio_clips[index].timeline_start_ms = Number(value ?? 0) })} />
            <InputNumber className="w-full" min={-60} max={12} addonAfter="dB" value={clip.volume_db} onChange={(value) => mutate((draft) => { draft.audio_clips[index].volume_db = Number(value ?? 0) })} />
            <InputNumber className="w-full" min={0} addonAfter={copy('in ms', '入点 ms')} value={clip.source_in_ms} onChange={(value) => mutate((draft) => { draft.audio_clips[index].source_in_ms = Number(value ?? 0) })} />
            <InputNumber className="w-full" min={1} addonAfter={copy('out ms', '出点 ms')} value={clip.source_out_ms} onChange={(value) => mutate((draft) => { draft.audio_clips[index].source_out_ms = Number(value ?? 1) })} />
            <Checkbox checked={clip.duck_under_dialogue} disabled={clip.role !== 'music'} onChange={(event) => mutate((draft) => { draft.audio_clips[index].duck_under_dialogue = event.target.checked })}>{copy('Duck under dialogue', '对白时自动压低')}</Checkbox>
            <Button danger icon={<DeleteOutlined />} onClick={() => mutate((draft) => { draft.audio_clips.splice(index, 1) })}>{copy('Remove', '删除')}</Button>
          </div>
        </Card>
      ))}
    </div>
  )

  const subtitlesTab = (
    <div className="space-y-3">
      <Button icon={<PlusOutlined />} onClick={() => mutate((draft) => draft.subtitles.push({ id: newId('subtitle'), start_ms: 0, end_ms: Math.min(2000, durationMs), text: '' }))}>{copy('Add subtitle', '添加字幕')}</Button>
      {document.subtitles.map((cue, index) => (
        <Card key={cue.id} size="small">
          <div className="grid grid-cols-1 xl:grid-cols-[160px_160px_1fr_auto] gap-3">
            <InputNumber className="w-full" min={0} addonAfter="ms" value={cue.start_ms} onChange={(value) => mutate((draft) => { draft.subtitles[index].start_ms = Number(value ?? 0) })} />
            <InputNumber className="w-full" min={1} addonAfter="ms" value={cue.end_ms} onChange={(value) => mutate((draft) => { draft.subtitles[index].end_ms = Number(value ?? 1) })} />
            <Input value={cue.text} placeholder={copy('Exact subtitle text', '准确字幕文案')} onChange={(event) => mutate((draft) => { draft.subtitles[index].text = event.target.value })} />
            <Button danger icon={<DeleteOutlined />} onClick={() => mutate((draft) => { draft.subtitles.splice(index, 1) })} />
          </div>
        </Card>
      ))}
    </div>
  )

  const overlaysTab = (
    <div className="space-y-3">
      <Button icon={<PlusOutlined />} onClick={() => mutate((draft) => draft.overlays.push({ id: newId('overlay'), type: 'cta', text: '', file_id: null, start_ms: 0, end_ms: Math.max(1, durationMs), position: 'bottom', width_percent: 20 }))}>{copy('Add Logo / CTA / Legal / End card', '添加 Logo / CTA / Legal / 尾卡')}</Button>
      {document.overlays.map((overlay, index) => (
        <Card key={overlay.id} size="small">
          <div className="grid grid-cols-1 xl:grid-cols-[130px_1fr_140px_140px_120px_120px_auto] gap-3">
            <Select value={overlay.type} options={['logo', 'cta', 'legal', 'end_card'].map((value) => ({ value, label: value }))} onChange={(value) => mutate((draft) => { draft.overlays[index].type = value })} />
            {overlay.type === 'logo' ? (
              <Input value={overlay.file_id ?? ''} placeholder={copy('Logo image file ID', 'Logo 图片文件 ID')} onChange={(event) => mutate((draft) => { draft.overlays[index].file_id = event.target.value })} />
            ) : (
              <Input value={overlay.text} placeholder={copy('Exact brand copy', '准确品牌文案')} onChange={(event) => mutate((draft) => { draft.overlays[index].text = event.target.value })} />
            )}
            <InputNumber className="w-full" min={0} addonAfter="ms" value={overlay.start_ms} onChange={(value) => mutate((draft) => { draft.overlays[index].start_ms = Number(value ?? 0) })} />
            <InputNumber className="w-full" min={1} addonAfter="ms" value={overlay.end_ms} onChange={(value) => mutate((draft) => { draft.overlays[index].end_ms = Number(value ?? 1) })} />
            <Select value={overlay.position} options={['top', 'center', 'bottom'].map((value) => ({ value, label: value }))} onChange={(value) => mutate((draft) => { draft.overlays[index].position = value })} />
            <InputNumber className="w-full" min={5} max={80} addonAfter="%" value={overlay.width_percent} disabled={overlay.type !== 'logo'} onChange={(value) => mutate((draft) => { draft.overlays[index].width_percent = Number(value ?? 20) })} />
            <Button danger icon={<DeleteOutlined />} onClick={() => mutate((draft) => { draft.overlays.splice(index, 1) })} />
          </div>
        </Card>
      ))}
    </div>
  )

  return (
    <div className="h-full overflow-auto p-4 space-y-4">
      <Card>
        <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
          <div>
            <Space wrap>
              <Link to={`/projects/${projectId}?tab=production`}><Button icon={<ArrowLeftOutlined />}>{copy('Production', '生产控制')}</Button></Link>
              <h2 className="m-0 text-xl font-semibold">{copy('Ad edit', '广告剪辑')}</h2>
              {revision ? <Tag color={revision.state === 'approved' ? 'green' : 'gold'}>v{revision.revision_number} · {revision.state}</Tag> : <Tag>{copy('Unsaved', '未保存')}</Tag>}
              {dirty ? <Tag color="orange">{copy('Unsaved changes', '有未保存修改')}</Tag> : null}
            </Space>
            <div className="mt-2 text-gray-500">{document.video_clips.length} {copy('clips', '个片段')} · {(durationMs / 1000).toFixed(2)}s · {document.canvas.width}×{document.canvas.height} · {document.canvas.fps}fps</div>
          </div>
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => void load()}>{copy('Reload', '重新加载')}</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void saveDraft()}>{copy('Save revision', '保存版本')}</Button>
            <Button icon={<CheckCircleOutlined />} disabled={!revision || revision.state !== 'draft' || dirty} loading={saving} onClick={() => void approve()}>{copy('Approve', '批准')}</Button>
            <Button type="primary" icon={<VideoCameraOutlined />} disabled={!revision || revision.state !== 'approved' || dirty} loading={saving} onClick={() => void render()}>{copy('Render MP4', '渲染 MP4')}</Button>
          </Space>
        </div>
        {renderTaskId ? <Alert className="mt-4" type="success" showIcon message={`${copy('Render task', '渲染任务')}: ${renderTaskId}`} /> : null}
      </Card>

      <Card title={copy('Canvas', '画布')}>
        <Space wrap>
          <InputNumber min={320} max={7680} addonAfter={copy('width', '宽')} value={document.canvas.width} onChange={(value) => mutate((draft) => { draft.canvas.width = Number(value ?? 1920) })} />
          <InputNumber min={320} max={7680} addonAfter={copy('height', '高')} value={document.canvas.height} onChange={(value) => mutate((draft) => { draft.canvas.height = Number(value ?? 1080) })} />
          <InputNumber min={1} max={120} addonAfter="fps" value={document.canvas.fps} onChange={(value) => mutate((draft) => { draft.canvas.fps = Number(value ?? 30) })} />
          <InputNumber min={3} max={20} addonAfter={copy('safe area %', '安全区 %')} value={document.canvas.safe_area_percent} onChange={(value) => mutate((draft) => { draft.canvas.safe_area_percent = Number(value ?? 5) })} />
          <Input value={document.canvas.font_family} addonBefore={copy('Font', '字体')} onChange={(event) => mutate((draft) => { draft.canvas.font_family = event.target.value })} />
          <Input type="color" value={document.canvas.primary_text_color} addonBefore={copy('Text', '文字')} onChange={(event) => mutate((draft) => { draft.canvas.primary_text_color = event.target.value })} />
          <Input style={{ width: 130 }} value={document.canvas.background} onChange={(event) => mutate((draft) => { draft.canvas.background = event.target.value })} />
        </Space>
      </Card>

      <Card>
        <Tabs items={[
          { key: 'video', label: copy('Picture edit', '画面剪辑'), children: videoTab },
          { key: 'audio', label: `${copy('Audio', '音轨')} (${document.audio_clips.length})`, children: audioTab },
          { key: 'subtitles', label: `${copy('Subtitles', '字幕')} (${document.subtitles.length})`, children: subtitlesTab },
          { key: 'overlays', label: `${copy('Brand overlays', '品牌后期')} (${document.overlays.length})`, children: overlaysTab },
        ]} />
      </Card>
    </div>
  )
}

const ResultCard = ({ title, detail, projectId, onRetry }: { title: string; detail: string; projectId?: string; onRetry: () => void }) => (
  <Card className="m-6">
    <Empty description={<div><strong>{title}</strong><div className="mt-2 text-gray-500">{detail}</div></div>}>
      <Space>
        <Button onClick={onRetry}>Retry</Button>
        {projectId ? <Link to={`/projects/${projectId}?tab=production`}><Button type="primary">Production</Button></Link> : null}
      </Space>
    </Empty>
  </Card>
)

export default VideoEditor
