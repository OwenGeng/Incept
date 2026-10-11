/** Application chrome only; never pass customer descriptions or names here. */
export const assetUiPhrases: ReadonlyArray<readonly [string, string]> = [
  ['客户网站素材', 'Client website assets'],
  ['客户网站素材库', 'Client website asset library'],
  ['客户网站素材 · 图片 / 视频 / Logo', 'Client website assets · Images / Videos / Logos'],
  ['客户官网或产品页面URL', 'Client website or product page URL'],
  ['https://客户官网 / 产品页面 / Best seller页面', 'https://client-website / product-page / bestseller-page'],
  ['发现素材', 'Discover assets'], ['导入选中素材', 'Import selected assets'],
  ['素材类型筛选', 'Filter asset type'], ['全部', 'All'], ['图标', 'Icon'],
  ['待导入', 'Not imported'], ['已导入', 'Imported'], ['导入失败', 'Import failed'],
  ['没有此类素材', 'No assets of this type'],
  ['填写客户网页发现素材，或让Agent采集后点击刷新。', 'Enter a client webpage to discover assets, or refresh after the Agent collects them.'],
  ['预览不可用', 'Preview unavailable'], ['导入后可预览', 'Import to preview'],
  ['官网未提供描述', 'No description provided by the website'], ['授权待确认', 'Usage rights require confirmation'],
  ['产品页面', 'Product page'], ['来源网页', 'Source page'], ['原始素材', 'Original asset'],
  ['交给Agent', 'Attach to Agent'], ['检查CTV交付规格', 'Check CTV delivery specs'],
  ['已添加到当前Agent输入框；不会自动发送。', 'Added to the current Agent input; not sent automatically.'],
  ['请先打开一个Agent对话，并确保输入框可添加附件。', 'Open an Agent conversation and make sure attachments can be added.'],
  ['素材操作失败', 'Asset operation failed'], ['请输入完整的HTTPS客户网页地址', 'Enter a complete HTTPS client webpage URL'],
  ['Moloco CTV制作规格 · 已确认客户配置', 'Moloco CTV production specs · Customer-confirmed configuration'],
  ['Moloco通用视频指南', 'Moloco video creative guide'],
  ['通用视频指南的End card：JPEG/JPG/PNG/GIF，方向与视频一致，宽高均≥320px；≤500KB，GIF≤1MB。CTV是否使用独立End card需另行确认。', 'Generic video end card: JPEG/JPG/PNG/GIF, matching video orientation, both dimensions ≥320px; ≤500KB, GIF ≤1MB. Confirm separately whether this CTV placement uses a standalone end card.'],
  ['仅采集公开静态网页中的图片、Logo、图标及视频直链；不绕过登录或视频保护。官网热销标记不等于销量排名，广告使用权须客户确认。导入不代表 Agent 已分析画面。Gemini、OpenAI、Claude 均可读取图片，可能使用缩放后的分析副本；Gemini 视频使用原生输入、受限分析副本或已有私有引用，OpenAI / Claude 读取带时间戳的采样帧，不读取音频且不覆盖全部帧。实际分析范围与处理限制以服务端说明为准，原始素材保持不变。', 'Collects images, logos, icons and direct video links from public static pages only; does not bypass login or video protection. Bestseller labels are not verified sales rankings. The client must confirm advertising rights. Importing does not mean the Agent has analyzed the media. Gemini, OpenAI and Claude can inspect images, potentially using resized analysis copies. Gemini uses native video, a bounded analysis copy or an existing private reference. OpenAI / Claude inspect timestamped sample frames without audio or full-frame coverage. The server reports actual analysis coverage and processing limits; originals remain unchanged.'],
  ['点击填入提示，也可以上传、拖入或粘贴客户图片和视频。', 'Choose a prompt, or upload, drag in or paste client images and videos.'],
  ['松开添加图片或视频 · 不会自动发送', 'Drop to attach images or videos · Not sent automatically'],
  ['每条最多 20 个附件；图片上传限额 100 MiB，视频 450 MB（450,000,000 字节）；分析与并发限制由服务端校验', 'Up to 20 attachments per message; image upload limit 100 MiB, video 450 MB (450,000,000 bytes). The server enforces analysis and concurrency limits.'],
  ['每条消息最多添加 20 个附件', 'Up to 20 attachments per message'],
  ['项 · 已选择', 'assets · Selected'],
  ['当前配置的附件读取能力由服务端校验；无法分析时会明确报错，不会将文件信息冒充内容分析。', 'The server checks attachment support for the selected provider. Unsupported analysis produces an explicit error; file metadata is never presented as content analysis.'],
  ['图片可能使用缩放后的分析副本，细节可能减少；原始文件保持不变，具体读取方式以分析说明为准。', 'Images may use resized analysis copies with reduced detail. Originals remain unchanged; the analysis report describes how they were read.'],
  ['OpenAI / Claude 将读取带时间戳的采样帧，不读取音频，不覆盖全部帧；这不是原生完整视频分析。', 'OpenAI / Claude inspect timestamped sample frames without audio or full-frame coverage; this is not native full-video analysis.'],
  ['Gemini 视频会使用原生输入、受限分析副本或已配置的私有引用；实际方式、分析范围和细节变化会在分析说明中披露，原始视频保持不变。', 'Gemini video uses native input, a bounded analysis copy or a configured private reference. The report describes the method, coverage and detail changes; the original remains unchanged.'],
  ['450 MB 是视频上传限额，不是模型输入上限；服务端另行校验分析时长、范围、负载和处理并发，超限会明确提示。', '450 MB is the video upload limit, not the model input limit. The server separately checks analysis duration, coverage, payload and processing concurrency, and reports exceeded limits.'],
  ['移除附件', 'Remove attachment'],
  ['文件超过允许大小；请缩小文件或拆分上传。', 'File exceeds the size limit; reduce its size or split the upload.'],
  ['视频不能超过 450 MB；其他工作区文件不能超过 500 MiB。', 'Videos must not exceed 450 MB; other workspace files must not exceed 500 MiB.'],
  ['网站素材目录过大', 'Website asset catalog is too large'],
  ['网站素材目录损坏，未覆盖已有内容', 'Website asset catalog is invalid; existing content was not overwritten'],
  ['网站素材采集仅支持HTTPS链接', 'Website asset collection supports HTTPS links only'],
  ['无法解析网站地址', 'Could not resolve the website address'],
  ['禁止访问内网或非公开地址', 'Private or non-public addresses are not allowed'],
  ['请输入公开HTML网页地址', 'Enter a public HTML webpage URL'],
  ['网页超过2MB采集限制', 'Page exceeds the 2MB collection limit'], ['网页重定向过多', 'Too many webpage redirects'],
  ['网页超过8MB采集限制', 'Page exceeds the 8MB collection limit'],
  ['素材发现超过90秒采集限制', 'Asset discovery exceeds the 90-second limit'],
  ['素材发现超过32MB总采集限制', 'Asset discovery exceeds the 32MB total limit'],
  ['素材发现达到总大小或时间限制；已发现素材保留，请按商品页分批继续。', 'Discovery reached the total size or time limit. Discovered assets were preserved; continue in batches by product page.'],
  ['素材发现达到巡查上限；未巡查的页面不代表没有素材，请按商品页继续。', 'Discovery reached its page limit. Unvisited pages may contain more assets; continue by product page.'],
  ['项目网站素材最多200项；已有素材保留，未继续添加。', 'Up to 200 website assets per project; existing assets were preserved and no further assets were added.'],
  ['文件不是支持的图片/视频格式（不导入HTML、SVG或流媒体播放列表）', 'Unsupported image/video format (HTML, SVG and streaming playlists are not imported)'],
  ['每次请选择1–12个已发现的素材', 'Select 1–12 discovered assets at a time'],
  ['只能导入当前项目已发现的素材', 'Only assets discovered in the current project can be imported'],
  ['本批采集超时，请分批重试', 'Collection timed out; retry in smaller batches'],
  ['素材超过采集大小限制', 'Asset exceeds the collection size limit'],
  ['素材超出大小/时间限制，未保存不完整文件', 'Asset exceeded size/time limits; no incomplete file was saved'],
  ['素材实际格式与发现类型不符', 'Actual asset format does not match the discovered type'],
  ['来源文件已变化，未覆盖已有素材', 'Source file changed; the existing asset was not overwritten'],
  ['交付格式必须为MP4', 'Delivery format must be MP4'], ['视频超过450MB', 'Video exceeds 450MB'],
  ['未检测到视频轨道', 'No video track detected'],
  ['交付分辨率需为1920×1080或1280×720', 'Delivery resolution must be 1920×1080 or 1280×720'],
  ['未确认帧率达到24 FPS', 'Could not confirm a frame rate of at least 24 FPS'],
  ['当前时长不在推荐的15/30/60秒档位', 'Duration is not one of the recommended 15/30/60 seconds'],
  ['未确认时长在6–180秒范围内', 'Could not confirm a duration within 6–180 seconds'],
  ['无法读取视频技术参数；请确认文件有效且部署包含ffprobe', 'Could not read video metadata; check the file and ensure ffprobe is installed'],
  ['视频探测结果无效', 'Invalid video probe result'],
];
const phrases = new Map(assetUiPhrases);

export function assetUiEnglish(source: string): string {
  const exact = phrases.get(source);
  if (exact !== undefined) return exact;
  for (const [zh, en] of assetUiPhrases) {
    if (zh.endsWith('。') && source.startsWith(zh + ' ')) return en + ' ' + assetUiEnglish(source.slice(zh.length + 1));
  }
  if (source.includes('；') && (source.match(/：(?:只支持|视频不能为空|图片不能为空)/gu)?.length ?? 0) > 1) {
    return source.split('；').map(assetUiEnglish).join('; ');
  }
  const rules: ReadonlyArray<readonly [RegExp, string]> = [
    [/^(.+)：只支持图片和视频文件$/u, '$1: Only image and video files are supported'],
    [/^(.+)：视频不能为空且不能超过 450 MB（450,000,000 字节） 上传限额$/u, '$1: Video must be non-empty and within the 450 MB (450,000,000 bytes) upload limit'],
    [/^(.+)：图片不能为空且不能超过 100 MiB 上传限额$/u, '$1: Image must be non-empty and within the 100 MiB upload limit'],
    [/^(\d+)项 · 已选择(\d+)项$/u, '$1 assets · $2 selected'],
    [/^选择 (.+)$/u, 'Select $1'],
    [/^检查了(\d+)个页面，发现目录共(\d+)项。/u, 'Inspected $1 pages; $2 assets in the catalog.'],
    [/^已导入(\d+)项，失败(\d+)项。已保存到素材库website文件夹；授权待客户确认。$/u, 'Imported $1; failed $2. Saved to the website folder in the asset library; client confirmation of usage rights is required.'],
    [/^网站返回HTTP (\d+)，未绕过访问限制$/u, 'Website returned HTTP $1; access restrictions were not bypassed'],
    [/^素材返回HTTP (\d+)；未跟随重定向或绕过访问限制$/u, 'Asset returned HTTP $1; redirects and access restrictions were not bypassed'],
    [/^(.+)：已通过客户CTV配置技术检查（不代表广告使用权或平台审核已获批准）。/u, '$1: Passed the customer CTV technical checks (not advertising-rights clearance or platform approval). '],
    [/^(.+)：未通过CTV交付技术检查（源素材可继续用于剪辑）。/u, '$1: Failed CTV delivery technical checks (source material can still be edited). '],
  ];
  let result = source;
  for (const [pattern, replacement] of rules) result = result.replace(pattern, replacement);
  // Translate only the server-owned trailing diagnostics, not the filename or
  // asset name carried in the prefix of the result.
  const composite = result.match(/^(Inspected \d+ pages; \d+ assets in the catalog\.)(.*)$/su)
    ?? result.match(/^(.*: (?:Passed the customer CTV technical checks \(not advertising-rights clearance or platform approval\)|Failed CTV delivery technical checks \(source material can still be edited\))\. )(.*)$/su);
  if (composite) return composite[1]! + composite[2]!.split('；').map(assetUiEnglish).join('; ');
  if (result === source && source.includes('；')) {
    const pieces = source.split('；').map(assetUiEnglish);
    if (pieces.join('；') !== source) return pieces.join('; ');
  }
  if (/^16:9 · MP4 · 推荐/u.test(result)) result = result.replace('推荐', 'Recommended');
  if (/^· 接受1280×720 · ≥/u.test(result)) result = result.replace('接受', 'Accepted ');
  if (/^秒 · 推荐/u.test(result)) result = result.replace('秒 · 推荐', 's · Recommended ');
  if (result === '秒') result = 's';
  return result;
}
