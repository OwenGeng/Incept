import { useCallback, useEffect, useRef, useState } from 'react'
import { App as AntApp, Button, Checkbox, Drawer, Empty, Input, InputNumber, List, Popconfirm, Select, Space, Spin, Tabs, Tag } from 'antd'
import { DeleteOutlined, PlusOutlined, SendOutlined } from '@ant-design/icons'
import { useAppStore } from '../../../../store/useAppStore'
import {
  chatWithProjectAgent,
  archiveProjectMemory,
  createProjectMemory,
  deleteProjectAgentSession,
  listProjectAgentMessages,
  listProjectAgentSessions,
  listProjectMemories,
  type ProjectMemory,
  type ProjectAgentMessage,
  type ProjectAgentSession,
} from '../../../../services/projectAgent'

export function CreativeAgentPanel({ projectId, open, onClose }: { projectId: string; open: boolean; onClose: () => void }) {
  const language = useAppStore((state) => state.language)
  const copy = useCallback((english: string, chinese: string) => language === 'zh-CN' ? chinese : english, [language])
  const { message } = AntApp.useApp()
  const [sessions, setSessions] = useState<ProjectAgentSession[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ProjectAgentMessage[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [activePane, setActivePane] = useState<'chat' | 'memory'>('chat')
  const [memories, setMemories] = useState<ProjectMemory[]>([])
  const [memoryContent, setMemoryContent] = useState('')
  const [memoryKind, setMemoryKind] = useState<ProjectMemory['kind']>('preference')
  const [memoryScope, setMemoryScope] = useState<ProjectMemory['scope']>('project')
  const [memoryConfidence, setMemoryConfidence] = useState(1)
  const [memoryTags, setMemoryTags] = useState('')
  const [memoryPinned, setMemoryPinned] = useState(false)
  const [memoryQuery, setMemoryQuery] = useState('')
  const bottomRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    listProjectAgentSessions(projectId)
      .then((items) => {
        setSessions(items)
        setSessionId((current) => current ?? items[0]?.id ?? null)
      })
      .catch(() => message.error(copy('Could not load agent conversations', '无法加载 Agent 会话')))
      .finally(() => setLoading(false))
  }, [copy, message, open, projectId])

  useEffect(() => {
    if (!open || !sessionId) {
      setMessages([])
      return
    }
    setLoading(true)
    listProjectAgentMessages(projectId, sessionId)
      .then(setMessages)
      .catch(() => message.error(copy('Could not load messages', '无法加载消息')))
      .finally(() => setLoading(false))
  }, [copy, message, open, projectId, sessionId])

  useEffect(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), [messages, sending])

  const loadMemories = useCallback((query = memoryQuery) => {
    if (!open) return
    listProjectMemories(projectId, query)
      .then(setMemories)
      .catch(() => message.error(copy('Could not load memory', '无法加载记忆')))
  }, [copy, memoryQuery, message, open, projectId])

  useEffect(() => { loadMemories() }, [loadMemories])

  const saveMemory = async () => {
    if (!memoryContent.trim()) return
    try {
      await createProjectMemory(projectId, {
        scope: memoryScope,
        kind: memoryKind,
        content: memoryContent.trim(),
        tags: memoryTags.split(',').map((item) => item.trim()).filter(Boolean),
        pinned: memoryPinned,
        confidence: memoryConfidence,
      })
      setMemoryContent('')
      setMemoryTags('')
      setMemoryPinned(false)
      loadMemories()
      message.success(copy('Memory saved.', '记忆已保存。'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not save memory.', '无法保存记忆。'))
    }
  }

  const send = async () => {
    const content = draft.trim()
    if (!content || sending) return
    setDraft('')
    setSending(true)
    try {
      const response = await chatWithProjectAgent(projectId, content, sessionId)
      setSessionId(response.session.id)
      setSessions((current) => [response.session, ...current.filter((item) => item.id !== response.session.id)])
      setMessages((current) => [...current, response.user_message, response.assistant_message])
    } catch (error) {
      setDraft(content)
      message.error(error instanceof Error ? error.message : copy('Agent request failed', 'Agent 请求失败'))
    } finally {
      setSending(false)
    }
  }

  const deleteSession = async () => {
    if (!sessionId || sending) return
    try {
      await deleteProjectAgentSession(projectId, sessionId)
      const remaining = sessions.filter((item) => item.id !== sessionId)
      setSessions(remaining)
      setSessionId(remaining[0]?.id ?? null)
      setMessages([])
      message.success(copy('Conversation deleted', '会话已删除'))
    } catch (error) {
      message.error(error instanceof Error ? error.message : copy('Could not delete conversation', '无法删除会话'))
    }
  }

  return (
    <Drawer
      title={copy('Creative agent', '创意 Agent')}
      open={open}
      onClose={onClose}
      width={480}
      styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', minHeight: 0 } }}
      extra={<Tag color="blue">{copy('Project-aware', '项目上下文')}</Tag>}
    >
      <Tabs
        className="px-3 pt-2"
        activeKey={activePane}
        onChange={(value) => setActivePane(value as 'chat' | 'memory')}
        items={[
          { key: 'chat', label: copy('Conversation', '对话') },
          { key: 'memory', label: `${copy('Memory', '记忆')} (${memories.length})` },
        ]}
      />
      {activePane === 'chat' ? <>
      <div className="border-b border-slate-200 p-3">
        <Space.Compact block>
          <Select
            className="flex-1"
            placeholder={copy('New conversation', '新会话')}
            value={sessionId ?? undefined}
            onChange={setSessionId}
            options={sessions.map((item) => ({ value: item.id, label: `${item.title} · ${item.status}` }))}
          />
          <Button icon={<PlusOutlined />} onClick={() => { setSessionId(null); setMessages([]) }}>
            {copy('New', '新建')}
          </Button>
          <Popconfirm
            title={copy('Delete this conversation?', '删除这个会话？')}
            description={copy('Its message history will be removed.', '会话中的消息记录也会被删除。')}
            okText={copy('Delete', '删除')}
            cancelText={copy('Cancel', '取消')}
            okButtonProps={{ danger: true }}
            disabled={!sessionId || sending}
            onConfirm={() => void deleteSession()}
          >
            <Button danger icon={<DeleteOutlined />} disabled={!sessionId || sending} aria-label={copy('Delete conversation', '删除会话')} />
          </Popconfirm>
        </Space.Compact>
      </div>

      <div className="min-h-0 flex-1 overflow-auto bg-slate-50/60 p-4">
        {loading ? <div className="flex justify-center py-16"><Spin /></div> : null}
        {!loading && messages.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={copy('Ask about research, creative direction, scripts, or production.', '可以询问研究、创意方向、脚本或制作问题。')}
          />
        ) : null}
        <List
          split={false}
          dataSource={messages}
          renderItem={(item) => (
            <List.Item className={`!border-0 !px-0 ${item.role === 'user' ? '!justify-end' : '!justify-start'}`}>
              <div className={`max-w-[88%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-6 ${item.role === 'user' ? 'bg-blue-600 text-white' : 'border border-slate-200 bg-white text-slate-800 shadow-sm'}`}>
                {item.content}
              </div>
            </List.Item>
          )}
        />
        {sending ? <div className="text-sm text-slate-500"><Spin size="small" /> {copy('Agent is thinking…', 'Agent 正在思考…')}</div> : null}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-slate-200 bg-white p-3">
        <Space.Compact block>
          <Input.TextArea
            autoSize={{ minRows: 2, maxRows: 6 }}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onPressEnter={(event) => {
              if (!event.shiftKey) { event.preventDefault(); void send() }
            }}
            placeholder={copy('Ask the creative agent…', '询问创意 Agent…')}
          />
          <Button type="primary" icon={<SendOutlined />} loading={sending} onClick={() => void send()} aria-label={copy('Send', '发送')} />
        </Space.Compact>
        <div className="mt-2 text-xs text-slate-400">
          {copy('The agent proposes changes; approve governed direction in Research.', 'Agent 提出建议；受控创意方向需在 Research 中批准。')}
        </div>
      </div>
      </> : (
        <div className="min-h-0 flex-1 overflow-auto p-4 space-y-4">
          <div className="space-y-2 rounded-lg border border-slate-200 p-3">
            <Space wrap>
              <Select
                value={memoryScope}
                onChange={setMemoryScope}
                options={[{ value: 'project', label: copy('Project', '项目') }, { value: 'user', label: copy('User', '用户') }]}
              />
              <Select
                value={memoryKind}
                onChange={setMemoryKind}
                options={['preference', 'fact', 'decision', 'summary'].map((value) => ({ value, label: value }))}
              />
              <InputNumber min={0} max={1} step={0.1} value={memoryConfidence} onChange={(value) => setMemoryConfidence(Number(value ?? 1))} addonBefore={copy('Confidence', '置信度')} />
            </Space>
            <Input.TextArea rows={4} value={memoryContent} onChange={(event) => setMemoryContent(event.target.value)} placeholder={copy('A durable preference, fact, decision, or summary…', '持久化偏好、事实、决策或摘要……')} />
            <Input value={memoryTags} onChange={(event) => setMemoryTags(event.target.value)} placeholder={copy('Tags, comma separated', '标签，用逗号分隔')} />
            <Checkbox checked={memoryPinned} onChange={(event) => setMemoryPinned(event.target.checked)}>{copy('Pin in agent context', '固定加入 Agent 上下文')}</Checkbox>
            <Button type="primary" onClick={() => void saveMemory()} disabled={!memoryContent.trim()}>{copy('Save memory', '保存记忆')}</Button>
          </div>
          <Input.Search value={memoryQuery} onChange={(event) => setMemoryQuery(event.target.value)} onSearch={(value) => loadMemories(value)} allowClear placeholder={copy('Search content or tags', '搜索内容或标签')} />
          <List
            dataSource={memories}
            locale={{ emptyText: copy('No saved memories.', '暂无记忆。') }}
            renderItem={(item) => (
              <List.Item actions={[<Button key="archive" danger type="link" onClick={async () => { await archiveProjectMemory(projectId, item.id); loadMemories() }}>{copy('Archive', '归档')}</Button>]}>
                <List.Item.Meta
                  title={<Space><Tag>{item.scope}</Tag><Tag>{item.kind}</Tag>{item.pinned ? <Tag color="blue">pinned</Tag> : null}</Space>}
                  description={<><div>{item.content}</div><div className="mt-1">{item.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)}</div><div className="text-xs text-slate-400">{item.source} · confidence {item.confidence}</div></>}
                />
              </List.Item>
            )}
          />
        </div>
      )}
    </Drawer>
  )
}
