const mimeByExtension: Record<string, string> = {
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp',
  gif: 'image/gif', avif: 'image/avif', mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime',
};

/** Upload admission only. Provider/preprocessing budgets are enforced separately by the server. */
export function selectAttachments<T extends { name: string; type: string; size: number }>(files: T[], existingCount: number) {
  const accepted: { file: T; mimeType: string }[] = [];
  const errors: string[] = [];
  for (const file of files) {
    const mimeType = file.type || mimeByExtension[file.name.split('.').at(-1)?.toLowerCase() ?? ''] || '';
    if (!/^(image|video)\//.test(mimeType)) { errors.push(`${file.name}：只支持图片和视频文件`); continue; }
    const video = mimeType.startsWith('video/');
    const limit = video ? 450_000_000 : 100 * 1024 * 1024;
    if (!Number.isSafeInteger(file.size) || file.size <= 0 || file.size > limit) {
      errors.push(`${file.name}：${video ? '视频' : '图片'}不能为空且不能超过 ${video ? '450 MB（450,000,000 字节）' : '100 MiB'} 上传限额`); continue;
    }
    if (existingCount + accepted.length >= 20) { errors.push('每条消息最多添加 20 个附件'); break; }
    accepted.push({ file, mimeType });
  }
  return { accepted, errors };
}
