import { useEffect, useState, useMemo } from 'react'
import {
  Alert,
  Layout,
  Input,
  Button,
  Table,
  Tag,
  Space,
  Tree,
  Card,
  Dropdown,
  Drawer,
  Modal,
  Form,
  Select,
  message,
  Tooltip,
  Empty,
  Grid,
} from 'antd'
import type { TableColumnsType } from 'antd'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CopyOutlined,
  MenuOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  DownOutlined,
  RightOutlined,
  ThunderboltOutlined,
  CheckCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { LlmService } from '../../../services/generated/services/LlmService'
import type {
  ModelRead,
  ModelCategoryKey,
  ProviderRead,
  ProviderSupportedRead,
} from '../../../services/generated'
import {
  MODEL_CATEGORIES,
  TABLE_ACTION_BTN_EDIT_CLASS,
  TABLE_ACTION_BTN_MORE_CLASS,
  TABLE_ACTION_BTN_TEST_CLASS,
  categoryColorMap,
} from './constants'
import { useAppStore } from '../../../store/useAppStore'

export default function ModelsTab() {
  const language = useAppStore((state) => state.language)
  const copy = (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english)
  const categoryLabel = (category: ModelCategoryKey) => {
    const labels: Record<ModelCategoryKey, [string, string]> = {
      text: ['Text generation', '文本生成'],
      image: ['Image generation', '图片生成'],
      video: ['Video generation', '视频生成'],
      speech: ['Voice generation', '配音生成'],
      music: ['Background music', '背景音乐'],
    }
    return copy(...labels[category])
  }
  const sortOptions = [
    { value: 'updated', label: copy('Recently updated', '最近更新') },
    { value: 'name', label: copy('Name', '名称') },
    { value: 'category', label: copy('Category', '类别') },
  ]
  const [providers, setProviders] = useState<ProviderRead[]>([])
  const [supportedProviders, setSupportedProviders] = useState<ProviderSupportedRead[]>([])
  const [models, setModels] = useState<ModelRead[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<'updated' | 'name' | 'category'>('updated')
  const [viewMode, setViewMode] = useState<'table' | 'card'>('table')
  const [selectedModel, setSelectedModel] = useState<ModelRead | null>(null)
  const [detailPanelOpen, setDetailPanelOpen] = useState(false)
  const [treeCollapsed, setTreeCollapsed] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState<ModelCategoryKey | null>(null)
  const [modelModalOpen, setModelModalOpen] = useState(false)
  const [modelEditing, setModelEditing] = useState<ModelRead | null>(null)
  const [providerOptionsLoading, setProviderOptionsLoading] = useState(true)
  const [updatingCatalogModelId, setUpdatingCatalogModelId] = useState<string | null>(null)
  const [form] = Form.useForm()
  const selectedFormCategory = Form.useWatch<ModelCategoryKey | undefined>('category', form)
  const { lg } = Grid.useBreakpoint()
  const isLargeScreen = lg ?? false

  const load = async () => {
    setLoading(true)
    try {
      const [provRes, modelsRes, supportedRes] = await Promise.all([
        LlmService.listProvidersApiV1LlmProvidersGet({ page: 1, pageSize: 100 }),
        LlmService.listModelsApiV1LlmModelsGet({
          q: search.trim() || undefined,
          order: sortBy === 'name' ? 'name' : sortBy === 'category' ? 'category' : 'updated_at',
          isDesc: true,
          page: 1,
          pageSize: 100,
        }),
        LlmService.listSupportedProvidersApiV1LlmProvidersSupportedGet({}),
      ])
      setProviders(provRes.data?.items ?? [])
      setModels(modelsRes.data?.items ?? [])
      setSupportedProviders(supportedRes.data ?? [])
    } catch {
      message.error(copy('Could not load models', '加载失败'))
    } finally {
      setLoading(false)
      setProviderOptionsLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [search, sortBy])

  const modelList = useMemo(() => {
    let list = models
    if (categoryFilter) list = list.filter((m) => m.category === categoryFilter)
    return list
  }, [models, categoryFilter])

  const categoryCounts = useMemo(() => {
    const c: Record<string, number> = {}
    MODEL_CATEGORIES.forEach((cat) => {
      c[cat.key] = models.filter((m) => m.category === cat.key).length
    })
    return c
  }, [models])

  const treeData = useMemo(
    () =>
      MODEL_CATEGORIES.map((c) => ({
        key: c.key,
        title: `${categoryLabel(c.key)} (${categoryCounts[c.key] ?? 0})`,
        isLeaf: true,
      })),
    [categoryCounts, language]
  )

  const getProviderName = (id: string) => providers.find((p) => p.id === id)?.name ?? id

  const resolveProviderSpec = (providerName: string) =>
    supportedProviders.find(
      (spec) => spec.display_name === providerName || (spec.aliases?.length && spec.aliases.includes(providerName)),
    )

  const filteredProviderOptions = useMemo(() => {
    if (!selectedFormCategory) return providers.map((p) => ({ label: p.name, value: p.id }))
    return providers
      .filter((provider) => {
        const spec = resolveProviderSpec(provider.name)
        return !!spec?.supported_categories?.includes(selectedFormCategory)
      })
      .map((p) => ({ label: p.name, value: p.id }))
  }, [providers, selectedFormCategory, supportedProviders])

  const editingUnsupportedProviderOption = useMemo(() => {
    if (!modelEditing) return null
    const provider = providers.find((p) => p.id === modelEditing.provider_id)
    if (!provider) return null
    const alreadyInOptions = filteredProviderOptions.some((opt) => opt.value === provider.id)
    if (alreadyInOptions) return null
    return {
      label: copy(`${provider.name} (historically/currently unsupported for this category)`, `${provider.name}（历史/当前不支持所选类别）`),
      value: provider.id,
    }
  }, [filteredProviderOptions, modelEditing, providers])

  const providerSelectOptions = useMemo(
    () =>
      editingUnsupportedProviderOption
        ? [editingUnsupportedProviderOption, ...filteredProviderOptions]
        : filteredProviderOptions,
    [editingUnsupportedProviderOption, filteredProviderOptions],
  )
  const unsupportedProviderWarning = useMemo(() => {
    if (!editingUnsupportedProviderOption || !selectedFormCategory) return null
    const provider = providers.find((p) => p.id === editingUnsupportedProviderOption.value)
    if (!provider) return null
    const selectedCategoryLabel = categoryLabel(selectedFormCategory)
    return copy(
      `The current provider “${provider.name}” does not support the ${selectedCategoryLabel} category. Switch to a supported provider before saving.`,
      `当前模型绑定供应商「${provider.name}」不支持「${selectedCategoryLabel}」类别，保存前建议切换到支持该类别的供应商。`,
    )
  }, [editingUnsupportedProviderOption, providers, selectedFormCategory])

  useEffect(() => {
    if (!selectedFormCategory) return
    const providerId = form.getFieldValue('provider_id') as string | undefined
    if (!providerId) return
    const stillSupported = filteredProviderOptions.some((opt) => opt.value === providerId)
    const keepHistoricalEditingProvider = modelEditing?.provider_id === providerId
    if (!stillSupported && !keepHistoricalEditingProvider) {
      form.setFieldsValue({ provider_id: undefined })
      message.warning(copy('The current provider does not support this model category. Choose another provider.', '当前供应商不支持所选模型类别，请重新选择'))
    }
  }, [filteredProviderOptions, form, modelEditing, selectedFormCategory])

  const handleSaveModel = async () => {
    try {
      const values = await form.validateFields()
      let params: Record<string, unknown> = {}
      try {
        if (values.params && String(values.params).trim())
          params = JSON.parse(String(values.params))
      } catch {
        message.error(copy('Parameters must be valid JSON', '参数格式需为合法 JSON'))
        return
      }
      if (modelEditing) {
        await LlmService.updateModelApiV1LlmModelsModelIdPatch({
          modelId: modelEditing.id,
          requestBody: {
            name: values.name,
            category: values.category,
            provider_id: values.provider_id,
            description: values.description ?? null,
            params,
          },
        })
        message.success(copy('Model updated', '模型已更新'))
      } else {
        if (!values.provider_id) {
          message.warning(copy('Add a provider before adding a model', '请先添加供应商后再添加模型'))
          return
        }
        const modelId =
          typeof crypto !== 'undefined' && crypto.randomUUID
            ? crypto.randomUUID()
            : `model_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`
        await LlmService.createModelApiV1LlmModelsPost({
          requestBody: {
            id: modelId,
            name: values.name,
            category: values.category,
            provider_id: values.provider_id,
            description: values.description,
            params,
          },
        })
        message.success(copy('Model added', '模型已添加'))
      }
      setModelModalOpen(false)
      setModelEditing(null)
      form.resetFields()
      void load()
    } catch (e) {
      if (e && typeof e === 'object' && 'errorFields' in e) return
      message.error(copy('Could not save model', '保存失败'))
    }
  }

  const handleDeleteModel = (m: ModelRead) => {
    Modal.confirm({
      title: copy('Delete model', '删除模型'),
      content: copy(`Delete “${m.name}”?`, `确定删除「${m.name}」？`),
      okText: copy('Delete', '删除'),
      cancelText: copy('Cancel', '取消'),
      okType: 'danger',
      onOk: async () => {
        await LlmService.deleteModelApiV1LlmModelsModelIdDelete({ modelId: m.id })
        message.success(copy('Model deleted', '已删除'))
        if (selectedModel?.id === m.id) setSelectedModel(null)
        void load()
      },
    })
  }

  const isCreatifyCatalogModel = (model: ModelRead) =>
    (model.params as Record<string, unknown> | undefined)?.catalog_source === 'creatify'

  const isCatalogModelEnabled = (model: ModelRead) =>
    Boolean((model.params as Record<string, unknown> | undefined)?.enabled)

  /** Persist the explicit administrator approval required before a catalog model can generate. */
  const handleCatalogModelEnabled = async (model: ModelRead, enabled: boolean) => {
    setUpdatingCatalogModelId(model.id)
    try {
      await LlmService.updateModelApiV1LlmModelsModelIdPatch({
        modelId: model.id,
        requestBody: {
          name: model.name,
          category: model.category,
          provider_id: model.provider_id,
          description: model.description ?? null,
          params: { ...(model.params ?? {}), enabled },
        },
      })
      message.success(enabled ? copy('Model enabled', '模型已启用') : copy('Model disabled', '模型已禁用'))
      void load()
    } catch {
      message.error(copy('Could not update the model', '无法更新模型'))
    } finally {
      setUpdatingCatalogModelId(null)
    }
  }

  const openModelModal = (m?: ModelRead) => {
    setModelEditing(m ?? null)
    if (m) {
      form.setFieldsValue({
        name: m.name,
        category: m.category,
        provider_id: m.provider_id,
        description: m.description,
        params: JSON.stringify(m.params ?? {}, null, 2),
      })
    } else {
      form.resetFields()
      form.setFieldsValue({ category: 'text' })
    }
    setModelModalOpen(true)
  }

  /** 基于已有模型打开「添加模型」浮窗，预填字段，名称追加「-复制」。 */
  const openCopyModelModal = (source: ModelRead) => {
    setModelEditing(null)
    form.resetFields()
    form.setFieldsValue({
      name: `${source.name}${copy('-copy', '-复制')}`,
      category: source.category,
      provider_id: source.provider_id,
      description: source.description ?? '',
      params: JSON.stringify(source.params ?? {}, null, 2),
    })
    setModelModalOpen(true)
  }

  const modelColumns: TableColumnsType<ModelRead> = [
    {
      title: copy('Name', '名称'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (n) => <Space>{n}</Space>,
    },
    {
      title: copy('Category', '类别'),
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (c: ModelCategoryKey) => (
        <Tag color={categoryColorMap[c]}>{categoryLabel(c)}</Tag>
      ),
    },
    {
      title: copy('Provider', '关联供应商'),
      dataIndex: 'provider_id',
      key: 'provider_id',
      width: 120,
      render: (id: string) => getProviderName(id),
    },
    {
      title: copy('Parameters', '参数'),
      dataIndex: 'params',
      key: 'params',
      ellipsis: true,
      render: (p: Record<string, unknown>) => (
        <Tooltip title={JSON.stringify(p)}>
          <span>
            {p && Object.keys(p).length ? JSON.stringify(p).slice(0, 30) + '…' : '—'}
          </span>
        </Tooltip>
      ),
    },
    {
      title: copy('Description', '描述'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (d: string) => <Tooltip title={d}>{d || '—'}</Tooltip>,
    },
    {
      title: copy('Created by', '创建人'),
      dataIndex: 'created_by',
      key: 'created_by',
      width: 100,
      render: (c: string) => c || '—',
    },
    {
      title: copy('Actions', '操作'),
      key: 'action',
      width: 112,
      fixed: 'right',
      align: 'center',
      render: (_, record) => (
        <Space size={4} className="flex-nowrap justify-center">
          <Tooltip title={copy('Edit', '编辑')}>
            <Button
              type="text"
              size="small"
              className={TABLE_ACTION_BTN_EDIT_CLASS}
              icon={<EditOutlined />}
              onClick={(e) => {
                e.stopPropagation()
                openModelModal(record)
              }}
            />
          </Tooltip>
          {isCreatifyCatalogModel(record) ? (
            <Tooltip title={isCatalogModelEnabled(record) ? copy('Disable model', '禁用模型') : copy('Enable model', '启用模型')}>
              <Button
                type="text"
                size="small"
                className={TABLE_ACTION_BTN_TEST_CLASS}
                icon={isCatalogModelEnabled(record) ? <StopOutlined /> : <CheckCircleOutlined />}
                loading={updatingCatalogModelId === record.id}
                onClick={(e) => {
                  e.stopPropagation()
                  void handleCatalogModelEnabled(record, !isCatalogModelEnabled(record))
                }}
              />
            </Tooltip>
          ) : (
            <Tooltip title={copy('Test generation', '测试生成')}>
              <Button
                type="text"
                size="small"
                className={TABLE_ACTION_BTN_TEST_CLASS}
                icon={<ThunderboltOutlined />}
                onClick={(e) => {
                  e.stopPropagation()
                }}
              />
            </Tooltip>
          )}
          <Dropdown
            menu={{
              items: [
                {
                  key: 'copy',
                  label: copy('Copy', '复制'),
                  icon: <CopyOutlined />,
                  onClick: ({ domEvent }) => {
                    domEvent.stopPropagation()
                    openCopyModelModal(record)
                  },
                },
                {
                  key: 'delete',
                  label: copy('Delete', '删除'),
                  danger: true,
                  icon: <DeleteOutlined />,
                  onClick: ({ domEvent }) => {
                    domEvent.stopPropagation()
                    handleDeleteModel(record)
                  },
                },
              ],
            }}
            trigger={['click']}
          >
            <Tooltip title={copy('More', '更多')}>
              <Button
                type="text"
                size="small"
                className={TABLE_ACTION_BTN_MORE_CLASS}
                icon={<MenuOutlined />}
                onClick={(e) => e.stopPropagation()}
              />
            </Tooltip>
          </Dropdown>
        </Space>
      ),
    },
  ]

  return (
    <>
      <div className="flex-shrink-0 px-4 py-2 border-b border-gray-100 bg-white flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-gray-600 text-sm">{copy(`${models.length} models`, `共 ${models.length} 个模型`)}</span>
        </div>
        <Space wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openModelModal()}>
            {copy('Add model', '添加模型')}
          </Button>
          <Input
            placeholder={copy('Search name or type', '搜索名称/类型')}
            allowClear
            className="w-48"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Dropdown
            menu={{
              items: sortOptions.map((o) => ({
                key: o.value,
                label: o.label,
                onClick: () => setSortBy(o.value as 'updated' | 'name' | 'category'),
              })),
            }}
          >
            <Button icon={<DownOutlined />}>
              {copy('Sort:', '排序：')}{sortOptions.find((s) => s.value === sortBy)?.label}
            </Button>
          </Dropdown>
        </Space>
      </div>

      <Layout className="flex-1 min-h-0 flex-row overflow-hidden">
        <div
          className="flex-shrink-0 border-r border-gray-200 bg-white overflow-auto"
          style={{ width: treeCollapsed ? 48 : 200 }}
        >
          {treeCollapsed ? (
            <Button
              type="text"
              icon={<RightOutlined />}
              onClick={() => setTreeCollapsed(false)}
              className="w-full rounded-none"
            />
          ) : (
            <>
              <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100">
                <span className="text-sm font-medium text-gray-700">{copy('Filter', '筛选')}</span>
                <Button
                  type="text"
                  size="small"
                  icon={<RightOutlined rotate={180} />}
                  onClick={() => setTreeCollapsed(true)}
                />
              </div>
              <Tree
                selectedKeys={categoryFilter ? [categoryFilter] : []}
                treeData={treeData}
                showLine
                blockNode
                onSelect={([key]) => setCategoryFilter(key ? (key as ModelCategoryKey) : null)}
                className="py-2"
              />
            </>
          )}
        </div>

        <div className="flex-1 min-w-0 overflow-auto p-4 bg-gray-50">
          <div className="flex justify-end gap-1 mb-2">
            <Button
              type={viewMode === 'table' ? 'primary' : 'default'}
              size="small"
              icon={<UnorderedListOutlined />}
              onClick={() => setViewMode('table')}
            />
            <Button
              type={viewMode === 'card' ? 'primary' : 'default'}
              size="small"
              icon={<AppstoreOutlined />}
              onClick={() => setViewMode('card')}
            />
          </div>

          {modelList.length === 0 ? (
            <Card>
              <Empty
                description={
                  models.length === 0
                    ? copy('No models yet. Add a provider before adding a model.', '暂无模型，请先添加供应商再添加模型')
                    : copy('No matching results', '无匹配结果')
                }
              >
                {providers.length > 0 && models.length === 0 && (
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => openModelModal()}>
                    {copy('Add your first model', '添加第一个模型')}
                  </Button>
                )}
              </Empty>
            </Card>
          ) : viewMode === 'table' ? (
            <Card>
              <Table<ModelRead>
                rowKey="id"
                loading={loading}
                columns={modelColumns}
                dataSource={modelList}
                scroll={{ x: 1024 }}
                pagination={{ pageSize: 20 }}
                onRow={(record) => ({
                  onClick: () => {
                    setSelectedModel(record)
                    setDetailPanelOpen(true)
                  },
                  style: { cursor: 'pointer' },
                })}
                size="small"
              />
            </Card>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {modelList.map((m) => (
                <Card
                  key={m.id}
                  hoverable
                  className="cursor-pointer"
                  style={{ minHeight: 220 }}
                  onClick={() => {
                    setSelectedModel(m)
                    setDetailPanelOpen(true)
                  }}
                  actions={[
                    <Button
                      key="edit"
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      onClick={(e) => {
                        e.stopPropagation()
                        openModelModal(m)
                      }}
                    >
                      {copy('Edit', '编辑')}
                    </Button>,
                    isCreatifyCatalogModel(m) ? (
                      <Button
                        key="toggle-catalog-model"
                        type="text"
                        size="small"
                        icon={isCatalogModelEnabled(m) ? <StopOutlined /> : <CheckCircleOutlined />}
                        loading={updatingCatalogModelId === m.id}
                        onClick={(e) => {
                          e.stopPropagation()
                          void handleCatalogModelEnabled(m, !isCatalogModelEnabled(m))
                        }}
                      >
                        {isCatalogModelEnabled(m) ? copy('Disable', '禁用') : copy('Enable', '启用')}
                      </Button>
                    ) : (
                      <Button key="test" type="text" size="small" icon={<ThunderboltOutlined />}>
                        {copy('Test generation', '测试生成')}
                      </Button>
                    ),
                    <Dropdown
                      key="more"
                      menu={{
                        items: [
                          {
                            key: 'copy',
                            label: copy('Copy', '复制'),
                            icon: <CopyOutlined />,
                            onClick: ({ domEvent }) => {
                              domEvent.stopPropagation()
                              openCopyModelModal(m)
                            },
                          },
                          {
                            key: 'delete',
                            label: copy('Delete', '删除'),
                            danger: true,
                            icon: <DeleteOutlined />,
                            onClick: ({ domEvent }) => {
                              domEvent.stopPropagation()
                              handleDeleteModel(m)
                            },
                          },
                        ],
                      }}
                      trigger={['click']}
                    >
                      <Button type="text" size="small" onClick={(e) => e.stopPropagation()}>
                        {copy('More', '更多')}
                      </Button>
                    </Dropdown>,
                  ]}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <Tag color={categoryColorMap[m.category]}>{categoryLabel(m.category)}</Tag>
                  </div>
                  <div className="font-medium mb-1">{m.name}</div>
                  {isCreatifyCatalogModel(m) && (
                    <Tag color={isCatalogModelEnabled(m) ? 'green' : 'default'}>
                      {isCatalogModelEnabled(m) ? copy('Enabled', '已启用') : copy('Disabled', '已禁用')}
                    </Tag>
                  )}
                  <div className="text-gray-500 text-sm mb-1">
                    {copy(`Provider: ${getProviderName(m.provider_id)}`, `供应商：${getProviderName(m.provider_id)}`)}
                  </div>
                  <div className="text-gray-500 text-sm line-clamp-2 mb-2">{m.description || '—'}</div>
                  {m.created_by && (
                    <span className="text-xs text-gray-400">{copy(`Created by: ${m.created_by}`, `创建：${m.created_by}`)}</span>
                  )}
                </Card>
              ))}
            </div>
          )}
        </div>

        {selectedModel && isLargeScreen && (
          <div
            className="flex-shrink-0 overflow-auto border-l border-gray-200 bg-white"
            style={{ width: '36%', minWidth: 320 }}
          >
            <div className="p-4 border-b border-gray-100 flex items-center justify-between">
              <span className="font-medium">{copy('Details', '详情')}</span>
              <Button
                type="link"
                size="small"
                onClick={() => {
                  setDetailPanelOpen(false)
                  setSelectedModel(null)
                }}
              >
                {copy('Collapse', '收起')}
              </Button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <div className="text-sm text-gray-500 mb-1">{copy('Name', '名称')}</div>
                <div className="font-medium">{selectedModel.name}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500 mb-1">{copy('Category', '类别')}</div>
                <Tag color={categoryColorMap[selectedModel.category]}>
                  {categoryLabel(selectedModel.category)}
                </Tag>
              </div>
              <div>
                <div className="text-sm text-gray-500 mb-1">{copy('Provider', '关联供应商')}</div>
                <div>{getProviderName(selectedModel.provider_id)}</div>
              </div>
              {isCreatifyCatalogModel(selectedModel) && (
                <div>
                  <div className="text-sm text-gray-500 mb-1">{copy('Asset Generator status', 'Asset Generator 状态')}</div>
                  <Tag color={isCatalogModelEnabled(selectedModel) ? 'green' : 'default'}>
                    {isCatalogModelEnabled(selectedModel) ? copy('Enabled', '已启用') : copy('Disabled', '已禁用')}
                  </Tag>
                </div>
              )}
              <div>
                <div className="text-sm text-gray-500 mb-1">{copy('Description', '描述')}</div>
                <div className="text-gray-700 text-sm">{selectedModel.description || '—'}</div>
              </div>
              <Space>
                <Button
                  type="primary"
                  icon={<EditOutlined />}
                  onClick={() => openModelModal(selectedModel)}
                >
                  {copy('Edit', '编辑')}
                </Button>
                <Button icon={<ThunderboltOutlined />}>{copy('Quick test', '快速测试')}</Button>
                {isCreatifyCatalogModel(selectedModel) && (
                  <Button
                    icon={isCatalogModelEnabled(selectedModel) ? <StopOutlined /> : <CheckCircleOutlined />}
                    loading={updatingCatalogModelId === selectedModel.id}
                    onClick={() => void handleCatalogModelEnabled(selectedModel, !isCatalogModelEnabled(selectedModel))}
                  >
                    {isCatalogModelEnabled(selectedModel) ? copy('Disable', '禁用') : copy('Enable', '启用')}
                  </Button>
                )}
              </Space>
            </div>
          </div>
        )}

        {selectedModel && !isLargeScreen && (
          <Drawer
            title={copy('Details', '详情')}
            placement="right"
            open={detailPanelOpen}
            onClose={() => setDetailPanelOpen(false)}
            width="min(100%, 400px)"
          >
            <div className="space-y-4">
              <div>
                <div className="text-sm text-gray-500 mb-1">{copy('Name', '名称')}</div>
                <div className="font-medium">{selectedModel.name}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500 mb-1">{copy('Category', '类别')}</div>
                <Tag color={categoryColorMap[selectedModel.category]}>
                  {categoryLabel(selectedModel.category)}
                </Tag>
              </div>
              {isCreatifyCatalogModel(selectedModel) && (
                <Tag color={isCatalogModelEnabled(selectedModel) ? 'green' : 'default'}>
                  {isCatalogModelEnabled(selectedModel) ? copy('Enabled', '已启用') : copy('Disabled', '已禁用')}
                </Tag>
              )}
              <Space>
                <Button
                  type="primary"
                  icon={<EditOutlined />}
                  onClick={() => openModelModal(selectedModel)}
                >
                  {copy('Edit', '编辑')}
                </Button>
                <Button icon={<ThunderboltOutlined />}>{copy('Quick test', '快速测试')}</Button>
                {isCreatifyCatalogModel(selectedModel) && (
                  <Button
                    icon={isCatalogModelEnabled(selectedModel) ? <StopOutlined /> : <CheckCircleOutlined />}
                    loading={updatingCatalogModelId === selectedModel.id}
                    onClick={() => void handleCatalogModelEnabled(selectedModel, !isCatalogModelEnabled(selectedModel))}
                  >
                    {isCatalogModelEnabled(selectedModel) ? copy('Disable', '禁用') : copy('Enable', '启用')}
                  </Button>
                )}
              </Space>
            </div>
          </Drawer>
        )}
      </Layout>

      <Modal
        title={modelEditing ? copy('Edit model', '编辑模型') : copy('Add model', '添加模型')}
        open={modelModalOpen}
        onCancel={() => {
          setModelModalOpen(false)
          setModelEditing(null)
          form.resetFields()
        }}
        onOk={() => void handleSaveModel()}
        width={560}
        destroyOnClose
      >
        <Form form={form} layout="vertical" className="pt-2">
          <Form.Item name="name" label={copy('Name', '名称')} rules={[{ required: true }]}>
            <Input placeholder={copy('For example: GPT-4', '例如：GPT-4')} />
          </Form.Item>
          <Form.Item name="category" label={copy('Category', '类别')} rules={[{ required: true }]}>
            <Select options={MODEL_CATEGORIES.map((c) => ({ label: categoryLabel(c.key), value: c.key }))} />
          </Form.Item>
          <Form.Item
            name="provider_id"
            label={copy('Provider', '关联供应商')}
            rules={[{ required: true, message: copy('Select a provider', '请选择供应商') }]}
          >
            <Select
              loading={providerOptionsLoading}
              placeholder={
                selectedFormCategory
                  ? copy(`Select a provider that supports ${categoryLabel(selectedFormCategory)}`, `选择支持${categoryLabel(selectedFormCategory)}的供应商`)
                  : copy('Select a provider (add one first)', '选择供应商（请先添加供应商）')
              }
              options={providerSelectOptions}
              notFoundContent={
                providerOptionsLoading
                  ? copy('Loading…', '加载中…')
                  : selectedFormCategory
                    ? copy('No provider supports this category', '暂无支持该类别的供应商')
                    : copy('No providers', '暂无供应商')
              }
            />
          </Form.Item>
          {unsupportedProviderWarning && (
            <Alert
              type="warning"
              showIcon
              className="mb-4"
              message={unsupportedProviderWarning}
            />
          )}
          <Form.Item name="params" label={copy('Parameters (JSON)', '参数（JSON）')}>
            <Input.TextArea rows={3} placeholder='{"max_tokens": 4096, "temperature": 0.7}' />
          </Form.Item>
          <Form.Item name="description" label={copy('Description', '描述')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
