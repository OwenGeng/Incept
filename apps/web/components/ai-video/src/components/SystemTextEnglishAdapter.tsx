import { useEffect, useRef } from 'react'
import { useAppStore } from '../store/useAppStore'

/**
 * Compatibility layer for AI Video screens which still embed legacy Chinese
 * labels. It intentionally translates only a closed list of system phrases.
 * Free-form scripts, prompts, asset names, and model output are never touched.
 * New or complex UI should still use normal i18n/copy calls at the component.
 */
const SYSTEM_COPY: Record<string, string> = {
  返回: 'Back',
  加载中: 'Loading',
  '加载中...': 'Loading…',
  '加载中…': 'Loading…',
  刷新: 'Refresh',
  保存: 'Save',
  已保存: 'Saved',
  保存失败: 'Save failed',
  取消: 'Cancel',
  关闭: 'Close',
  编辑: 'Edit',
  删除: 'Delete',
  创建: 'Create',
  新建: 'New',
  添加: 'Add',
  复制: 'Copy',
  导出: 'Export',
  更多: 'More',
  详情: 'Details',
  名称: 'Name',
  标题: 'Title',
  描述: 'Description',
  状态: 'Status',
  操作: 'Actions',
  设置: 'Settings',
  搜索: 'Search',
  筛选: 'Filter',
  排序: 'Sort',
  全部: 'All',
  已选: 'Selected',
  暂无数据: 'No data',
  暂无内容: 'No content',
  暂无分镜: 'No storyboards',
  没有匹配的分镜: 'No matching storyboards',
  分镜: 'Storyboard',
  分镜列表: 'Storyboards',
  分镜管理页: 'Storyboard management',
  创建分镜: 'Create storyboard',
  分镜标题: 'Storyboard title',
  一键提取分镜: 'Extract storyboards',
  分镜提取中: 'Extracting storyboards',
  重新提取需先清空分镜: 'Clear storyboards before extracting again',
  取消提取: 'Cancel extraction',
  正在取消: 'Cancelling',
  清空选择: 'Clear selection',
  批量删除: 'Delete selected',
  进入分镜工作室: 'Open storyboard studio',
  继续当前镜头: 'Continue current shot',
  剧本摘录: 'Script excerpt',
  准备度: 'Readiness',
  序号: 'No.',
  待确认: 'Needs review',
  生成中: 'Generating',
  已就绪: 'Ready',
  角色: 'Characters',
  场景: 'Scenes',
  道具: 'Props',
  服装: 'Costumes',
  资产: 'Assets',
  提示词模板: 'Prompt templates',
  模型管理: 'Models',
  供应商: 'Providers',
  演员: 'Actors',
  中文: 'Chinese',
  英文: 'English',
  请选择供应商: 'Choose a provider',
  选择供应商: 'Choose a provider',
  '加载供应商清单…': 'Loading provider catalog…',
  '搜索序号、标题或剧本摘录…': 'Search number, title, or script excerpt…',
  '确定删除该分镜？': 'Delete this storyboard?',
  请填写标题: 'Enter a title',
  可选: 'Optional',
  文件: 'Files',
  文件列表: 'Files',
  搜索文件名或标签: 'Search file names or tags',
  搜索文件名: 'Search file names',
  按标签筛选: 'Filter by tag',
  批量导出: 'Download selected',
  下载: 'Download',
  暂无文件: 'No files found',
  无法加载文件: 'Files could not be loaded',
  加载文件失败: 'Could not load files',
  视频编辑: 'Video editor',
  返回章节列表: 'Back to chapters',
  项目列表: 'Projects',
  导出成片: 'Export video',
  剪切: 'Trim',
  添加效果: 'Add effect',
  预览: 'Preview',
  素材库: 'Media library',
  '暂无素材，可从文件管理导入': 'No media yet. Import it from Files.',
  '时间线（拖拽素材到轨道）': 'Timeline (drag media onto a track)',
  轨道: 'Track',
  内容: 'Content',
  视频轨道: 'Video track',
  音频轨道: 'Audio track',
  拖入视频素材: 'Drop video media here',
  '拖入音频/配乐': 'Drop audio or music here',
  加载时间线失败: 'Could not load timeline',
  仪表盘: 'Dashboard',
  章节: 'Chapters',
  剪辑: 'Edit',
  草稿: 'Draft',
  拍摄中: 'In production',
  完成: 'Complete',
  项目不存在: 'Project not found',
  返回项目列表: 'Back to projects',
  创建第一章: 'Create first chapter',
  关联演员: 'Link actors',
  新建角色: 'New character',
  上传素材: 'Upload assets',
  新建场景: 'New scene',
  新建道具: 'New prop',
  新建服装: 'New costume',
  进入后期剪辑: 'Open post-production',
  处理首个已选: 'Open first selected',
  提取确认工作区: 'Extraction review',
  提取并刷新候选: 'Extract and refresh candidates',
  无需提取: 'No extraction needed',
  恢复提取: 'Resume extraction',
  对白确认: 'Dialogue review',
  全部接受: 'Accept all',
  全部忽略: 'Ignore all',
  新提取: 'Newly extracted',
  镜头基础信息: 'Shot details',
  镜头语言默认值: 'Shot language defaults',
  '内容 / 剧本摘录': 'Content / script excerpt',
  景别: 'Framing',
  机位: 'Camera angle',
  运镜: 'Camera movement',
  '时长（秒）': 'Duration (seconds)',
  动作拍点: 'Action beats',
  新增一条: 'Add beat',
  准备完成: 'Preparation complete',
  待继续准备: 'Preparation needed',
  进入工作室: 'Open studio',
  分镜工作室: 'Storyboard studio',
  关键帧: 'Keyframes',
  关键帧与参考图: 'Keyframes & references',
  图片生成: 'Image generation',
  视频生成: 'Video generation',
  生成图片: 'Generate image',
  生成视频: 'Generate video',
  加载失败: 'Could not load',
  重试: 'Try again',
  保存基础信息: 'Save details',
  保存标题失败: 'Could not save title',
  保存备注失败: 'Could not save notes',
  保存设置: 'Save settings',
  参数: 'Parameters',
  全局默认模型与参数: 'Global default model and parameters',
  全局种子值: 'Global seed',
  历史记录: 'History',
  历史生成图片: 'Generated image history',
  任务中心: 'Task center',
  任务产物: 'Task output',
  一键优化: 'Optimize',
  优化中: 'Optimizing',
  优化完成: 'Optimization complete',
  一致性检查: 'Consistency check',
  发现问题: 'Issues found',
  前往分镜编辑页处理提取与确认: 'Open storyboard editor to review extraction',
  前往系统设置: 'Open system settings',
}

const SYSTEM_PATTERNS: Array<[RegExp, (match: RegExpMatchArray) => string]> = [
  [/^已选\s+(\d+)\s+项$/, (match) => `${match[1]} selected`],
  [/^全部\s+(\d+)$/, (match) => `All ${match[1]}`],
  [/^待确认\s+(\d+)$/, (match) => `Needs review ${match[1]}`],
  [/^生成中\s+(\d+)$/, (match) => `Generating ${match[1]}`],
  [/^已就绪\s+(\d+)$/, (match) => `Ready ${match[1]}`],
  [/^第(\d+)章$/, (match) => `Chapter ${match[1]}`],
  [/^第(\d+)章\s*·\s*(.+)$/, (match) => `Chapter ${match[1]} · ${match[2]}`],
  [/^视频\s+(\d+)$/, (match) => `Video ${match[1]}`],
  [/^已关联场景：(.+)$/, (match) => `Linked scene: ${match[1]}`],
]

const EXCLUDED_SELECTOR = [
  'input',
  'textarea',
  'select',
  '[contenteditable="true"]',
  '[role="textbox"]',
  'pre',
  'code',
  '.monaco-editor',
  '.ProseMirror',
  '[data-ai-video-user-content]',
].join(',')

function translateSystemText(source: string): string | null {
  const exact = SYSTEM_COPY[source]
  if (exact) return exact
  for (const [pattern, translate] of SYSTEM_PATTERNS) {
    const match = source.match(pattern)
    if (match) return translate(match)
  }
  return null
}

function isSafeSystemNode(node: Text): boolean {
  const parent = node.parentElement
  return Boolean(parent && !parent.closest(EXCLUDED_SELECTOR))
}

export function SystemTextEnglishAdapter() {
  const language = useAppStore((state) => state.language)
  const originalText = useRef(new Map<Text, string>())
  const originalAttributes = useRef(new Map<Element, Map<string, string>>())

  useEffect(() => {
    const root = document.getElementById('root')
    if (!root) return

    const restoreChinese = () => {
      originalText.current.forEach((source, node) => {
        if (node.isConnected) node.data = source
      })
      originalAttributes.current.forEach((attributes, element) => {
        if (!element.isConnected) return
        attributes.forEach((source, attribute) => element.setAttribute(attribute, source))
      })
      originalText.current.clear()
      originalAttributes.current.clear()
    }

    if (language === 'zh-CN') {
      restoreChinese()
      return
    }

    const translateTextNode = (node: Text) => {
      if (!isSafeSystemNode(node)) return
      const source = originalText.current.get(node) ?? node.data
      const leadingWhitespace = source.match(/^\s*/)?.[0] ?? ''
      const trailingWhitespace = source.match(/\s*$/)?.[0] ?? ''
      const translated = translateSystemText(source.trim())
      if (!translated) return
      if (!originalText.current.has(node)) originalText.current.set(node, source)
      const next = `${leadingWhitespace}${translated}${trailingWhitespace}`
      if (node.data !== next) node.data = next
    }

    const translateAttributes = (element: Element) => {
      for (const attribute of ['title', 'placeholder', 'aria-label']) {
        const current = element.getAttribute(attribute)
        if (!current) continue
        const source = originalAttributes.current.get(element)?.get(attribute) ?? current
        const translated = translateSystemText(source.trim())
        if (!translated) continue
        if (!originalAttributes.current.has(element)) originalAttributes.current.set(element, new Map())
        originalAttributes.current.get(element)?.set(attribute, source)
        if (current !== translated) element.setAttribute(attribute, translated)
      }
    }

    const translateTree = (node: Node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        translateTextNode(node as Text)
        return
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return
      const element = node as Element
      if (element.closest(EXCLUDED_SELECTOR)) return
      translateAttributes(element)
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT)
      let textNode = walker.nextNode() as Text | null
      while (textNode) {
        translateTextNode(textNode)
        textNode = walker.nextNode() as Text | null
      }
      element.querySelectorAll('*').forEach(translateAttributes)
    }

    translateTree(root)
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === 'characterData') translateTextNode(mutation.target as Text)
        if (mutation.type === 'attributes') translateAttributes(mutation.target as Element)
        mutation.addedNodes.forEach(translateTree)
      })
    })
    observer.observe(root, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['title', 'placeholder', 'aria-label'] })

    return () => observer.disconnect()
  }, [language])

  return null
}
