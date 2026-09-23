export type TaskCopyPreset = {
  title: string
  runningDescription: string
  cancellingDescription: string
  successDescription: string
  cancelledDescription: string
  failedDescription: string
  startedMessage: string
  reusedMessage: string
  cancelledImmediatelyMessage: string
  cancelRequestedMessage: string
  runningMessage: string
  cancellingMessage: string
}

const TASK_COPY_ZH = {
  chapterDivision: {
    title: '分镜提取',
    runningDescription: '系统正在后台提取分镜，完成后会自动刷新当前内容。',
    cancellingDescription: '已发送取消请求，系统会在当前步骤结束后停止。',
    successDescription: '分镜提取已完成，页面内容已自动刷新。',
    cancelledDescription: '分镜提取已取消。',
    failedDescription: '分镜提取失败，请稍后重试。',
    startedMessage: '已开始分镜提取',
    reusedMessage: '已恢复当前章节的分镜提取任务',
    cancelledImmediatelyMessage: '分镜提取已取消',
    cancelRequestedMessage: '已请求取消分镜提取',
    runningMessage: '当前已有分镜提取任务在运行',
    cancellingMessage: '当前分镜提取任务正在取消，请稍候',
  },
  scriptExtract: {
    title: '资产提取',
    runningDescription: '任务完成后会自动刷新资产与对白候选，无需手动刷新页面。',
    cancellingDescription: '已发送取消请求，系统会在当前步骤结束后停止，并在结束后自动刷新页面。',
    successDescription: '资产提取已完成，候选内容已自动刷新。',
    cancelledDescription: '资产提取已取消。',
    failedDescription: '资产提取失败，请稍后重试。',
    startedMessage: '已开始资产提取',
    reusedMessage: '已恢复当前章节的资产提取任务',
    cancelledImmediatelyMessage: '资产提取已取消',
    cancelRequestedMessage: '已请求取消资产提取',
    runningMessage: '当前已有资产提取任务在运行',
    cancellingMessage: '当前资产提取任务正在取消，请稍候',
  },
  consistencyCheck: {
    title: '一致性检查',
    runningDescription: '检查完成后会自动展示最新的一致性检查结果。',
    cancellingDescription: '已发送取消请求，系统会在当前步骤结束后停止，并在结束后同步最新结果。',
    successDescription: '一致性检查已完成，结果已自动更新。',
    cancelledDescription: '一致性检查已取消。',
    failedDescription: '一致性检查失败，请稍后重试。',
    startedMessage: '已开始一致性检查',
    reusedMessage: '已恢复当前章节的一致性检查任务',
    cancelledImmediatelyMessage: '一致性检查已取消',
    cancelRequestedMessage: '已请求取消一致性检查',
    runningMessage: '当前已有一致性检查任务在运行',
    cancellingMessage: '当前一致性检查任务正在取消，请稍候',
  },
  scriptSimplify: {
    title: '智能精简',
    runningDescription: '精简完成后会自动回填最新文本。',
    cancellingDescription: '已发送取消请求，系统会在当前步骤结束后停止。',
    successDescription: '智能精简已完成，最新文本已自动回填。',
    cancelledDescription: '智能精简已取消。',
    failedDescription: '智能精简失败，请稍后重试。',
    startedMessage: '已开始智能精简',
    reusedMessage: '已恢复当前章节的智能精简任务',
    cancelledImmediatelyMessage: '智能精简已取消',
    cancelRequestedMessage: '已请求取消智能精简',
    runningMessage: '当前已有智能精简任务在运行',
    cancellingMessage: '当前智能精简任务正在取消，请稍候',
  },
  scriptOptimize: {
    title: '一键优化',
    runningDescription: '优化完成后会自动回填原文内容。',
    cancellingDescription: '已发送取消请求，系统会在当前步骤结束后停止。',
    successDescription: '一键优化已完成，原文内容已自动回填。',
    cancelledDescription: '一键优化已取消。',
    failedDescription: '一键优化失败，请稍后重试。',
    startedMessage: '已开始一键优化',
    reusedMessage: '已恢复当前章节的一键优化任务',
    cancelledImmediatelyMessage: '一键优化已取消',
    cancelRequestedMessage: '已请求取消一键优化',
    runningMessage: '当前已有一键优化任务在运行',
    cancellingMessage: '当前一键优化任务正在取消，请稍候',
  },
  smartDetect: {
    title: '智能检测',
    runningDescription: '检测完成后会自动展示缺失项与优化描述。',
    cancellingDescription: '已发送取消请求，系统会在当前步骤结束后停止。',
    successDescription: '智能检测已完成，结果已自动更新。',
    cancelledDescription: '智能检测已取消。',
    failedDescription: '智能检测失败，请稍后重试。',
    startedMessage: '已开始智能检测',
    reusedMessage: '已恢复当前资产的智能检测任务',
    cancelledImmediatelyMessage: '智能检测已取消',
    cancelRequestedMessage: '已请求取消智能检测',
    runningMessage: '当前已有智能检测任务在运行',
    cancellingMessage: '当前智能检测任务正在取消，请稍候',
  },
  imageGeneration: {
    title: '图片生成',
    runningDescription: '系统正在后台生成图片，完成后会自动同步最新结果。',
    cancellingDescription: '已发送取消请求，系统会在当前步骤结束后停止。',
    successDescription: '图片生成已完成。',
    cancelledDescription: '图片生成已取消。',
    failedDescription: '图片生成失败，请稍后重试。',
    startedMessage: '已开始图片生成',
    reusedMessage: '已恢复当前图片生成任务',
    cancelledImmediatelyMessage: '图片生成已取消',
    cancelRequestedMessage: '已请求取消图片生成',
    runningMessage: '当前已有图片生成任务在运行',
    cancellingMessage: '当前图片生成任务正在取消，请稍候',
  },
  videoGeneration: {
    title: '视频生成',
    runningDescription: '系统正在后台生成视频，完成后可直接回到当前镜头查看。',
    cancellingDescription: '已发送取消请求，系统会在当前步骤结束后停止。',
    successDescription: '视频生成已完成。',
    cancelledDescription: '视频生成已取消。',
    failedDescription: '视频生成失败，请稍后重试。',
    startedMessage: '已开始视频生成',
    reusedMessage: '已恢复当前视频生成任务',
    cancelledImmediatelyMessage: '视频生成已取消',
    cancelRequestedMessage: '已请求取消视频生成',
    runningMessage: '当前已有视频生成任务在运行',
    cancellingMessage: '当前视频生成任务正在取消，请稍候',
  },
  shotFramePrompt: {
    title: '分镜提示词生成',
    runningDescription: '系统正在后台生成分镜提示词，完成后会自动回填当前内容。',
    cancellingDescription: '已发送取消请求，系统会在当前步骤结束后停止。',
    successDescription: '分镜提示词已生成。',
    cancelledDescription: '分镜提示词生成已取消。',
    failedDescription: '分镜提示词生成失败，请稍后重试。',
    startedMessage: '已开始分镜提示词生成',
    reusedMessage: '已恢复当前分镜提示词生成任务',
    cancelledImmediatelyMessage: '分镜提示词生成已取消',
    cancelRequestedMessage: '已请求取消分镜提示词生成',
    runningMessage: '当前已有分镜提示词生成任务在运行',
    cancellingMessage: '当前分镜提示词生成任务正在取消，请稍候',
  },
  shotFrameImage: {
    title: '关键帧图片生成',
    runningDescription: '系统正在后台生成关键帧图片，完成后会自动刷新当前缩略图。',
    cancellingDescription: '已发送取消请求，系统会在当前步骤结束后停止。',
    successDescription: '关键帧图片已生成。',
    cancelledDescription: '关键帧图片生成已取消。',
    failedDescription: '关键帧图片生成失败，请稍后重试。',
    startedMessage: '已开始关键帧图片生成',
    reusedMessage: '已恢复当前关键帧图片生成任务',
    cancelledImmediatelyMessage: '关键帧图片生成已取消',
    cancelRequestedMessage: '已请求取消关键帧图片生成',
    runningMessage: '当前已有关键帧图片生成任务在运行',
    cancellingMessage: '当前关键帧图片生成任务正在取消，请稍候',
  },
} satisfies Record<string, TaskCopyPreset>

export const TASK_KIND_TITLE_MAP: Record<string, string> = {
  script_divide: TASK_COPY_ZH.chapterDivision.title,
  script_extract: TASK_COPY_ZH.scriptExtract.title,
  script_consistency: TASK_COPY_ZH.consistencyCheck.title,
  script_simplify: TASK_COPY_ZH.scriptSimplify.title,
  script_optimize: TASK_COPY_ZH.scriptOptimize.title,
  script_character_portrait: '角色画像分析',
  script_prop_info: '道具信息分析',
  script_scene_info: '场景信息分析',
  script_costume_info: '服装信息分析',
  image_generation: '图片生成',
  video_generation: '视频生成',
  shot_frame_prompt: '分镜提示词生成',
}

const ENGLISH_TASK_KIND_TITLE_MAP: Record<string, string> = {
  script_divide: 'Shot extraction',
  script_extract: 'Asset extraction',
  script_consistency: 'Consistency check',
  script_simplify: 'Smart simplification',
  script_optimize: 'One-click optimization',
  script_character_portrait: 'Character portrait analysis',
  script_prop_info: 'Prop information analysis',
  script_scene_info: 'Scene information analysis',
  script_costume_info: 'Costume information analysis',
  image_generation: 'Image generation',
  video_generation: 'Video generation',
  shot_frame_prompt: 'Storyboard prompt generation',
}

function englishTaskCopy(title: string): TaskCopyPreset {
  return {
    title,
    runningDescription: `${title} is running in the background.`,
    cancellingDescription: 'Cancellation was requested. The task will stop after its current step.',
    successDescription: `${title} completed and the latest result is available.`,
    cancelledDescription: `${title} was cancelled.`,
    failedDescription: `${title} failed. Please try again.`,
    startedMessage: `${title} started.`,
    reusedMessage: `Resumed the current ${title.toLowerCase()} task.`,
    cancelledImmediatelyMessage: `${title} was cancelled.`,
    cancelRequestedMessage: `Cancellation requested for ${title.toLowerCase()}.`,
    runningMessage: `A ${title.toLowerCase()} task is already running.`,
    cancellingMessage: `The ${title.toLowerCase()} task is being cancelled.`,
  }
}

export const TASK_COPY: Record<keyof typeof TASK_COPY_ZH, TaskCopyPreset> = new Proxy(TASK_COPY_ZH, {
  get(target, key: string | symbol) {
    if (typeof key !== 'string') return Reflect.get(target, key)
    const chineseCopy = target[key as keyof typeof target]
    if (!chineseCopy || i18n.language === 'zh-CN') return chineseCopy
    const taskKindByPreset: Record<string, string> = {
      chapterDivision: 'script_divide',
      scriptExtract: 'script_extract',
      consistencyCheck: 'script_consistency',
      scriptSimplify: 'script_simplify',
      scriptOptimize: 'script_optimize',
      smartDetect: 'smart_detect',
      imageGeneration: 'image_generation',
      videoGeneration: 'video_generation',
      shotFramePrompt: 'shot_frame_prompt',
      shotFrameImage: 'shot_frame_image',
    }
    const fallbackTitle = key.replace(/([A-Z])/g, ' $1').replace(/^./, (char) => char.toUpperCase())
    return englishTaskCopy(ENGLISH_TASK_KIND_TITLE_MAP[taskKindByPreset[key]] ?? fallbackTitle)
  },
})

export const RELATION_TYPE_LABEL_MAP: Record<string, string> = {
  chapter_division: '章节',
  script_extraction: '章节',
  consistency_check: '章节',
  script_optimization: '章节',
  script_simplification: '章节',
  character_portrait_analysis: '资产',
  prop_info_analysis: '资产',
  scene_info_analysis: '资产',
  costume_info_analysis: '资产',
  video: '镜头视频',
  shot_first_frame_prompt: '首帧提示词',
  shot_last_frame_prompt: '尾帧提示词',
  shot_key_frame_prompt: '关键帧提示词',
  actor_image: '演员图片',
  scene_image: '场景图片',
  prop_image: '道具图片',
  costume_image: '服装图片',
  character_image: '角色图片',
  shot_frame_image: '分镜图片',
}

const ENGLISH_RELATION_TYPE_LABEL_MAP: Record<string, string> = {
  chapter_division: 'Chapter',
  script_extraction: 'Chapter',
  consistency_check: 'Chapter',
  script_optimization: 'Chapter',
  script_simplification: 'Chapter',
  character_portrait_analysis: 'Asset',
  prop_info_analysis: 'Asset',
  scene_info_analysis: 'Asset',
  costume_info_analysis: 'Asset',
  video: 'Shot video',
  shot_first_frame_prompt: 'First-frame prompt',
  shot_last_frame_prompt: 'Last-frame prompt',
  shot_key_frame_prompt: 'Key-frame prompt',
  actor_image: 'Actor image',
  scene_image: 'Scene image',
  prop_image: 'Prop image',
  costume_image: 'Costume image',
  character_image: 'Character image',
  shot_frame_image: 'Storyboard image',
}

export function resolveTaskTitle(taskKind?: string | null): string {
  const isChinese = i18n.language === 'zh-CN'
  if (!taskKind) return isChinese ? '后台任务' : 'Background task'
  return (isChinese ? TASK_KIND_TITLE_MAP : ENGLISH_TASK_KIND_TITLE_MAP)[taskKind] ?? taskKind.split('_').join(' ')
}

export function resolveTaskSourceLabel(
  relationType?: string | null,
  relationEntityId?: string | null,
): string | null {
  if (!relationType) return null
  const isChinese = i18n.language === 'zh-CN'
  const label = (isChinese ? RELATION_TYPE_LABEL_MAP : ENGLISH_RELATION_TYPE_LABEL_MAP)[relationType]
    ?? (isChinese ? '关联对象' : 'Related item')
  if (!relationEntityId) return label
  return isChinese ? `${label}：${relationEntityId}` : `${label}: ${relationEntityId}`
}
import i18n from '../../../i18n'
