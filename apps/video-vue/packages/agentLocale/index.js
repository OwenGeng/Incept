// Translate application-owned status only; preserve user and model content.
export const nativePhraseEntries = [
  [
    "准备执行",
    "Preparing task"
  ],
  [
    "正在处理",
    "Processing"
  ],
  [
    "上次运行已中断",
    "The previous run was interrupted"
  ],
  [
    "子任务与团队",
    "Subtasks and teams"
  ],
  [
    "全局记忆",
    "Memory"
  ],
  [
    "上报父 Agent",
    "Report to parent agent"
  ],
  [
    "已上报父 Agent",
    "Reported to parent agent"
  ],
  [
    "父会话标识无效",
    "Invalid parent conversation identifier"
  ],
  [
    "请选择要删除的消息",
    "Select the messages to delete"
  ],
  [
    "会话文件损坏，无法删除消息",
    "The conversation file is corrupted; messages cannot be deleted"
  ],
  [
    "会话文件无效",
    "Invalid conversation file"
  ],
  [
    "会话记录结构无效，无法删除消息",
    "Invalid conversation structure; messages cannot be deleted"
  ],
  [
    "消息不在当前对话中，请重新打开对话",
    "The message is not in the current conversation. Reopen it."
  ],
  [
    "请输入消息或添加图片、视频",
    "Enter a message or attach an image or video"
  ],
  [
    "附件必须是工作区内非空且不超过 100 MB 的文件",
    "Attachments must be nonempty workspace files no larger than 100 MB"
  ],
  [
    "重发需要指定原对话",
    "Resending requires the original conversation"
  ],
  [
    "对话正在运行，请等待回复完成",
    "The conversation is running. Wait for the response to finish."
  ],
  [
    "子 Agent 运行时不能重发历史消息",
    "History cannot be resent while the sub-agent is running"
  ],
  [
    "子 Agent 正在准备或结束回复，请稍后发送",
    "The sub-agent is starting or finishing a response. Try again shortly."
  ],
  [
    "请等子 Agent 当前回复结束后发送附件",
    "Wait for the sub-agent response to finish before sending attachments"
  ],
  [
    "会话不存在，请重新打开对话",
    "Conversation not found. Reopen the conversation."
  ],
  [
    "会话必须是普通文件",
    "The conversation must be a regular file"
  ],
  [
    "重发消息不在当前对话中，请重新打开对话",
    "The resent message is not in the current conversation. Reopen it."
  ],
  [
    "模型返回了空摘要，已保留原上下文",
    "The model returned an empty summary. The original context was preserved."
  ],
  [
    "模型请求失败",
    "Model request failed"
  ],
  [
    "模型回复因长度限制被截断，未能完整生成回答。",
    "The model response reached its length limit and is incomplete."
  ],
  [
    "任务正在等待调用方补充输入，不能继续执行工具",
    "The task is waiting for input; tool execution cannot continue"
  ],
  [
    "子任务没有返回回复",
    "The subtask returned no response"
  ],
  [
    "子任务执行失败",
    "Subtask failed"
  ],
  [
    "子任务没有返回文本结果",
    "The subtask returned no text result"
  ],
  [
    "本地记忆已关闭，请遵循用户的设置，不再读取或保存记忆",
    "Memory is disabled. Do not read or save memory."
  ],
  [
    "保存记忆需要提供 content 和最近读取的 revision",
    "Saving memory requires content and the most recently read revision"
  ],
  [
    "只有远端 A2A 团队支持 taskId/contextId",
    "Only remote A2A teams support taskId/contextId"
  ],
  [
    "未收到响应流",
    "No response stream was received"
  ],
  [
    "连接已中断，请重试",
    "The connection was interrupted. Try again."
  ],
  [
    "提问缺少对应的工具调用",
    "The question has no matching tool call"
  ],
  [
    "Agent 正在运行，请先停止",
    "The agent is running. Stop it first."
  ],
  [
    "工具名称 subAgent 已被内置子任务工具占用",
    "The tool name subAgent is reserved by the native host"
  ],
  [
    "工具名称 memory 已被内置全局记忆工具占用",
    "The tool name memory is reserved by the native host"
  ],
  [
    "工具名称 report 已被内置上报工具占用",
    "The tool name report is reserved by the native host"
  ]
];
export function nativeSystemText(value, language) {
  const english = language.startsWith('en');
  for (const [zh, en] of nativePhraseEntries) {
    if (value === zh || value === en) return english ? en : zh;
  }
  if (english) return value.replace(/^正在调用 (.+)$/, 'Calling $1')
    .replace(/^上下文压缩失败：/, 'Context compression failed: ')
    .replace(/^请求失败（(\d+)）$/, 'Request failed ($1)');
  return value.replace(/^Calling (.+)$/, '正在调用 $1')
    .replace(/^Context compression failed: /, '上下文压缩失败：')
    .replace(/^Request failed \((\d+)\)$/, '请求失败（$1）');
}
export function nativeToolResult(value, name, language) {
  if (name === 'web_search') {
    try {
      const receipt = typeof value === 'string' ? JSON.parse(value) : value;
      if (receipt?.status === 'research_incomplete') {
        const localized = {...receipt, message: language.startsWith('en')
          ? 'Research incomplete: search returned no usable sources. Continue with verified existing materials or user-provided URLs; disclose the missing research and do not invent findings.'
          : '调研未完成：搜索未返回可用来源。可使用已有的可核实资料或用户提供的链接继续；须说明调研缺口，不能编造结果。'};
        return typeof value === 'string' ? JSON.stringify(localized) : localized;
      }
    } catch {}
  }
  if (name === 'report' && typeof value === 'string') return nativeSystemText(value, language);
  if (name !== 'subAgent' || typeof value !== 'string') return value;
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed.tasks)) return value;
    return JSON.stringify({...parsed, tasks: parsed.tasks.map((task) => ({...task,
      result: ['running','error','cancelled'].includes(task.status) && typeof task.result === 'string'
        ? nativeSystemText(task.result, language) : task.result}))});
  } catch { return value; }
}
