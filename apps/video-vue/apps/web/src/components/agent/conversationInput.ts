export function messagePrompt(text: string, attachmentCount: number): string {
  return text.trim() || (attachmentCount ? '请检查我提供的客户素材，说明可读取的内容、用途和限制；不要把未读取的内容当成已确认事实。' : '');
}

export function resendMessageId(message: { id: string; entryId?: string }): string {
  return message.entryId ?? message.id;
}

export function canReadAttachments(providerId: string): boolean {
  return ['gemini', 'google', 'google-vertex', 'google-vertex-ai', 'openai', 'anthropic', 'claude'].includes(providerId.toLowerCase());
}

export function attachmentWarnings(providerId: string, attachments: { name: string; mimeType?: string; file?: { size: number } }[]): string[] {
  if (!attachments.length) return [];
  if (!canReadAttachments(providerId)) {
    return ['当前配置的附件读取能力由服务端校验；无法分析时会明确报错，不会将文件信息冒充内容分析。'];
  }
  const warnings: string[] = [];
  const videos = attachments.filter(item => item.mimeType?.startsWith('video/') || (!item.mimeType && /\.(mp4|mov|webm)$/i.test(item.name)));
  if (videos.length < attachments.length) warnings.push('图片可能使用缩放后的分析副本，细节可能减少；原始文件保持不变，具体读取方式以分析说明为准。');
  if (videos.length) {
    if (['openai', 'anthropic', 'claude'].includes(providerId.toLowerCase())) warnings.push('OpenAI / Claude 将读取带时间戳的采样帧，不读取音频，不覆盖全部帧；这不是原生完整视频分析。');
    else warnings.push('Gemini 视频会使用原生输入、受限分析副本或已配置的私有引用；实际方式、分析范围和细节变化会在分析说明中披露，原始视频保持不变。');
    warnings.push('450 MB 是视频上传限额，不是模型输入上限；服务端另行校验分析时长、范围、负载和处理并发，超限会明确提示。');
  }
  return warnings;
}

export function recoverDraft<T extends { path: string }>(current: T[], failed: T[]): T[] {
  return [...failed.filter(item => !item.path || !current.some(draft => draft.path === item.path)), ...current];
}

export type AgentRunScope = { directory: string; sessionFile: string; runId?: string };
/** Never cancel an unspecified/newer run after the UI has switched projects. */
export function cancelPayload(scope: AgentRunScope | undefined) {
  if (!scope?.directory || !scope.sessionFile || !scope.runId) return undefined;
  return { directory: scope.directory, sessionFile: scope.sessionFile, runId: scope.runId };
}
