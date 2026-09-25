import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Steps,
  Tag,
  Upload,
} from 'antd'
import { CheckCircleOutlined, LinkOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../../../../../store/useAppStore'
import {
  approveProjectDirection,
  getProjectResearch,
  saveProjectResearch,
  uploadResearchFile,
  type CreativeDirection,
  type ProjectResearch,
  type ResearchFinding,
  type ResearchSource,
} from '../../../../../services/projectResearch'

const makeId = (prefix: string) => `${prefix}_${crypto.randomUUID?.() ?? `${Date.now()}_${Math.random()}`}`

export function ResearchTab({ onResearchChange }: { onResearchChange?: (value: ProjectResearch) => void }) {
  const { message } = AntApp.useApp()
  const { projectId } = useParams<{ projectId: string }>()
  const language = useAppStore((state) => state.language)
  const copy = useCallback(
    (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english),
    [language],
  )
  const [research, setResearch] = useState<ProjectResearch | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [sourceOpen, setSourceOpen] = useState(false)
  const [findingOpen, setFindingOpen] = useState(false)
  const [directionOpen, setDirectionOpen] = useState(false)
  const [briefForm] = Form.useForm()
  const [sourceForm] = Form.useForm()
  const [findingForm] = Form.useForm()
  const [directionForm] = Form.useForm()

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
  const creativeFormatOptions = [
    { value: 'Product demo', label: copy('Product demo', '产品演示') },
    { value: 'UGC / Creator', label: copy('UGC / Creator', 'UGC / 创作者') },
    { value: 'Gameplay capture', label: copy('Gameplay capture', '游戏实录') },
    { value: 'App walkthrough', label: copy('App walkthrough', '应用导览') },
    { value: 'Motion graphics', label: copy('Motion graphics', '动态图形') },
    { value: '3D / CGI', label: '3D / CGI' },
    { value: 'Lifestyle / Live action', label: copy('Lifestyle / Live action', '生活方式 / 真人实拍') },
  ]
  const creativePlaybookOptions = [
    { value: 'Hook & payoff', label: copy('Hook & payoff', '钩子与回报') },
    { value: 'Problem-solution', label: copy('Problem-solution', '问题—解决方案') },
    { value: 'Feature walkthrough', label: copy('Feature walkthrough', '功能讲解') },
    { value: 'Social proof', label: copy('Social proof', '社会证明') },
    { value: 'Offer / promotion', label: copy('Offer / promotion', '优惠 / 促销') },
    { value: 'Before-after', label: copy('Before-after', '前后对比') },
    { value: 'Unboxing', label: copy('Unboxing', '开箱') },
    { value: 'Brand story', label: copy('Brand story', '品牌故事') },
  ]

  const commit = useCallback((value: ProjectResearch) => {
    const normalized = {
      ...value,
      brief: {
        ...value.brief,
        brand_colors: value.brief.brand_colors ?? [],
        brand_font_family: value.brief.brand_font_family || 'Arial',
        safe_area_percent: value.brief.safe_area_percent || 5,
      },
    }
    setResearch(normalized)
    briefForm.setFieldsValue(normalized.brief)
    onResearchChange?.(normalized)
  }, [briefForm, onResearchChange])

  useEffect(() => {
    if (!projectId) return
    setLoading(true)
    getProjectResearch(projectId)
      .then(commit)
      .catch(() => message.error(copy('Could not load project research', '无法加载项目研究资料')))
      .finally(() => setLoading(false))
  }, [commit, copy, message, projectId])

  const persist = async (next: ProjectResearch) => {
    if (!projectId) return
    setSaving(true)
    try {
      const saved = await saveProjectResearch(projectId, {
        entry_mode: next.entry_mode,
        status: next.status,
        brief: next.brief,
        sources: next.sources,
        findings: next.findings,
        creative_directions: next.creative_directions,
        approved_direction_id: next.approved_direction_id,
      })
      commit(saved)
      message.success(copy('Research saved', '研究资料已保存'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not save research', '无法保存研究资料'))
    } finally {
      setSaving(false)
    }
  }

  const activeDirection = useMemo(
    () => research?.creative_directions.find((item) => item.id === research.approved_direction_id),
    [research],
  )

  if (loading) return <div className="flex justify-center py-24"><Spin size="large" /></div>
  if (!research || !projectId) return <Empty description={copy('Research is unavailable', '研究资料不可用')} />

  const workflowIndex = research.status === 'approved' ? 2 : research.creative_directions.length ? 1 : 0

  return (
    <div className="space-y-4 overflow-auto pb-8">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.22em] text-slate-500">{copy('Advertising research', '广告研究')}</div>
            <h2 className="mt-1 text-xl font-semibold">{copy('Build an evidence-backed creative direction', '基于证据建立创意方向')}</h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              {copy('Collect product facts and references first. Production unlocks after a direction is approved.', '先收集产品事实与参考素材，批准创意方向后才能进入制作。')}
            </p>
          </div>
          <Tag color={research.status === 'approved' ? 'success' : 'processing'}>
            {research.status === 'approved' ? copy('Direction approved', '方向已批准') : copy('Research required', '需要研究')}
          </Tag>
        </div>
        <Steps
          className="mt-6"
          current={workflowIndex}
          items={[
            { title: copy('Brief & sources', '简报与素材') },
            { title: copy('Findings & direction', '发现与方向') },
            { title: copy('Approved', '已批准') },
          ]}
        />
      </Card>

      {research.status === 'approved' && activeDirection ? (
        <Alert
          type="success"
          showIcon
          message={copy(`Approved direction: ${activeDirection.name}`, `已批准方向：${activeDirection.name}`)}
          description={activeDirection.rationale || activeDirection.script_direction}
        />
      ) : null}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card title={copy('Product intake', '产品信息')}>
            <Form
              form={briefForm}
              layout="vertical"
              initialValues={research.brief}
              onFinish={(brief) => void persist({ ...research, exists: true, brief, status: research.status === 'approved' ? 'approved' : 'draft' })}
            >
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
                <Input prefix={<LinkOutlined />} placeholder="https://" />
              </Form.Item>
              <Form.Item name="product_name" label={copy('Product / service name', '商品 / 服务名称')} rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="product_description" label={copy('Product truth', '商品真实信息')}>
                <Input.TextArea rows={3} placeholder={copy('What the product actually is and does. Do not add unsupported claims.', '填写商品真实用途和能力，不要添加无依据的宣传。')} />
              </Form.Item>
              <Form.Item name="market" label={copy('Market (optional)', '市场（选填）')}>
                <Input placeholder={copy('For example: US, Japan, Global', '例如：美国、日本、全球')} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name="target_audience" label={copy('Target audience', '目标人群')} rules={[{ required: true }]}>
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="conversion_goal" label={copy('Conversion goal', '转化目标')} rules={[{ required: true }]}>
                    <Input placeholder={copy('Purchase, install, sign up…', '购买、安装、注册……')} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="key_messages" label={copy('Key messages', '核心卖点')}>
                <Select mode="tags" tokenSeparators={[',', '\n']} placeholder={copy('Add one evidence-backed message per tag', '每条填写一个有依据的卖点')} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={8}>
                  <Form.Item name="target_duration_seconds" label={copy('Target duration', '目标时长')} rules={[{ required: true }]}>
                    <InputNumber className="w-full" min={5} max={180} addonAfter="s" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="aspect_ratios" label={copy('Output ratios', '输出画幅')} rules={[{ required: true }]}>
                    <Select mode="multiple" options={['16:9', '9:16', '1:1', '4:3', '3:4', '21:9'].map((value) => ({ value, label: value }))} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="language" label={copy('Language', '语言')} rules={[{ required: true }]}>
                    <Input placeholder="en / zh-CN / ja" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="cta" label="CTA">
                <Input placeholder={copy('Exact call-to-action copy', '准确行动号召文案')} />
              </Form.Item>
              <Form.Item name="legal" label={copy('Legal / disclosure', 'Legal / 免责声明')}>
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item name="required_overlays" label={copy('Required deterministic overlays', '必须确定性渲染的元素')}>
                <Select mode="multiple" options={['logo', 'cta', 'legal', 'end_card'].map((value) => ({ value, label: value }))} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={10}>
                  <Form.Item name="brand_colors" label={copy('Brand colors', '品牌色')}>
                    <Select mode="tags" tokenSeparators={[',', '\n']} placeholder="#FFFFFF" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="brand_font_family" label={copy('Brand font', '品牌字体')}>
                    <Input placeholder="Arial" />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item name="safe_area_percent" label={copy('Safe area', '安全区')}>
                    <InputNumber className="w-full" min={3} max={20} addonAfter="%" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="prohibited_claims" label={copy('Prohibited claims', '禁用表达')}>
                <Select mode="tags" tokenSeparators={[',', '\n']} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name="budget_amount" label={copy('Generation budget', '生成预算')}>
                    <InputNumber className="w-full" min={0} precision={2} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="budget_currency" label={copy('Currency', '币种')}>
                    <Input maxLength={3} placeholder="USD" />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" htmlType="submit" loading={saving}>{copy('Save product intake', '保存产品信息')}</Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card
            title={copy('Reference library', '参考资料库')}
            extra={<Button icon={<PlusOutlined />} onClick={() => setSourceOpen(true)}>{copy('Add link', '添加链接')}</Button>}
          >
            <Upload
              showUploadList={false}
              beforeUpload={(file) => {
                void (async () => {
                  try {
                    const fileId = await uploadResearchFile(projectId, file)
                    const source: ResearchSource = {
                      id: makeId('source'),
                      type: file.type.startsWith('video/') ? 'reference_video' : 'product_asset',
                      title: file.name,
                      file_id: fileId,
                      notes: '',
                      rights_confirmed: true,
                    }
                    const brief = source.type === 'product_asset'
                      ? { ...research.brief, product_asset_file_ids: [...research.brief.product_asset_file_ids, fileId] }
                      : research.brief
                    await persist({ ...research, exists: true, brief, sources: [...research.sources, source] })
                  } catch {
                    message.error(copy('Upload failed', '上传失败'))
                  }
                })()
                return false
              }}
            >
              <Button icon={<UploadOutlined />} className="mb-3">{copy('Upload product, video, or brand asset', '上传产品、视频或品牌素材')}</Button>
            </Upload>
            <Upload
              showUploadList={false}
              accept="image/*"
              beforeUpload={(file) => {
                void (async () => {
                  try {
                    const fileId = await uploadResearchFile(projectId, file)
                    const source: ResearchSource = {
                      id: makeId('source'),
                      type: 'brand_guideline',
                      title: file.name,
                      file_id: fileId,
                      notes: 'Deterministic logo overlay source',
                      rights_confirmed: true,
                    }
                    const brief = { ...research.brief, logo_file_id: fileId }
                    await persist({ ...research, exists: true, brief, sources: [...research.sources, source] })
                  } catch {
                    message.error(copy('Logo upload failed', 'Logo 上传失败'))
                  }
                })()
                return false
              }}
            >
              <Button icon={<UploadOutlined />} className="mb-3 ml-2">{copy('Upload logo', '上传 Logo')}</Button>
            </Upload>
            {research.brief.logo_file_id ? <Tag color="green">Logo: {research.brief.logo_file_id}</Tag> : null}
            <List
              locale={{ emptyText: copy('No references yet', '暂无参考资料') }}
              dataSource={research.sources}
              renderItem={(item) => (
                <List.Item extra={<Tag>{item.type.replaceAll('_', ' ')}</Tag>}>
                  <List.Item.Meta title={item.title} description={item.notes || item.url || item.file_id} />
                </List.Item>
              )}
            />
          </Card>
        </Col>

        <Col xs={24} xl={10}>
          <Card title={copy('Findings', '研究发现')} extra={<Button icon={<PlusOutlined />} onClick={() => setFindingOpen(true)}>{copy('Add finding', '添加发现')}</Button>}>
            <List
              locale={{ emptyText: copy('Document reusable patterns and product evidence.', '记录可复用模式与产品证据。') }}
              dataSource={research.findings}
              renderItem={(item) => <List.Item><List.Item.Meta title={item.title} description={item.observation} /></List.Item>}
            />
          </Card>
        </Col>

        <Col xs={24} xl={14}>
          <Card title={copy('Creative directions', '创意方向')} extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setDirectionOpen(true)}>{copy('Add direction', '添加方向')}</Button>}>
            <List
              locale={{ emptyText: copy('Add a direction after reviewing the evidence.', '审阅证据后添加创意方向。') }}
              dataSource={research.creative_directions}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    research.approved_direction_id === item.id ? (
                      <Tag key="approved" color="success" icon={<CheckCircleOutlined />}>{copy('Approved', '已批准')}</Tag>
                    ) : (
                      <Button
                        key="approve"
                        type="link"
                        onClick={() => {
                          void approveProjectDirection(projectId, item.id)
                            .then((value) => {
                              commit(value)
                              message.success(copy('Creative direction approved', '创意方向已批准'))
                            })
                            .catch((error: unknown) => {
                              message.error(error instanceof Error ? error.message : copy('Could not approve direction', '无法批准创意方向'))
                            })
                        }}
                      >
                        {copy('Approve', '批准')}
                      </Button>
                    ),
                  ]}
                >
                  <List.Item.Meta title={item.name} description={`${item.creative_format} · ${item.creative_playbook}\n${item.visual_direction}`} />
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      <Modal title={copy('Add reference link', '添加参考链接')} open={sourceOpen} onCancel={() => setSourceOpen(false)} footer={null} forceRender>
        <Form form={sourceForm} layout="vertical" onFinish={(values) => {
          const source: ResearchSource = { id: makeId('source'), rights_confirmed: true, notes: '', ...values }
          void persist({ ...research, exists: true, sources: [...research.sources, source] }).then(() => { sourceForm.resetFields(); setSourceOpen(false) })
        }}>
          <Form.Item name="type" label={copy('Source type', '资料类型')} rules={[{ required: true }]}><Select options={[
            { value: 'product_page', label: copy('Product page', '产品页面') },
            { value: 'competitor_video', label: copy('Comparable video', '同类视频') },
            { value: 'reference_video', label: copy('Reference video', '参考视频') },
          ]} /></Form.Item>
          <Form.Item name="title" label={copy('Title', '标题')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="url" label="URL" rules={[{ required: true }, { type: 'url' }]}><Input /></Form.Item>
          <Form.Item name="notes" label={copy('Notes', '备注')}><Input.TextArea rows={3} /></Form.Item>
          <Button type="primary" htmlType="submit">{copy('Add reference', '添加参考')}</Button>
        </Form>
      </Modal>

      <Modal title={copy('Add finding', '添加研究发现')} open={findingOpen} onCancel={() => setFindingOpen(false)} footer={null} forceRender>
        <Form form={findingForm} layout="vertical" onFinish={(values) => {
          const finding: ResearchFinding = { id: makeId('finding'), source_ids: [], ...values }
          void persist({ ...research, exists: true, findings: [...research.findings, finding], status: 'researching' }).then(() => { findingForm.resetFields(); setFindingOpen(false) })
        }}>
          <Form.Item name="title" label={copy('Finding', '发现')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="observation" label={copy('Evidence-backed observation', '有证据支持的观察')} rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item>
          <Form.Item name="source_ids" label={copy('Sources', '证据来源')}><Select mode="multiple" options={research.sources.map((item) => ({ value: item.id, label: item.title }))} /></Form.Item>
          <Button type="primary" htmlType="submit">{copy('Save finding', '保存发现')}</Button>
        </Form>
      </Modal>

      <Modal title={copy('Add creative direction', '添加创意方向')} open={directionOpen} onCancel={() => setDirectionOpen(false)} footer={null} width={680} forceRender>
        <Form form={directionForm} layout="vertical" onFinish={(values) => {
          const direction: CreativeDirection = { id: makeId('direction'), rationale: '', evidence_finding_ids: [], ...values }
          void persist({ ...research, exists: true, creative_directions: [...research.creative_directions, direction], status: 'ready' }).then(() => { directionForm.resetFields(); setDirectionOpen(false) })
        }}>
          <Form.Item name="name" label={copy('Direction name', '方向名称')} rules={[{ required: true }]}><Input /></Form.Item>
          <Row gutter={12}>
            <Col span={12}><Form.Item name="creative_format" label={copy('Creative format', '创意形式')} rules={[{ required: true }]}><Select options={creativeFormatOptions} /></Form.Item></Col>
            <Col span={12}><Form.Item name="creative_playbook" label={copy('Creative playbook', '创意打法')} rules={[{ required: true }]}><Select options={creativePlaybookOptions} /></Form.Item></Col>
          </Row>
          <Form.Item name="visual_direction" label={copy('Visual direction', '视觉方向')} rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="script_direction" label={copy('Script direction', '脚本方向')} rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
          <Form.Item name="rationale" label={copy('Rationale', '理由')}><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="evidence_finding_ids" label={copy('Supporting findings', '支持发现')}><Select mode="multiple" options={research.findings.map((item) => ({ value: item.id, label: item.title }))} /></Form.Item>
          <Button type="primary" htmlType="submit">{copy('Save direction', '保存方向')}</Button>
        </Form>
      </Modal>
    </div>
  )
}
