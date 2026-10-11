// Only product events cross the private process boundary. Provider payloads and
// private reasoning remain in Pi; bounded tool summaries are safe to render.
export function safeValue(value: unknown, depth = 0, budget = { remaining: 40000 }): any {
  if (budget.remaining <= 0 || depth > 6) return '[value omitted]';
  if (typeof value === 'string') {
    if (value.length <= 200000 && /^[\[{]/.test(value.trim())) {
      try { return JSON.stringify(safeValue(JSON.parse(value), depth + 1, budget)); } catch {}
    }
    const text = value.replace(/data:[^;,\s]+;base64,[A-Za-z0-9+/=]+/g, '[binary omitted]')
      .replace(/Bearer\s+\S+/gi, 'Bearer [redacted]').slice(0, Math.min(12000, budget.remaining));
    budget.remaining -= Buffer.byteLength(JSON.stringify(text), 'utf8') + 8;
    return text;
  }
  if (Array.isArray(value)) {
    const items: any[] = [];
    for (const item of value.slice(0, 100)) {
      if (budget.remaining <= 0) { items.push('[remaining items omitted]'); break; }
      items.push(safeValue(item, depth + 1, budget));
    }
    return items;
  }
  if (value && typeof value === 'object') {
    const entries: [string, any][] = [];
    for (const [key, item] of Object.entries(value).slice(0, 100)) {
      if (budget.remaining <= 0) { entries.push(['_truncated', true]); break; }
      budget.remaining -= Buffer.byteLength(JSON.stringify(key.slice(0, 128)), 'utf8') + 8;
      entries.push([key.slice(0, 128), /^(api.?key|authorization|password|secret|token|data|base64|thinking|thought|reasoning|signature)$/i.test(key)
        ? '[redacted]' : safeValue(item, depth + 1, budget)]);
    }
    return Object.fromEntries(entries);
  }
  budget.remaining -= 24;
  return value;
}

function resultSummary(result: any) {
  const text = result?.content?.filter((part: any) => part.type === 'text').map((part: any) => safeValue(part.text)).join('\n');
  return text || JSON.stringify(safeValue(result?.details ?? result));
}

export function createEventProjector(send: (event: any) => void) {
  let messageNumber = 0;
  const parts: any[] = [];
  const emit = (event: any) => { send(event); };
  const textParts = new Map<string, any>();
  const tools = new Map<string, any>();
  return { parts, emit, accept(event: any) {
    if (event.type === 'message_start' && event.message.role === 'assistant') messageNumber++;
    if (event.type === 'compaction_start' || event.type === 'compaction_end')
      emit({ type: 'compaction', active: event.type === 'compaction_start' });
    if (event.type === 'message_update' && event.assistantMessageEvent.type.startsWith('text_')) {
      const update = event.assistantMessageEvent;
      const blockId = `text-${messageNumber}-${update.contentIndex}`;
      let part = textParts.get(blockId);
      if (!part) { part = { id: blockId, type: 'text', blockId, content: '' }; textParts.set(blockId, part); parts.push(part); }
      if (update.type === 'text_delta') { part.content += update.delta; emit({ type: 'text', blockId, delta: update.delta }); }
      if (update.type === 'text_end') { part.content = update.content; part.done = true;
        emit({ type: 'text', blockId, content: update.content, done: true }); }
    }
    if (event.type === 'message_update' && event.assistantMessageEvent.type.startsWith('toolcall_')) {
      const update = event.assistantMessageEvent;
      const call = update.partial?.content[update.contentIndex];
      if (call?.type === 'toolCall' && call.id && call.name) {
        let part = tools.get(call.id);
        if (!part) { part = { id: `tool-${call.id}`, type: 'tool', blockId: `tool-${call.id}`, tool: { id: call.id, name: call.name, status: 'running' } };
          tools.set(call.id, part); parts.push(part); }
        part.tool.args = safeValue(call.arguments ?? {}); emit(structuredClone(part));
      }
    }
    if (event.type.startsWith('tool_execution_')) {
      const id = event.toolCallId;
      let part = tools.get(id);
      if (!part) { part = { id: `tool-${id}`, type: 'tool', blockId: `tool-${id}`, tool: { id, name: event.toolName,
        args: safeValue(event.args ?? {}), status: 'running' } }; tools.set(id, part); parts.push(part); }
      if (event.type === 'tool_execution_update') part.tool.result = resultSummary(event.partialResult);
      if (event.type === 'tool_execution_end') {
        part.tool.status = event.isError ? (/cancel|abort|interrupted/i.test(JSON.stringify(event.result)) ? 'interrupted' : 'error') : 'success';
        part.tool.result = resultSummary(event.result);
      }
      emit(structuredClone(part));
    }
  }, interrupt() {
    for (const part of tools.values()) if (part.tool.status === 'running') {
      part.tool.status = 'interrupted'; emit(structuredClone(part));
    }
  } };
}
