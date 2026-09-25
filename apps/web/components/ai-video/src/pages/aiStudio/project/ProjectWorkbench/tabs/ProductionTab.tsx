import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Empty, Input, List, Modal, Select, Space, Spin, Steps, Tag, message } from 'antd'
import { CheckCircleOutlined, DownloadOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { Link, useParams } from 'react-router-dom'
import {
  approveProductionRevision,
  confirmVideoGenerationBatch,
  createVideoGenerationBatch,
  createProductionDelivery,
  createProductionRevision,
  getProductionPlan,
  getUsageSummary,
  listGenerationBatches,
  listProductionArtifacts,
  listProductionDeliveries,
  listProductionQAReports,
  listProductionRevisions,
  runProductionQA,
  selectProductionArtifact,
  snapshotShotPlan,
  type ProductionDelivery,
  type ProductionArtifact,
  type ProductionQAReport,
  type ProductionRevision,
  type ProductionRevisionKind,
  type ProductionScopeType,
  type ProductionWorkflowPlan,
  type GenerationBatch,
  type UsageSummary,
  type VideoBatchRequest,
} from '../../../../../services/productionControl'
import { aiVideoApiBase } from '../../../../../runtime'
import { useAppStore } from '../../../../../store/useAppStore'

const STEP_KEYS = ['brief', 'script', 'storyboard', 'keyframes', 'takes', 'edit', 'render', 'qa', 'delivery'] as const

const kindOptions: Array<{ value: ProductionRevisionKind; label: string }> = [
  { value: 'script', label: 'Script' },
  { value: 'shot_plan', label: 'Shot plan' },
  { value: 'keyframe', label: 'Keyframe' },
  { value: 'motion_prompt', label: 'Motion prompt' },
  { value: 'edit', label: 'Edit' },
]

function suggestedKind(action: string): ProductionRevisionKind {
  if (action.includes('shot_plan')) return 'shot_plan'
  if (action.includes('keyframe')) return 'keyframe'
  if (action.includes('edit')) return 'edit'
  return 'script'
}

export const ProductionTab: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>()
  const language = useAppStore((state) => state.language)
  const copy = (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english)
  const [plan, setPlan] = useState<ProductionWorkflowPlan | null>(null)
  const [revisions, setRevisions] = useState<ProductionRevision[]>([])
  const [qaReports, setQaReports] = useState<ProductionQAReport[]>([])
  const [deliveries, setDeliveries] = useState<ProductionDelivery[]>([])
  const [artifacts, setArtifacts] = useState<ProductionArtifact[]>([])
  const [batches, setBatches] = useState<GenerationBatch[]>([])
  const [usage, setUsage] = useState<UsageSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [kind, setKind] = useState<ProductionRevisionKind>('script')
  const [scopeType, setScopeType] = useState<ProductionScopeType>('project')
  const [scopeId, setScopeId] = useState('')
  const [payloadText, setPayloadText] = useState('{}')
  const [scriptFields, setScriptFields] = useState({ hook: '', problem: '', proof: '', payoff: '', cta: '', voiceover: '', timed_beats: '' })
  const [deliveryOpen, setDeliveryOpen] = useState(false)
  const [deliveryFileIds, setDeliveryFileIds] = useState('')
  const [batchOpen, setBatchOpen] = useState(false)
  const [batchPrompt, setBatchPrompt] = useState('')
  const [batchRatio, setBatchRatio] = useState<VideoBatchRequest['items'][number]['ratio']>('16:9')
  const [batchResolution, setBatchResolution] = useState<'360p' | '720p' | '1080p' | '4k'>('720p')
  const [batchReferenceMode, setBatchReferenceMode] = useState<VideoBatchRequest['items'][number]['reference_mode']>('key')
  const [batchPreview, setBatchPreview] = useState<GenerationBatch | null>(null)

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const [nextPlan, nextRevisions, nextQaReports, nextDeliveries, nextBatches, nextUsage, nextArtifacts] = await Promise.all([
        getProductionPlan(projectId),
        listProductionRevisions(projectId),
        listProductionQAReports(projectId),
        listProductionDeliveries(projectId),
        listGenerationBatches(projectId),
        getUsageSummary(projectId),
        listProductionArtifacts(projectId),
      ])
      setPlan(nextPlan)
      setRevisions(nextRevisions)
      setQaReports(nextQaReports)
      setDeliveries(nextDeliveries)
      setBatches(nextBatches)
      setUsage(nextUsage)
      setArtifacts(nextArtifacts)
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not load production state.', '无法加载生产状态'))
    } finally {
      setLoading(false)
    }
  }, [language, projectId])

  useEffect(() => {
    void load()
  }, [load])

  const openCreate = () => {
    const nextKind = suggestedKind(plan?.next_action.type ?? '')
    setKind(nextKind)
    setScopeType(nextKind === 'keyframe' || nextKind === 'motion_prompt' ? 'shot' : 'project')
    setScopeId(plan?.next_action.requested_ids[0] ?? '')
    setPayloadText('{}')
    const latestScript = revisions.find((item) => item.kind === 'script')?.payload ?? {}
    setScriptFields({
      hook: String(latestScript.hook ?? ''),
      problem: String(latestScript.problem ?? ''),
      proof: String(latestScript.proof ?? ''),
      payoff: String(latestScript.payoff ?? ''),
      cta: String(latestScript.cta ?? ''),
      voiceover: String(latestScript.voiceover ?? ''),
      timed_beats: Array.isArray(latestScript.timed_beats)
        ? (latestScript.timed_beats as Array<{ start?: string; end?: string; purpose?: string; copy?: string }>).map((item) => `${item.start ?? ''}-${item.end ?? ''} | ${item.purpose ?? ''} | ${item.copy ?? ''}`).join('\n')
        : '',
    })
    setCreateOpen(true)
  }

  const parseTimedBeats = () => scriptFields.timed_beats
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [range = '', purpose = '', ...copyParts] = line.split('|').map((item) => item.trim())
      const [start = '', end = ''] = range.split('-').map((item) => item.trim())
      return { start, end, purpose, copy: copyParts.join(' | ') }
    })

  const submitCreate = async () => {
    if (!projectId) return
    let payload: Record<string, unknown>
    if (kind === 'script') {
      if (!scriptFields.hook.trim() || !scriptFields.proof.trim() || !scriptFields.cta.trim()) {
        message.error(copy('Hook, proof and CTA are required for an ad script.', '广告脚本必须填写 Hook、Proof 和 CTA。'))
        return
      }
      payload = {
        schema_version: 1,
        format: 'advertising_script',
        hook: scriptFields.hook.trim(),
        problem: scriptFields.problem.trim(),
        proof: scriptFields.proof.trim(),
        payoff: scriptFields.payoff.trim(),
        cta: scriptFields.cta.trim(),
        voiceover: scriptFields.voiceover.trim(),
        timed_beats: parseTimedBeats(),
      }
    } else {
      try {
        payload = JSON.parse(payloadText) as Record<string, unknown>
        if (!payload || Array.isArray(payload) || typeof payload !== 'object') throw new Error('invalid')
      } catch {
        message.error(copy('Payload must be a JSON object.', 'Payload 必须是 JSON 对象'))
        return
      }
    }
    setSaving(true)
    try {
      await createProductionRevision(projectId, {
        kind,
        scope_type: scopeType,
        scope_id: scopeType === 'project' ? null : scopeId.trim(),
        parent_revision_id: revisions.find((item) => item.kind === kind && item.scope_type === scopeType && item.scope_id === (scopeType === 'project' ? projectId : scopeId.trim()))?.id ?? null,
        payload,
      })
      setCreateOpen(false)
      message.success(copy('Draft revision created.', '已创建草稿版本'))
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not create revision.', '创建版本失败'))
    } finally {
      setSaving(false)
    }
  }

  const approve = async (revision: ProductionRevision) => {
    if (!projectId) return
    setSaving(true)
    try {
      await approveProductionRevision(projectId, revision.id)
      message.success(copy('Revision approved.', '版本已批准'))
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not approve revision.', '批准版本失败'))
    } finally {
      setSaving(false)
    }
  }

  const snapshotPlan = async () => {
    if (!projectId) return
    setSaving(true)
    try {
      await snapshotShotPlan(projectId)
      message.success(copy('Shot Plan draft created from persisted shots.', '已从现有镜头生成 Shot Plan 草稿。'))
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not snapshot the Shot Plan.', '无法生成 Shot Plan 快照'))
    } finally {
      setSaving(false)
    }
  }

  const approveRequestedShotPlan = async () => {
    const revisionId = plan?.next_action.requested_ids[0]
    const revision = revisions.find((item) => item.id === revisionId)
    if (revision) await approve(revision)
  }

  const runQa = async () => {
    if (!projectId) return
    const edit = revisions.find((revision) => revision.kind === 'edit' && revision.state === 'approved')
    if (!edit) {
      message.warning(copy('Approve an edit revision first.', '请先批准一个剪辑版本'))
      return
    }
    setSaving(true)
    try {
      const report = await runProductionQA(projectId, edit.id)
      message[report.status === 'passed' ? 'success' : 'warning'](
        report.status === 'passed' ? copy('QA passed.', 'QA 已通过') : copy('QA found blocking problems.', 'QA 发现阻断问题'),
      )
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not run QA.', '无法运行 QA'))
    } finally {
      setSaving(false)
    }
  }

  const submitDelivery = async () => {
    if (!projectId) return
    const edit = revisions.find((revision) => revision.kind === 'edit' && revision.state === 'approved')
    const qa = qaReports.find((report) => report.edit_revision_id === edit?.id && report.status === 'passed')
    const fileIds = deliveryFileIds.split(',').map((value) => value.trim()).filter(Boolean)
    if (!edit || !qa) {
      message.warning(copy('A passing QA report is required.', '需要已通过的 QA 报告'))
      return
    }
    if (!fileIds.length) {
      message.warning(copy('Provide at least one rendered file ID.', '请至少填写一个已渲染文件 ID'))
      return
    }
    setSaving(true)
    try {
      await createProductionDelivery(projectId, {
        edit_revision_id: edit.id,
        qa_report_id: qa.id,
        delivery_type: 'final',
        file_ids: fileIds,
      })
      setDeliveryOpen(false)
      setDeliveryFileIds('')
      message.success(copy('Final delivery created.', '最终交付已创建'))
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not create delivery.', '创建交付失败'))
    } finally {
      setSaving(false)
    }
  }

  const openDelivery = () => {
    const edit = revisions.find((item) => item.kind === 'edit' && item.state === 'approved')
    const renderArtifact = artifacts.find((item) => item.artifact_type === 'render' && item.currency === 'current' && item.source_revision_id === edit?.id && item.file_id)
    setDeliveryFileIds(renderArtifact?.file_id ?? '')
    setDeliveryOpen(true)
  }

  const selectArtifact = async (artifact: ProductionArtifact) => {
    if (!projectId) return
    setSaving(true)
    try {
      await selectProductionArtifact(projectId, artifact.id)
      message.success(copy(
        artifact.artifact_type === 'frame_key' ? 'Keyframe selected and approved.' : 'Frame selected.',
        artifact.artifact_type === 'frame_key' ? '关键帧已选用并批准。' : '帧图片已选用。',
      ))
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not select artifact.', '无法选用产物'))
    } finally {
      setSaving(false)
    }
  }

  const buildBatchRequest = (): VideoBatchRequest => ({
    confirm_cost: false,
    confirmed_by: null,
    items: (plan?.next_action.requested_ids ?? []).map((shotId) => ({
      shot_id: shotId,
      reference_mode: batchReferenceMode,
      prompt: batchPrompt.trim() || null,
      images: [],
      ratio: batchRatio,
      model_id: null,
      provider_params: { resolution: batchResolution, audio: false },
    })),
  })

  const submitBatch = async (confirmCost: boolean) => {
    if (!projectId || !plan?.next_action.requested_ids.length) return
    if (batchReferenceMode === 'text_only' && !batchPrompt.trim()) {
      message.warning(copy('Text-only generation requires a prompt.', '纯文本生成需要填写提示词'))
      return
    }
    setSaving(true)
    try {
      const batch = confirmCost
        ? await (() => {
            const quoteFingerprint = batchPreview?.estimate.quote_fingerprint
            if (!batchPreview || !quoteFingerprint) {
              throw new Error(copy('Run preflight again before confirming.', '请重新运行预检后再确认。'))
            }
            return confirmVideoGenerationBatch(projectId, batchPreview.id, quoteFingerprint)
          })()
        : await createVideoGenerationBatch(projectId, buildBatchRequest())
      setBatchPreview(batch)
      if (batch.status === 'queued') {
        message.success(copy('Batch admitted and queued.', '批次已通过准入并进入队列'))
        setBatchOpen(false)
      } else if (batch.status === 'blocked') {
        message.error(copy('Batch blocked; no generation task was created.', '批次被阻断，未创建任何生成任务'))
      }
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not create batch.', '无法创建批次'))
    } finally {
      setSaving(false)
    }
  }

  const currentStepIndex = useMemo(() => {
    if (!plan) return 0
    const index = STEP_KEYS.indexOf(plan.current_step as (typeof STEP_KEYS)[number])
    return index < 0 ? STEP_KEYS.length : index
  }, [plan])

  if (loading && !plan) {
    return <Spin className="m-8" />
  }

  if (!plan) {
    return <Empty description={copy('Production plan is unavailable.', '生产计划不可用')} />
  }

  return (
    <div className="h-full overflow-auto pb-8 space-y-4">
      <Card
        title={copy('Production control', '生产控制面')}
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
              {copy('Refresh', '刷新')}
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              {copy('New revision', '新建版本')}
            </Button>
            <Link to={`/projects/${projectId}/editor`}>
              <Button>{copy('Open editor', '打开编辑器')}</Button>
            </Link>
          </Space>
        }
      >
        <Steps
          current={currentStepIndex}
          size="small"
          items={STEP_KEYS.map((key) => ({
            title: copy(
              { brief: 'Brief', script: 'Script', storyboard: 'Storyboard', keyframes: 'Keyframes', takes: 'Takes', edit: 'Edit', render: 'Render', qa: 'QA', delivery: 'Delivery' }[key],
              { brief: '简报', script: '脚本', storyboard: '分镜', keyframes: '关键帧', takes: '视频版本', edit: '剪辑', render: '渲染', qa: '质检', delivery: '交付' }[key],
            ),
            status: plan.steps.find((step) => step.key === key)?.complete ? 'finish' : undefined,
          }))}
        />
        <Alert
          className="mt-5"
          type={plan.blockers.length ? 'error' : plan.next_action.type === 'none' ? 'success' : 'info'}
          showIcon
          message={
            plan.next_action.type === 'none'
              ? copy('Production complete', '生产已完成')
              : `${copy('Next action', '下一步')}：${plan.next_action.type}`
          }
          description={
            <div className="space-y-2">
              <div>{plan.next_action.reason}</div>
              {plan.next_action.requested_ids.length ? (
                <div className="flex flex-wrap gap-1">
                  {plan.next_action.requested_ids.map((id) => <Tag key={id}>{id}</Tag>)}
                </div>
              ) : null}
            </div>
          }
          action={
            plan.next_action.type === 'create_edit_revision' || plan.next_action.type === 'render_edit' ? (
              <Link to={`/projects/${projectId}/editor`}>
                <Button size="small" type="primary">{copy('Open editor', '打开编辑器')}</Button>
              </Link>
            ) : plan.next_action.type === 'create_shots' ? (
              <Link to={`/projects/${projectId}?tab=chapters`}>
                <Button size="small" type="primary">{copy('Open chapters', '打开章节')}</Button>
              </Link>
            ) : plan.next_action.type === 'snapshot_shot_plan' ? (
              <Button size="small" type="primary" loading={saving} onClick={() => void snapshotPlan()}>{copy('Snapshot Shot Plan', '生成 Shot Plan 快照')}</Button>
            ) : plan.next_action.type === 'approve_shot_plan_revision' ? (
              <Button size="small" type="primary" loading={saving} onClick={() => void approveRequestedShotPlan()}>{copy('Approve Shot Plan', '批准 Shot Plan')}</Button>
            ) : plan.next_action.type.includes('revision') || plan.next_action.type.includes('keyframe') ? (
              <Button size="small" type="primary" onClick={openCreate}>{copy('Create draft', '创建草稿')}</Button>
            ) : plan.next_action.type === 'run_qa' ? (
              <Button size="small" type="primary" loading={saving} onClick={() => void runQa()}>{copy('Run QA', '运行 QA')}</Button>
            ) : plan.next_action.type === 'create_delivery' ? (
              <Button size="small" type="primary" onClick={openDelivery}>{copy('Create delivery', '创建交付')}</Button>
            ) : plan.next_action.type === 'generate_takes' ? (
              <Button size="small" type="primary" onClick={() => { setBatchPreview(null); setBatchOpen(true) }}>
                {copy('Preflight batch', '批量预检')}
              </Button>
            ) : undefined
          }
        />
      </Card>

      {plan.blockers.length ? (
        <Card title={copy('Blocking problems', '阻断问题')}>
          <List
            dataSource={plan.blockers}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta title={`${item.code}: ${item.message}`} description={`${item.target_type ?? ''} ${item.target_id ?? ''}`} />
                <Tag color="red">{item.severity}</Tag>
              </List.Item>
            )}
          />
        </Card>
      ) : null}

      {plan.artifacts.length ? (
        <Card title={copy('Artifact currency', '产物时效')}>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {plan.artifacts.map((artifact) => (
              <Card key={artifact.artifact_type} size="small" title={artifact.artifact_type}>
                <Space wrap>
                  <Tag color="green">current {artifact.current}</Tag>
                  <Tag color="gold">stale {artifact.stale}</Tag>
                  <Tag>missing {artifact.missing}</Tag>
                  <Tag color="red">blocked {artifact.blocked}</Tag>
                  <Tag color="blue">selected {artifact.selected}</Tag>
                </Space>
              </Card>
            ))}
          </div>
        </Card>
      ) : null}

      {artifacts.some((item) => item.artifact_type.startsWith('frame_')) ? (
        <Card title={copy('Frame candidates', '帧图片候选')}>
          <Alert
            className="mb-3"
            type="info"
            showIcon
            message={copy('Generation creates candidates only. Selecting a keyframe also creates its approved immutable revision.', '生成只会新增候选；明确选用关键帧时才会创建并批准不可变版本。')}
          />
          <List
            dataSource={artifacts.filter((item) => item.artifact_type.startsWith('frame_'))}
            renderItem={(artifact) => (
              <List.Item actions={[
                artifact.file_id ? <a key="preview" href={`${aiVideoApiBase}/api/v1/studio/files/${encodeURIComponent(artifact.file_id)}/download`} target="_blank" rel="noreferrer">{copy('Preview', '预览')}</a> : null,
                <Button key="select" size="small" type={artifact.lifecycle === 'selected' ? 'primary' : 'default'} disabled={!artifact.file_id || artifact.currency === 'blocked' || artifact.currency === 'missing'} loading={saving} onClick={() => void selectArtifact(artifact)}>
                  {artifact.lifecycle === 'selected' ? copy('Selected', '已选用') : copy('Select', '选用')}
                </Button>,
              ].filter(Boolean)}>
                <List.Item.Meta
                  title={<Space wrap><span>{artifact.artifact_type}</span><Tag>{artifact.shot_id}</Tag><Tag color={artifact.lifecycle === 'selected' ? 'green' : 'gold'}>{artifact.lifecycle}</Tag></Space>}
                  description={<code>{artifact.input_fingerprint.slice(0, 16)}</code>}
                />
              </List.Item>
            )}
          />
        </Card>
      ) : null}

      <Card title={copy('Revision history', '版本历史')}>
        <List
          locale={{ emptyText: copy('No production revisions yet.', '暂无生产版本') }}
          dataSource={revisions}
          renderItem={(revision) => (
            <List.Item
              actions={revision.state === 'draft' ? [
                <Button
                  key="approve"
                  size="small"
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  loading={saving}
                  onClick={() => void approve(revision)}
                >
                  {copy('Approve', '批准')}
                </Button>,
              ] : []}
            >
              <List.Item.Meta
                title={
                  <Space wrap>
                    <span>{revision.kind} v{revision.revision_number}</span>
                    <Tag color={revision.state === 'approved' ? 'green' : revision.state === 'superseded' ? 'default' : 'gold'}>
                      {revision.state}
                    </Tag>
                    <Tag>{revision.scope_type}:{revision.scope_id}</Tag>
                  </Space>
                }
                description={<code>{revision.input_fingerprint.slice(0, 16)}</code>}
              />
            </List.Item>
          )}
        />
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title={copy('QA reports', 'QA 报告')}>
          <List
            locale={{ emptyText: copy('No QA reports yet.', '暂无 QA 报告') }}
            dataSource={qaReports}
            renderItem={(report) => (
              <List.Item>
                <List.Item.Meta
                  title={<Space><span>{report.id.slice(0, 8)}</span><Tag color={report.status === 'passed' ? 'green' : 'red'}>{report.status}</Tag></Space>}
                  description={`${report.checks.length} checks · ${report.edit_revision_id.slice(0, 8)}`}
                />
              </List.Item>
            )}
          />
        </Card>
        <Card title={copy('Deliveries', '交付')}>
          <List
            locale={{ emptyText: copy('No deliveries yet.', '暂无交付') }}
            dataSource={deliveries}
            renderItem={(delivery) => (
              <List.Item actions={[
                ...delivery.file_ids.map((fileId) => (
                  <a key={fileId} href={`${aiVideoApiBase}/api/v1/studio/files/${encodeURIComponent(fileId)}/download`} target="_blank" rel="noreferrer">
                    <Button size="small" icon={<DownloadOutlined />}>MP4</Button>
                  </a>
                )),
                <a key="manifest" href={`${aiVideoApiBase}/api/v1/studio/projects/${encodeURIComponent(projectId ?? '')}/production/deliveries/${encodeURIComponent(delivery.id)}/manifest.json`} target="_blank" rel="noreferrer">
                  <Button size="small" icon={<DownloadOutlined />}>Manifest</Button>
                </a>,
                Number((delivery.manifest.sidecars as { subtitle_count?: number } | undefined)?.subtitle_count ?? 0) > 0 ? (
                  <a key="srt" href={`${aiVideoApiBase}/api/v1/studio/projects/${encodeURIComponent(projectId ?? '')}/production/deliveries/${encodeURIComponent(delivery.id)}/subtitles.srt`} target="_blank" rel="noreferrer">
                    <Button size="small" icon={<DownloadOutlined />}>SRT</Button>
                  </a>
                ) : null,
              ].filter(Boolean)}>
                <List.Item.Meta
                  title={<Space><span>{delivery.id.slice(0, 8)}</span><Tag color="blue">{delivery.delivery_type}</Tag></Space>}
                  description={`${delivery.file_ids.length} files · ${delivery.status}`}
                />
              </List.Item>
            )}
          />
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card title={copy('Generation batches', '生成批次')}>
          <List
            locale={{ emptyText: copy('No batches yet.', '暂无批次') }}
            dataSource={batches.slice(0, 10)}
            renderItem={(batch) => (
              <List.Item>
                <List.Item.Meta
                  title={<Space><span>{batch.id.slice(0, 12)}</span><Tag color={batch.status === 'queued' ? 'blue' : batch.status === 'blocked' ? 'red' : 'gold'}>{batch.status}</Tag></Space>}
                  description={`${batch.requested_ids.length} shots · ${batch.estimate.currency ?? '—'} ${batch.estimate.total ?? 'unpriced'}`}
                />
              </List.Item>
            )}
          />
        </Card>
        <Card title={copy('Usage ledger', '用量账本')}>
          {usage && Object.keys(usage.by_currency).length ? (
            <Space direction="vertical">
              {usage.budget ? (
                <Alert
                  type={Number(usage.budget.remaining) < 0 ? 'error' : 'info'}
                  showIcon
                  message={`${copy('Budget remaining', '剩余预算')}: ${usage.budget.currency} ${usage.budget.remaining}`}
                  description={`${copy('Budget', '预算')} ${usage.budget.amount} · ${copy('Committed', '已占用')} ${usage.budget.committed}`}
                />
              ) : null}
              {Object.entries(usage.by_currency).map(([currency, values]) => (
                <div key={currency}><Tag color="blue">{currency}</Tag> {copy('estimated', '预计')} {values.estimated} · {copy('actual', '实际')} {values.actual}</div>
              ))}
              <div className="text-gray-500">{usage.total_entries} {copy('entries', '条记录')} · {usage.unpriced_entries} {copy('unpriced', '条未定价')}</div>
            </Space>
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={copy('No usage yet.', '暂无用量')} />}
        </Card>
      </div>

      <Modal
        title={copy('Create production revision', '创建生产版本')}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={() => void submitCreate()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <div className="space-y-4">
          <div>
            <div className="mb-1 text-sm text-gray-600">{copy('Revision kind', '版本类型')}</div>
            <Select
              className="w-full"
              value={kind}
              options={kindOptions}
              onChange={(value) => {
                setKind(value)
                if (value === 'keyframe' || value === 'motion_prompt') setScopeType('shot')
              }}
            />
          </div>
          <div>
            <div className="mb-1 text-sm text-gray-600">{copy('Scope', '作用域')}</div>
            <Select
              className="w-full"
              value={scopeType}
              options={[
                { value: 'project', label: copy('Project', '项目') },
                { value: 'chapter', label: copy('Chapter', '章节') },
                { value: 'shot', label: copy('Shot', '镜头') },
              ]}
              onChange={setScopeType}
              disabled={kind === 'keyframe' || kind === 'motion_prompt'}
            />
          </div>
          {scopeType !== 'project' ? (
            <div>
              <div className="mb-1 text-sm text-gray-600">{copy('Scope ID', '作用域 ID')}</div>
              <Input value={scopeId} onChange={(event) => setScopeId(event.target.value)} />
            </div>
          ) : null}
          {kind === 'script' ? (
            <div className="space-y-3">
              <Alert type="info" showIcon message={copy('Write the approved ad structure, not a generic prose block.', '按广告结构编写正式脚本，而不是只填一段泛化文案。')} />
              <Input value={scriptFields.hook} onChange={(event) => setScriptFields((value) => ({ ...value, hook: event.target.value }))} placeholder="Hook *" />
              <Input value={scriptFields.problem} onChange={(event) => setScriptFields((value) => ({ ...value, problem: event.target.value }))} placeholder={copy('Problem / tension', '痛点 / 冲突')} />
              <Input.TextArea rows={2} value={scriptFields.proof} onChange={(event) => setScriptFields((value) => ({ ...value, proof: event.target.value }))} placeholder={copy('Product proof *', '商品证明 *')} />
              <Input value={scriptFields.payoff} onChange={(event) => setScriptFields((value) => ({ ...value, payoff: event.target.value }))} placeholder={copy('Payoff / result', '回报 / 结果')} />
              <Input value={scriptFields.cta} onChange={(event) => setScriptFields((value) => ({ ...value, cta: event.target.value }))} placeholder="CTA *" />
              <Input.TextArea rows={3} value={scriptFields.voiceover} onChange={(event) => setScriptFields((value) => ({ ...value, voiceover: event.target.value }))} placeholder={copy('Voice-over / dialogue', '旁白 / 对白')} />
              <Input.TextArea rows={4} value={scriptFields.timed_beats} onChange={(event) => setScriptFields((value) => ({ ...value, timed_beats: event.target.value }))} placeholder={copy('One beat per line: 0-3 | hook | Exact copy', '每行一个节拍：0-3 | hook | 准确文案')} />
            </div>
          ) : (
            <div>
              <div className="mb-1 text-sm text-gray-600">Payload JSON</div>
              <Input.TextArea value={payloadText} onChange={(event) => setPayloadText(event.target.value)} rows={10} />
            </div>
          )}
        </div>
      </Modal>

      <Modal
        title={copy('Video batch preflight', '视频批次预检')}
        open={batchOpen}
        onCancel={() => setBatchOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setBatchOpen(false)}>{copy('Cancel', '取消')}</Button>,
          batchPreview?.status === 'confirmation_required' ? (
            <Button key="confirm" type="primary" danger loading={saving} onClick={() => void submitBatch(true)}>
              {copy('Confirm cost and queue', '确认费用并提交')}
            </Button>
          ) : (
            <Button key="preflight" type="primary" loading={saving} onClick={() => void submitBatch(false)}>
              {copy('Run preflight', '运行预检')}
            </Button>
          ),
        ]}
        destroyOnHidden
      >
        <div className="space-y-4">
          <Alert
            type="info"
            showIcon
            message={copy(
              `${plan.next_action.requested_ids.length} shots will be checked as one all-or-none batch.`,
              `${plan.next_action.requested_ids.length} 个镜头将作为一个全有或全无批次检查。`,
            )}
          />
          <div>
            <div className="mb-1 text-sm text-gray-600">{copy('Reference mode', '参考模式')}</div>
            <Select
              className="w-full"
              value={batchReferenceMode}
              onChange={(value) => {
                setBatchReferenceMode(value)
                setBatchPreview(null)
              }}
              options={[
                { value: 'key', label: copy('Approved keyframe', '已批准关键帧') },
                { value: 'first_last', label: copy('First + last frame', '首帧 + 尾帧') },
                { value: 'first_last_key', label: copy('First + last + key', '首帧 + 尾帧 + 关键帧') },
                { value: 'text_only', label: copy('Text only', '纯文本') },
              ]}
            />
          </div>
          <div>
            <div className="mb-1 text-sm text-gray-600">{copy('Output resolution', '输出分辨率')}</div>
            <Select
              className="w-full"
              value={batchResolution}
              onChange={(value) => {
                setBatchResolution(value)
                setBatchPreview(null)
              }}
              options={['360p', '720p', '1080p', '4k'].map((value) => ({ value, label: value }))}
            />
            <div className="mt-1 text-xs text-gray-500">
              {copy('Resolution is sent explicitly so the catalog estimate matches the requested output tier.', '系统会明确提交分辨率，使目录估算与所选输出档位一致。')}
            </div>
          </div>
          <div>
            <div className="mb-1 text-sm text-gray-600">{copy('Aspect ratio', '画幅比例')}</div>
            <Select
              className="w-full"
              value={batchRatio}
              onChange={(value) => {
                setBatchRatio(value)
                setBatchPreview(null)
              }}
              options={['16:9', '9:16', '1:1', '4:3', '3:4', '21:9'].map((value) => ({ value, label: value }))}
            />
          </div>
          <div>
            <div className="mb-1 text-sm text-gray-600">{copy('Shared motion direction (optional)', '统一运动补充（可选）')}</div>
            <Input.TextArea
              rows={3}
              value={batchPrompt}
              onChange={(event) => {
                setBatchPrompt(event.target.value)
                setBatchPreview(null)
              }}
            />
          </div>
          {batchPreview ? (
            <Alert
              type={batchPreview.status === 'blocked' ? 'error' : 'warning'}
              showIcon
              message={batchPreview.status}
              description={
                batchPreview.status === 'blocked'
                  ? JSON.stringify(batchPreview.admission.blockers ?? [], null, 2)
                  : (
                    <div className="space-y-1">
                      <div>{`${copy('Estimated cost', '预计费用')}: ${batchPreview.estimate.currency ?? '—'} ${batchPreview.estimate.total ?? copy('unpriced', '未定价')}`}</div>
                      {(batchPreview.estimate.items ?? []).some((item) => Array.isArray(item.exclusions) && item.exclusions.length > 0) ? (
                        <div className="text-xs">
                          {copy('Official catalog media-output estimate; input and text-output tokens are excluded. Provider-reported billing remains the actual cost.', '官方目录的媒体输出估算；不含输入与文本输出 Token。实际费用仍以 Provider 回传账单为准。')}
                        </div>
                      ) : null}
                    </div>
                  )
              }
            />
          ) : null}
        </div>
      </Modal>

      <Modal
        title={copy('Create final delivery', '创建最终交付')}
        open={deliveryOpen}
        onCancel={() => setDeliveryOpen(false)}
        onOk={() => void submitDelivery()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Alert
          type="info"
          showIcon
          message={copy('Use file IDs produced by the deterministic render pipeline.', '请填写确定性渲染管线产生的文件 ID。')}
          className="mb-4"
        />
        <Input.TextArea
          rows={4}
          value={deliveryFileIds}
          onChange={(event) => setDeliveryFileIds(event.target.value)}
          placeholder={copy('Comma-separated file IDs', '多个文件 ID 用英文逗号分隔')}
        />
      </Modal>
    </div>
  )
}
