import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Checkbox, Form, Input, List, Modal, Select, Space, Tabs, Tag, Typography } from 'antd'
import { ApiOutlined, CloudDownloadOutlined, ImportOutlined, KeyOutlined, PlusOutlined } from '@ant-design/icons'
import { useAppStore } from '../../../store/useAppStore'
import {
  createAutomationKey,
  createCustomEndpoint,
  executeComfyWorkflow,
  executeCustomEndpoint,
  importComfyWorkflow,
  installMarketEntry,
  listAutomationKeys,
  listComfyWorkflows,
  listCustomEndpoints,
  listMarketEntries,
  mcpEndpointUrl,
  previewEndpointExecution,
  publishMarketEntry,
  revokeAutomationKey,
  updateCustomEndpoint,
  validateCustomEndpoint,
  type AutomationKey,
  type ComfyWorkflow,
  type CustomEndpoint,
  type MarketEntry,
} from '../../../services/integrationHub'

const parseObject = (value: string, label: string): Record<string, unknown> => {
  const parsed = JSON.parse(value || '{}') as unknown
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error(`${label} must be a JSON object`)
  return parsed as Record<string, unknown>
}

export default function IntegrationsTab() {
  const { message } = AntApp.useApp()
  const language = useAppStore((state) => state.language)
  const copy = (en: string, zh: string) => language === 'zh-CN' ? zh : en
  const [endpoints, setEndpoints] = useState<CustomEndpoint[]>([])
  const [workflows, setWorkflows] = useState<ComfyWorkflow[]>([])
  const [market, setMarket] = useState<MarketEntry[]>([])
  const [keys, setKeys] = useState<AutomationKey[]>([])
  const [modal, setModal] = useState<'endpoint' | 'comfy' | 'run-comfy' | 'market' | 'key' | null>(null)
  const [runningWorkflow, setRunningWorkflow] = useState<ComfyWorkflow | null>(null)
  const [editingEndpoint, setEditingEndpoint] = useState<CustomEndpoint | null>(null)
  const [result, setResult] = useState('')
  const [issuedToken, setIssuedToken] = useState('')
  const [publicMcpUrl, setPublicMcpUrl] = useState(mcpEndpointUrl)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    try {
      const [endpointRows, workflowRows, marketRows, keyRows] = await Promise.all([
        listCustomEndpoints(), listComfyWorkflows(), listMarketEntries(), listAutomationKeys(),
      ])
      setEndpoints(endpointRows); setWorkflows(workflowRows); setMarket(marketRows); setKeys(keyRows)
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not load integrations.', '无法加载集成配置。'))
    }
  }, [language, message])

  useEffect(() => { void load() }, [load])
  useEffect(() => { setPublicMcpUrl(new URL(mcpEndpointUrl, window.location.origin).toString()) }, [])

  const open = (kind: typeof modal) => {
    form.resetFields(); setResult(''); setIssuedToken(''); setEditingEndpoint(null); setModal(kind)
    if (kind === 'endpoint') form.setFieldsValue({ category: 'video', status: 'draft', auth_type: 'none', auth_header: 'Authorization', request_contract: '{\n  "method": "POST",\n  "path": "/user-confirmed-path",\n  "body_template": {"prompt": "${input.prompt}"}\n}', response_contract: '{\n  "output_path": "data.url",\n  "job_id_path": "data.job_id",\n  "error_path": "error.message"\n}', polling_contract: '{}', capabilities: '{}' })
    if (kind === 'comfy') form.setFieldsValue({ workflow: '{}', input_schema: '{}', bindings: '{}', status: 'draft' })
    if (kind === 'run-comfy') form.setFieldsValue({ input: '{}', persist_output: false })
    if (kind === 'market') form.setFieldsValue({ publisher: 'Local', trust_level: 'local', status: 'published', version: '1.0.0', categories: ['workflow'], template: '{}', credential_destination: 'Environment variable on the Incept API host' })
    if (kind === 'key') form.setFieldsValue({ scopes: ['read:production', 'read:memory'] })
  }

  const openEndpoint = (endpoint?: CustomEndpoint) => {
    form.resetFields(); setResult(''); setIssuedToken(''); setEditingEndpoint(endpoint ?? null); setModal('endpoint')
    form.setFieldsValue(endpoint ? {
      name: endpoint.name,
      category: endpoint.category,
      base_url: endpoint.base_url,
      status: endpoint.status,
      auth_type: endpoint.auth_type,
      auth_header: endpoint.auth_header,
      credential_env: endpoint.credential_env,
      request_contract: JSON.stringify(endpoint.request_contract, null, 2),
      response_contract: JSON.stringify(endpoint.response_contract, null, 2),
      polling_contract: JSON.stringify(endpoint.polling_contract, null, 2),
      capabilities: JSON.stringify(endpoint.capabilities, null, 2),
    } : { category: 'video', status: 'draft', auth_type: 'none', auth_header: 'Authorization', request_contract: '{\n  "method": "POST",\n  "path": "/user-confirmed-path",\n  "body_template": {"prompt": "${input.prompt}"}\n}', response_contract: '{\n  "output_path": "data.url",\n  "job_id_path": "data.job_id",\n  "error_path": "error.message"\n}', polling_contract: '{}', capabilities: '{}' })
  }

  const submit = async () => {
    try {
      const values = await form.validateFields()
      if (modal === 'endpoint') {
        const endpointValue = {
          name: values.name, category: values.category, base_url: values.base_url, status: values.status,
          auth_type: values.auth_type, auth_header: values.auth_header, credential_env: values.credential_env || null,
          request_contract: parseObject(values.request_contract, 'Request contract'),
          response_contract: parseObject(values.response_contract, 'Response contract'),
          polling_contract: parseObject(values.polling_contract, 'Polling contract'),
          capabilities: parseObject(values.capabilities, 'Capabilities'),
        }
        if (editingEndpoint) await updateCustomEndpoint(editingEndpoint.id, endpointValue)
        else await createCustomEndpoint(endpointValue)
      } else if (modal === 'comfy') {
        await importComfyWorkflow({ name: values.name, description: values.description || '', endpoint_id: values.endpoint_id || null, workflow: parseObject(values.workflow, 'Workflow'), input_schema: parseObject(values.input_schema, 'Input schema'), bindings: parseObject(values.bindings, 'Bindings'), status: values.status })
      } else if (modal === 'run-comfy' && runningWorkflow) {
        const execution = await executeComfyWorkflow(runningWorkflow.id, {
          input: parseObject(values.input, 'Input'),
          confirm_external_call: true,
          wait_for_result: true,
          persist_output: Boolean(values.persist_output),
          project_id: values.project_id || null,
          shot_id: values.shot_id || null,
          artifact_type: values.artifact_type || null,
        })
        setResult(JSON.stringify(execution, null, 2))
        setModal(null)
        return
      } else if (modal === 'market') {
        await publishMarketEntry({ ...values, template: parseObject(values.template, 'Template'), source_url: values.source_url || null })
      } else if (modal === 'key') {
        const created = await createAutomationKey(values.name, values.scopes)
        setIssuedToken(created.token)
        await load()
        return
      }
      setModal(null); message.success(copy('Saved.', '已保存。')); await load()
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(error instanceof Error ? error.message : copy('Save failed.', '保存失败。'))
    }
  }

  const endpointPane = <div className="space-y-3 p-4 overflow-auto">
    <Alert showIcon type="info" message={copy('Credentials are referenced by server environment-variable name and are never stored in endpoint templates.', '凭证只引用服务端环境变量名，不会写入 endpoint 模板。')} />
    <Button type="primary" icon={<PlusOutlined />} onClick={() => openEndpoint()}>{copy('New endpoint', '新建 endpoint')}</Button>
    <List dataSource={endpoints} locale={{ emptyText: copy('No custom endpoints.', '暂无自定义 endpoint。') }} renderItem={(item) => <Card size="small" className="mb-3">
      <div className="flex justify-between gap-3"><div><strong>{item.name}</strong><div className="text-xs text-slate-500">{item.base_url} · v{item.config_version}</div></div><Space><Tag>{item.category}</Tag><Tag color={item.status === 'active' ? 'green' : 'gold'}>{item.status}</Tag></Space></div>
      <Space className="mt-3" wrap>
        <Button size="small" onClick={() => openEndpoint(item)}>{copy('Edit', '编辑')}</Button>
        <Button size="small" onClick={async () => { try { setResult(JSON.stringify(await previewEndpointExecution(item.id, { prompt: 'Preview only' }), null, 2)) } catch (e) { message.error(String(e)) } }}>{copy('Preview request', '预览请求')}</Button>
        <Button size="small" onClick={async () => { try { setResult(JSON.stringify(await validateCustomEndpoint(item.id, { data: { url: 'https://example.test/output.mp4' } }), null, 2)) } catch (e) { message.error(e instanceof Error ? e.message : String(e)) } }}>{copy('Offline response check', '离线响应校验')}</Button>
        <Button size="small" danger onClick={() => Modal.confirm({ title: copy('Call this external endpoint?', '确认调用此外部 endpoint？'), content: copy('This sends the preview prompt to the configured third party and may incur cost.', '这会把测试提示词发送给已配置的第三方，并可能产生费用。'), okText: copy('Call endpoint', '确认调用'), onOk: async () => { try { setResult(JSON.stringify(await executeCustomEndpoint(item.id, { prompt: 'Connectivity test' }), null, 2)) } catch (e) { message.error(e instanceof Error ? e.message : String(e)) } } })}>{copy('Live test', '真实测试')}</Button>
      </Space>
    </Card>} />
    {result ? <Input.TextArea rows={8} value={result} readOnly /> : null}
  </div>

  const comfyPane = <div className="space-y-3 p-4 overflow-auto">
    <Alert showIcon type="info" message={copy('Import API-format or UI-format workflow JSON, then bind semantic inputs to node fields. No ComfyUI path is guessed.', '导入 API 或 UI 格式 workflow JSON，再把语义输入绑定到节点字段；系统不会猜测 ComfyUI 路径。')} />
    <Button type="primary" icon={<ImportOutlined />} onClick={() => open('comfy')}>{copy('Import workflow', '导入 workflow')}</Button>
    <List dataSource={workflows} locale={{ emptyText: copy('No workflows imported.', '暂无 workflow。') }} renderItem={(item) => <List.Item actions={[<Button key="preview" size="small" onClick={async () => { try { setResult(JSON.stringify(await executeComfyWorkflow(item.id, { input: {}, confirm_external_call: false, persist_output: false }), null, 2)) } catch (e) { message.error(e instanceof Error ? e.message : String(e)) } }}>{copy('Preview bound workflow', '预览绑定结果')}</Button>, <Button key="run" size="small" type="primary" disabled={item.status !== 'ready' || !item.endpoint_id} onClick={() => { setRunningWorkflow(item); open('run-comfy') }}>{copy('Run', '执行')}</Button>]}><List.Item.Meta title={`${item.name} · v${item.version}`} description={JSON.stringify(item.capabilities)} /><Space><Tag>{item.status}</Tag>{item.endpoint_id ? <Tag color="blue">endpoint</Tag> : null}</Space></List.Item>} />
    {result ? <Input.TextArea rows={10} value={result} readOnly /> : null}
  </div>

  const marketPane = <div className="space-y-3 p-4 overflow-auto">
    <Alert showIcon type="warning" message={copy('Market entries are reviewable templates, not trusted code. Inspect source, credential destination, and request mappings before installation.', 'Market 条目是可审阅模板，不是可信代码；安装前检查来源、凭证去向和请求映射。')} />
    <Button type="primary" icon={<PlusOutlined />} onClick={() => open('market')}>{copy('Publish local template', '发布本地模板')}</Button>
    <List dataSource={market} locale={{ emptyText: copy('The endpoint market is empty.', 'Endpoint market 为空。') }} renderItem={(item) => <List.Item actions={[<Button key="install" icon={<CloudDownloadOutlined />} disabled={item.status !== 'published'} onClick={async () => { try { await installMarketEntry(item.id); message.success(copy('Installed as an editable local copy.', '已安装为可编辑本地副本。')); await load() } catch (e) { message.error(e instanceof Error ? e.message : String(e)) } }}>{copy('Install', '安装')}</Button>]}><List.Item.Meta title={<Space><span>{item.name}</span><Tag>{item.trust_level}</Tag></Space>} description={`${item.publisher} · ${item.version} · ${item.credential_destination}`} /></List.Item>} />
  </div>

  const automationPane = <div className="space-y-3 p-4 overflow-auto">
    <Alert showIcon type="info" message={<span>MCP Streamable HTTP: <Typography.Text copyable code>{publicMcpUrl}</Typography.Text></span>} description={copy('External agents use scoped API keys and the same WorkflowPlan, revision, artifact, and memory contracts as the UI.', '外部 Agent 使用带 scope 的 API Key，并与 UI 共用 WorkflowPlan、版本、产物和记忆合同。')} />
    <Button type="primary" icon={<KeyOutlined />} onClick={() => open('key')}>{copy('Create API key', '创建 API Key')}</Button>
    <List dataSource={keys} locale={{ emptyText: copy('No automation keys.', '暂无自动化 Key。') }} renderItem={(item) => <List.Item actions={[item.status === 'active' ? <Button key="revoke" danger size="small" onClick={async () => { await revokeAutomationKey(item.id); await load() }}>{copy('Revoke', '撤销')}</Button> : null]}><List.Item.Meta title={`${item.name} · ${item.key_prefix}…`} description={item.scopes.join(', ')} /><Tag color={item.status === 'active' ? 'green' : 'default'}>{item.status}</Tag></List.Item>} />
  </div>

  return <div className="h-full overflow-hidden bg-white"><Tabs className="h-full" items={[
    { key: 'endpoints', label: <span><ApiOutlined /> {copy('Endpoints', 'Endpoints')}</span>, children: endpointPane },
    { key: 'comfy', label: 'ComfyUI', children: comfyPane },
    { key: 'market', label: copy('Endpoint market', 'Endpoint market'), children: marketPane },
    { key: 'automation', label: copy('MCP & external agents', 'MCP 与外部 Agent'), children: automationPane },
  ]} />
    <Modal forceRender title={modal === 'endpoint' && editingEndpoint ? copy('Edit endpoint', '编辑 endpoint') : modal} open={modal != null} onCancel={() => setModal(null)} onOk={() => issuedToken ? setModal(null) : void submit()} okText={issuedToken ? copy('Done', '完成') : modal === 'run-comfy' ? copy('Confirm and run', '确认并执行') : copy('Save', '保存')} cancelButtonProps={issuedToken ? { style: { display: 'none' } } : undefined} width={760}>
      {issuedToken ? <Alert type="success" showIcon message={copy('Copy this token now; it will not be shown again.', '请立即复制 Token；之后不会再次显示。')} description={<Typography.Text copyable code>{issuedToken}</Typography.Text>} /> : <Form form={form} layout="vertical">
        {modal === 'endpoint' ? <>
          <Space className="w-full" align="start"><Form.Item name="name" label={copy('Name', '名称')} rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="category" label={copy('Category', '类别')} rules={[{ required: true }]}><Select style={{ width: 140 }} options={['text','image','video','speech','music','workflow'].map(value => ({ value }))} /></Form.Item><Form.Item name="status" label={copy('Status', '状态')}><Select style={{ width: 120 }} options={['draft','testing','active','disabled'].map(value => ({ value }))} /></Form.Item></Space>
          <Form.Item name="base_url" label="Base URL" rules={[{ required: true }, { type: 'url' }]}><Input placeholder="https://…" /></Form.Item>
          <Space align="start"><Form.Item name="auth_type" label={copy('Auth', '鉴权')}><Select style={{ width: 130 }} options={['none','bearer','header'].map(value => ({ value }))} /></Form.Item><Form.Item name="auth_header" label={copy('Header', '请求头')}><Input /></Form.Item><Form.Item name="credential_env" label={copy('Credential env', '凭证环境变量')}><Input placeholder="MY_ENDPOINT_TOKEN" /></Form.Item></Space>
          <Form.Item name="request_contract" label={copy('Request contract JSON', '请求合同 JSON')} rules={[{ required: true }]}><Input.TextArea rows={7} /></Form.Item>
          <Form.Item name="response_contract" label={copy('Response mapping JSON', '响应映射 JSON')} rules={[{ required: true }]}><Input.TextArea rows={5} /></Form.Item>
          <Form.Item name="polling_contract" label={copy('Polling contract JSON (optional)', '轮询合同 JSON（可选）')} tooltip={copy('Use ${input.job_id} in the explicit path or body. The system never guesses a polling route.', '在明确路径或请求体中使用 ${input.job_id}；系统不会猜测轮询路由。')}><Input.TextArea rows={5} /></Form.Item>
          <Form.Item name="capabilities" label={copy('Capabilities JSON', '能力 JSON')}><Input.TextArea rows={3} /></Form.Item>
        </> : null}
        {modal === 'comfy' ? <><Form.Item name="name" label={copy('Name', '名称')} rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="endpoint_id" label={copy('Execution endpoint', '执行 endpoint')}><Select allowClear options={endpoints.map(item => ({ value: item.id, label: item.name }))} /></Form.Item><Form.Item name="workflow" label="Workflow JSON" rules={[{ required: true }]}><Input.TextArea rows={10} /></Form.Item><Form.Item name="input_schema" label="Input schema JSON"><Input.TextArea rows={4} /></Form.Item><Form.Item name="bindings" label="Node bindings JSON"><Input.TextArea rows={4} /></Form.Item><Form.Item name="status" label={copy('Status', '状态')}><Select options={['draft','ready','disabled'].map(value => ({ value }))} /></Form.Item></> : null}
        {modal === 'run-comfy' ? <>
          <Alert showIcon type="warning" className="mb-3" message={copy('This performs a real external call and may incur cost.', '这会执行真实外部调用，并可能产生费用。')} />
          <Form.Item name="input" label={copy('Semantic input JSON', '语义输入 JSON')} rules={[{ required: true }]}><Input.TextArea rows={8} placeholder={'{"prompt":"Product on a clean studio background"}'} /></Form.Item>
          <Form.Item name="persist_output" valuePropName="checked"><Checkbox>{copy('Download completed output into the Incept asset library and create a candidate artifact', '将完成的输出下载到 Incept 素材库并创建候选产物')}</Checkbox></Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, next) => prev.persist_output !== next.persist_output}>{({ getFieldValue }) => getFieldValue('persist_output') ? <><Form.Item name="project_id" label="Project ID" rules={[{ required: true }]}><Input /></Form.Item><Space align="start"><Form.Item name="shot_id" label="Shot ID"><Input /></Form.Item><Form.Item name="artifact_type" label={copy('Artifact type', '产物类型')}><Input placeholder="render / keyframe" /></Form.Item></Space></> : null}</Form.Item>
        </> : null}
        {modal === 'market' ? <><Form.Item name="name" label={copy('Name', '名称')} rules={[{ required: true }]}><Input /></Form.Item><Space><Form.Item name="publisher" label={copy('Publisher', '发布者')}><Input /></Form.Item><Form.Item name="trust_level" label={copy('Trust', '信任级别')}><Select style={{ width: 130 }} options={['local','reviewed','unverified'].map(value => ({ value }))} /></Form.Item><Form.Item name="version" label={copy('Version', '版本')}><Input /></Form.Item></Space><Form.Item name="credential_destination" label={copy('Credential destination', '凭证去向')} rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="source_url" label={copy('Source URL', '来源 URL')}><Input /></Form.Item><Form.Item name="template" label={copy('Install template JSON', '安装模板 JSON')}><Input.TextArea rows={10} /></Form.Item><Form.Item name="categories" hidden><Input /></Form.Item><Form.Item name="status" hidden><Input /></Form.Item></> : null}
        {modal === 'key' ? <><Form.Item name="name" label={copy('Key name', 'Key 名称')} rules={[{ required: true }]}><Input /></Form.Item><Form.Item name="scopes" label="Scopes" rules={[{ required: true }]}><Select mode="multiple" options={['read:production','write:production','read:memory','write:memory'].map(value => ({ value }))} /></Form.Item></> : null}
      </Form>}
    </Modal>
  </div>
}
