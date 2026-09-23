import React, { useEffect, useState, useMemo } from 'react'
import {
  Layout,
  Tabs,
  Input,
  Button,
  Table,
  Tag,
  Space,
  Tree,
  Drawer,
  Card,
  Dropdown,
  Modal,
  message,
  Tooltip,
  Empty,
  Grid,
} from 'antd'
import type { TableColumnsType } from 'antd'
import {
  PlusOutlined,
  SearchOutlined,
  EditOutlined,
  DeleteOutlined,
  StarOutlined,
  StarFilled,
  CopyOutlined,
  ExportOutlined,
  MenuOutlined,
  AppstoreOutlined,
  UnorderedListOutlined,
  DownOutlined,
  RightOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import api from '../../../services/aiStudioApi'
import type { Agent, AgentTypeKey } from '../../../mocks/data'
import { useAppStore } from '../../../store/useAppStore'

const AGENT_TYPES: { key: AgentTypeKey; color: string }[] = [
  { key: 'plot', color: 'blue' },
  { key: 'character', color: 'green' },
  { key: 'scene', color: 'orange' },
  { key: 'prop', color: 'purple' },
  { key: 'other', color: 'default' },
]

const typeColorMap = Object.fromEntries(AGENT_TYPES.map((t) => [t.key, t.color]))

export default function AgentManagement() {
  const language = useAppStore((state) => state.language)
  const copy = (english: string, chinese: string) => (language === 'zh-CN' ? chinese : english)
  const agentTypeLabel = (type: AgentTypeKey) => {
    const labels: Record<AgentTypeKey, [string, string]> = {
      plot: ['Plot extraction', '剧情提取'],
      character: ['Character extraction', '角色提取'],
      scene: ['Scene extraction', '场景提取'],
      prop: ['Prop extraction', '道具提取'],
      other: ['Other', '其他类型'],
    }
    return copy(...labels[type])
  }
  const typeLabelMap = useMemo(
    () => Object.fromEntries(AGENT_TYPES.map((type) => [type.key, agentTypeLabel(type.key)])) as Record<AgentTypeKey, string>,
    [language],
  )
  const sortOptions = [
    { value: 'updated', label: copy('Recently updated', '最近更新') },
    { value: 'name', label: copy('Name', '名称') },
  ]
  const navigate = useNavigate()
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<string>('all')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<'updated' | 'name'>('updated')
  const [viewMode, setViewMode] = useState<'table' | 'card'>('table')
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null)
  const [detailPanelOpen, setDetailPanelOpen] = useState(false)
  const [treeCollapsed, setTreeCollapsed] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createType, setCreateType] = useState<AgentTypeKey>('plot')
  const [createDesc, setCreateDesc] = useState('')
  const [createLoading, setCreateLoading] = useState(false)
  const [typeFilter, setTypeFilter] = useState<AgentTypeKey | null>(null)
  const { lg } = Grid.useBreakpoint()
  const isLargeScreen = lg ?? false

  const load = async () => {
    setLoading(true)
    try {
      const list = await api.agents.list()
      setAgents(Array.isArray(list) ? list : [])
    } catch {
      message.error(copy('Could not load agents', '加载 Agent 列表失败'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const filteredList = useMemo(() => {
    let list = agents
    // 左侧树选中时以树为准，否则用 Tab
    if (typeFilter) {
      list = list.filter((a) => a.type === typeFilter)
    } else if (activeTab !== 'all') {
      list = list.filter((a) => a.type === activeTab)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(
        (a) =>
          a.name.toLowerCase().includes(q) ||
          typeLabelMap[a.type]?.toLowerCase().includes(q) ||
          a.description.toLowerCase().includes(q) ||
          a.createdBy.toLowerCase().includes(q)
      )
    }
    if (sortBy === 'name') {
      list = [...list].sort((a, b) => a.name.localeCompare(b.name))
    } else {
      list = [...list].sort(
        (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      )
    }
    return list
  }, [agents, activeTab, typeFilter, search, sortBy])

  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = { all: agents.length }
    AGENT_TYPES.forEach((t) => {
      counts[t.key] = agents.filter((a) => a.type === t.key).length
    })
    return counts
  }, [agents])

  const treeData = useMemo(
    () =>
      AGENT_TYPES.map((t) => ({
        key: t.key,
      title: `${agentTypeLabel(t.key)} (${typeCounts[t.key] ?? 0})`,
        isLeaf: true,
      })),
    [typeCounts, language]
  )

  const handleRowClick = (record: Agent) => {
    setSelectedAgent(record)
    setDetailPanelOpen(true)
  }

  const handleSetDefault = async (agent: Agent) => {
    try {
      await api.agents.update(agent.id, { isDefault: true })
      message.success(copy('Set as default', '已设为默认'))
      void load()
      if (selectedAgent?.id === agent.id) setSelectedAgent({ ...agent, isDefault: true })
    } catch {
      message.error(copy('Could not update default agent', '设置失败'))
    }
  }

  const handleBatchDelete = () => {
    Modal.confirm({
      title: copy('Delete selected agents', '批量删除'),
      content: copy(`Delete ${selectedRowKeys.length} selected agents?`, `确定删除选中的 ${selectedRowKeys.length} 个 Agent？`),
      okText: copy('Delete', '删除'),
      cancelText: copy('Cancel', '取消'),
      okType: 'danger',
      onOk: async () => {
        for (const id of selectedRowKeys) {
          await api.agents.delete(String(id))
        }
        message.success(copy('Agents deleted', '已删除'))
        setSelectedRowKeys([])
        void load()
        setDetailPanelOpen(false)
        setSelectedAgent(null)
      },
    })
  }

  const handleCreate = async () => {
    if (!createName.trim()) {
      message.warning(copy('Enter an agent name', '请输入 Agent 名称'))
      return
    }
    setCreateLoading(true)
    try {
      const created = await api.agents.create({
        name: createName.trim(),
        type: createType,
        description: createDesc.trim(),
      })
      message.success(copy('Agent created', '创建成功'))
      setCreateModalOpen(false)
      setCreateName('')
      setCreateDesc('')
      navigate(`/agents/${created.id}/edit`)
      void load()
    } catch {
      message.error(copy('Could not create agent', '创建失败'))
    } finally {
      setCreateLoading(false)
    }
  }

  const handleDelete = (agent: Agent, e: React.MouseEvent) => {
    e.stopPropagation()
    Modal.confirm({
      title: copy('Delete agent', '删除 Agent'),
      content: copy(`Delete “${agent.name}”?`, `确定删除「${agent.name}」？`),
      okText: copy('Delete', '删除'),
      cancelText: copy('Cancel', '取消'),
      okType: 'danger',
      onOk: async () => {
        await api.agents.delete(agent.id)
        message.success(copy('Agent deleted', '已删除'))
        if (selectedAgent?.id === agent.id) {
          setDetailPanelOpen(false)
          setSelectedAgent(null)
        }
        void load()
      },
    })
  }

  const tableColumns: TableColumnsType<Agent> = [
    {
      title: copy('Name', '名称'),
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name, record) => (
        <Space>
          {record.isDefault && (
            <StarFilled style={{ color: '#faad14' }} title={copy('Default', '默认')} />
          )}
          <span>{name}</span>
        </Space>
      ),
    },
    {
      title: copy('Type', '类型'),
      dataIndex: 'type',
      key: 'type',
      width: 110,
      render: (type: AgentTypeKey) => (
        <Tag color={typeColorMap[type] ?? 'default'}>{typeLabelMap[type] ?? type}</Tag>
      ),
    },
    {
      title: copy('Description', '描述'),
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (desc: string) => (
        <Tooltip title={desc}>
          <span>{desc || '—'}</span>
        </Tooltip>
      ),
    },
    {
      title: copy('Default', '默认'),
      dataIndex: 'isDefault',
      key: 'isDefault',
      width: 70,
      render: (isDefault: boolean, record) =>
        isDefault ? (
          <StarFilled style={{ color: '#faad14' }} />
        ) : (
          <StarOutlined
            className="text-gray-400 hover:text-amber-500"
            onClick={(e) => {
              e.stopPropagation()
              Modal.confirm({
                title: copy('Set as default', '设为默认'),
                content: copy('This will replace the current default agent for this type.', '此操作将替换当前该类型的默认 Agent。'),
                onOk: () => handleSetDefault(record),
              })
            }}
          />
        ),
    },
    {
      title: copy('Version', '版本'),
      key: 'version',
      width: 140,
      render: (_, record) => copy(`${record.version} (updated ${record.updatedAt})`, `${record.version} (更新于 ${record.updatedAt})`),
    },
    {
      title: copy('Created by / updated', '创建者/更新'),
      key: 'creator',
      width: 120,
      render: (_, record) => `${record.updatedBy} / ${record.updatedAt}`,
    },
    {
      title: copy('Actions', '操作'),
      key: 'action',
      width: 180,
      render: (_, record) => (
        <Space size="small" onClick={(e) => e.stopPropagation()}>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => navigate(`/agents/${record.id}/edit`)}>
            {copy('Edit', '编辑')}
          </Button>
          <Button type="link" size="small" icon={<ThunderboltOutlined />} onClick={() => navigate(`/agents/${record.id}/edit?test=1`)}>
            {copy('Test', '测试')}
          </Button>
          <Dropdown
            menu={{
              items: [
                { key: 'copy', label: copy('Copy', '复制'), icon: <CopyOutlined /> },
                { key: 'export', label: copy('Export', '导出'), icon: <ExportOutlined /> },
                { type: 'divider' },
                {
                  key: 'delete',
                  label: copy('Delete', '删除'),
                  danger: true,
                  icon: <DeleteOutlined />,
                  onClick: () => handleDelete(record, { stopPropagation: () => {} } as unknown as React.MouseEvent),
                },
              ],
            }}
            trigger={['click']}
          >
            <Button type="link" size="small" icon={<MenuOutlined />} />
          </Dropdown>
        </Space>
      ),
    },
  ]

  return (
    <Layout className="h-full flex flex-col" style={{ minHeight: 0 }}>
      {/* 顶部区域 */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 bg-white space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-gray-800">{copy('Agent management', 'Agent管理')}</span>
            <span className="text-gray-500 text-sm">{copy(`· ${agents.length} agents total`, `· 总计 ${agents.length} 个 Agent`)}</span>
          </div>
          <Space wrap>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
              {copy('New agent', '创建新 Agent')}
            </Button>
            <Input
              placeholder={copy('Search by name, type, or creator', '按名称/类型/创建者搜索')}
              prefix={<SearchOutlined className="text-gray-400" />}
              allowClear
              className="w-52"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <Dropdown
              menu={{
                items: sortOptions.map((o) => ({
                  key: o.value,
                  label: o.label,
                  onClick: () => setSortBy(o.value as 'updated' | 'name'),
                })),
              }}
            >
              <Button icon={<DownOutlined />}>{copy('Sort:', '排序：')}{sortOptions.find((s) => s.value === sortBy)?.label}</Button>
            </Dropdown>
          </Space>
        </div>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          size="small"
          items={[
            { key: 'all', label: copy(`All (${typeCounts.all})`, `全部 (${typeCounts.all})`) },
            ...AGENT_TYPES.map((t) => ({
              key: t.key,
              label: `${agentTypeLabel(t.key)} (${typeCounts[t.key]})`,
            })),
          ]}
        />
      </div>

      {/* 主体：左侧树 + 列表 + 右侧面板 */}
      <Layout className="flex-1 min-h-0 flex-row overflow-hidden">
        {/* 左侧类型树 */}
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
                <span className="text-sm font-medium text-gray-700">{copy('Filter by type', '类型筛选')}</span>
                <Button type="text" size="small" icon={<RightOutlined rotate={180} />} onClick={() => setTreeCollapsed(true)} />
              </div>
              <Tree
                selectedKeys={typeFilter ? [typeFilter] : []}
                treeData={treeData}
                showLine
                blockNode
                expandAction="click"
                onSelect={([key]) => setTypeFilter(key ? (key as AgentTypeKey) : null)}
                className="py-2"
              />
            </>
          )}
        </div>

        {/* 列表区 */}
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

          {filteredList.length === 0 ? (
            <Card>
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={agents.length === 0
                  ? copy('No agents yet. Create your first agent to begin.', '暂无 Agent，点击「创建新 Agent」开始')
                  : copy('No matching results', '无匹配结果')}
              >
                {agents.length === 0 && (
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
                    {copy('Create your first agent', '创建第一个 Agent')}
                  </Button>
                )}
              </Empty>
            </Card>
          ) : viewMode === 'table' ? (
            <Card className="mb-4">
              {selectedRowKeys.length > 0 && (
                <div className="mb-3 flex items-center gap-2 flex-wrap">
                  <span className="text-gray-500 text-sm">{copy(`${selectedRowKeys.length} selected`, `已选 ${selectedRowKeys.length} 项`)}</span>
                  <Button size="small" danger icon={<DeleteOutlined />} onClick={handleBatchDelete}>
                    {copy('Delete selected', '批量删除')}
                  </Button>
                </div>
              )}
              <Table<Agent>
                rowKey="id"
                loading={loading}
                columns={tableColumns}
                dataSource={filteredList}
                pagination={{ pageSize: 20, showSizeChanger: true }}
                rowSelection={{
                  selectedRowKeys,
                  onChange: (keys) => setSelectedRowKeys(keys as React.Key[]),
                }}
                onRow={(record) => ({
                  onClick: () => handleRowClick(record),
                  style: { cursor: 'pointer' },
                })}
                size="small"
              />
            </Card>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filteredList.map((agent) => (
                <Card
                  key={agent.id}
                  hoverable
                  className="cursor-pointer transition-shadow"
                  style={{ minHeight: 220 }}
                  onClick={() => handleRowClick(agent)}
                  actions={[
                    <Button key="edit" type="text" size="small" icon={<EditOutlined />} onClick={(e) => { e.stopPropagation(); navigate(`/agents/${agent.id}/edit`) }}>{copy('Edit', '编辑')}</Button>,
                    <Button key="test" type="text" size="small" icon={<ThunderboltOutlined />} onClick={(e) => { e.stopPropagation(); navigate(`/agents/${agent.id}/edit?test=1`) }}>{copy('Test', '测试')}</Button>,
                    <Dropdown
                      key="more"
                      menu={{
                        items: [
                          { key: 'copy', label: copy('Copy', '复制'), icon: <CopyOutlined /> },
                          { key: 'export', label: copy('Export', '导出'), icon: <ExportOutlined /> },
                          {
                            key: 'delete',
                            label: copy('Delete', '删除'),
                            danger: true,
                            icon: <DeleteOutlined />,
                            onClick: () => handleDelete(agent, { stopPropagation: () => {} } as unknown as React.MouseEvent),
                          },
                        ],
                      }}
                      trigger={['click']}
                    >
                      <Button type="text" size="small" icon={<MenuOutlined />} onClick={(e) => e.stopPropagation()}>{copy('More', '更多')}</Button>
                    </Dropdown>,
                  ]}
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <Tag color={typeColorMap[agent.type]}>{typeLabelMap[agent.type]}</Tag>
                    {agent.isDefault && <StarFilled style={{ color: '#faad14' }} />}
                  </div>
                  <div className="font-medium text-gray-900 mb-1 truncate" title={agent.name}>
                    {agent.name}
                  </div>
                  <div className="text-gray-500 text-sm line-clamp-2 mb-2" title={agent.description}>
                    {agent.description || '—'}
                  </div>
                  <div className="text-xs text-gray-400">
                    {copy(`${agent.version} · Updated ${agent.updatedAt}`, `${agent.version} · 更新：${agent.updatedAt}`)}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* 右侧详情：桌面为侧栏，移动端为 Drawer */}
        {selectedAgent && isLargeScreen && (
            <div className="flex-shrink-0 overflow-auto border-l border-gray-200 bg-white" style={{ width: '36%', minWidth: 320 }}>
              <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                <span className="font-medium">{copy('Agent details', 'Agent 详情')}</span>
                <Button type="link" size="small" onClick={() => { setSelectedAgent(null); setDetailPanelOpen(false) }}>{copy('Collapse', '收起')}</Button>
              </div>
              <div className="p-4 space-y-4">
                <div>
                  <div className="text-sm text-gray-500 mb-1">{copy('Name', '名称')}</div>
                  <div className="font-medium">{selectedAgent.name}</div>
                </div>
                <div>
                  <div className="text-sm text-gray-500 mb-1">{copy('Type', '类型')}</div>
                  <Tag color={typeColorMap[selectedAgent.type]}>{typeLabelMap[selectedAgent.type]}</Tag>
                </div>
                <div>
                  <div className="text-sm text-gray-500 mb-1">{copy('Description', '描述')}</div>
                  <div className="text-gray-700 text-sm">{selectedAgent.description || '—'}</div>
                </div>
                <div className="text-sm text-gray-500">
                  {copy(`Version ${selectedAgent.version} · Updated ${selectedAgent.updatedAt} · ${selectedAgent.updatedBy}`, `版本 ${selectedAgent.version} · 更新于 ${selectedAgent.updatedAt} · ${selectedAgent.updatedBy}`)}
                </div>
                <Space>
                  <Button type="primary" icon={<EditOutlined />} onClick={() => navigate(`/agents/${selectedAgent.id}/edit`)}>
                    {copy('Edit', '编辑')}
                  </Button>
                  <Button icon={<ThunderboltOutlined />} onClick={() => navigate(`/agents/${selectedAgent.id}/edit?test=1`)}>
                    {copy('Quick test', '快速测试')}
                  </Button>
                </Space>
              </div>
            </div>
        )}
        {selectedAgent && !isLargeScreen && (
            <Drawer
              title={copy('Agent details', 'Agent 详情')}
              placement="right"
              open={detailPanelOpen}
              onClose={() => setDetailPanelOpen(false)}
              width="min(100%, 400px)"
            >
              <div className="space-y-4">
                <div>
                  <div className="text-sm text-gray-500 mb-1">{copy('Name', '名称')}</div>
                  <div className="font-medium">{selectedAgent.name}</div>
                </div>
                <div>
                  <div className="text-sm text-gray-500 mb-1">{copy('Type', '类型')}</div>
                  <Tag color={typeColorMap[selectedAgent.type]}>{typeLabelMap[selectedAgent.type]}</Tag>
                </div>
                <div>
                  <div className="text-sm text-gray-500 mb-1">{copy('Description', '描述')}</div>
                  <div className="text-gray-700 text-sm">{selectedAgent.description || '—'}</div>
                </div>
                <Space>
                  <Button type="primary" icon={<EditOutlined />} onClick={() => navigate(`/agents/${selectedAgent.id}/edit`)}>
                    {copy('Edit', '编辑')}
                  </Button>
                  <Button icon={<ThunderboltOutlined />} onClick={() => navigate(`/agents/${selectedAgent.id}/edit?test=1`)}>
                    {copy('Quick test', '快速测试')}
                  </Button>
                </Space>
              </div>
            </Drawer>
        )}
      </Layout>

      {/* 创建 Agent 弹窗 */}
      <Modal
        title={copy('New agent', '创建新 Agent')}
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        onOk={() => void handleCreate()}
        confirmLoading={createLoading}
        okText={copy('Create', '创建')}
        cancelText={copy('Cancel', '取消')}
        width={480}
      >
        <div className="space-y-4 pt-2">
          <div>
            <label className="block text-sm text-gray-600 mb-1">{copy('Name', '名称')}</label>
            <Input
              placeholder={copy('For example: Plot Extractor v2.1', '例如：剧情提取Agent v2.1')}
              value={createName}
              onChange={(e) => setCreateName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">{copy('Type', '类型')}</label>
            <Space wrap>
              {AGENT_TYPES.map((t) => (
                <Tag
                  key={t.key}
                  color={createType === t.key ? t.color : 'default'}
                  className="cursor-pointer"
                  onClick={() => setCreateType(t.key)}
                >
                  {agentTypeLabel(t.key)}
                </Tag>
              ))}
            </Space>
          </div>
          <div>
            <label className="block text-sm text-gray-600 mb-1">{copy('Description (optional)', '描述（选填）')}</label>
            <Input.TextArea
              rows={3}
              placeholder={copy('Briefly describe what this agent does', '简要描述该 Agent 的用途')}
              value={createDesc}
              onChange={(e) => setCreateDesc(e.target.value)}
            />
          </div>
        </div>
      </Modal>
    </Layout>
  )
}
