import { restoredLocaleText } from "./localeRestore";
import { nativePhraseEntries } from "@linglonglab/video-runtime-types/agent/locale";
import { computed, onMounted, onUnmounted, watch } from "vue";
import { uiSettings, updateUiSettings } from "@/stores/settings";
import { dynamicUiTranslations, extendedUiPhraseEntries, nodeUiPhraseEntries, uiPhraseEntries } from "@/i18nCatalog";
import { assetUiEnglish } from "@/assetUiLocale";

export type InterfaceLanguage = "zh-CN" | "en";

export const interfaceLanguage = computed<InterfaceLanguage>(() => uiSettings.value.language);
export const isEnglish = computed(() => interfaceLanguage.value === "en");

export function setInterfaceLanguage(language: InterfaceLanguage) {
  updateUiSettings({ language });
}

export function t(chinese: string, english: string) {
  return isEnglish.value ? english : chinese;
}

/**
 * Compatibility catalogue for the restored Vue workspace.
 *
 * The upstream UI contains a large amount of literal Chinese copy across
 * separately-built node bundles.  During the migration we keep those bundles
 * source-compatible and translate their rendered chrome here. User-authored
 * canvas, document, prompt and project content is deliberately excluded.
 */
const phrases = new Map<string, string>([
  ...nativePhraseEntries,
  ["模型与推理设置", "Model and reasoning settings"],
  ["创建项目并发送", "Create project and send"],
  ["返回 LinglongLab", "Back to LinglongLab"],
  ["云端项目 · 自动保存", "Cloud project · Autosaved"],
  ["灵感创作模式", "Creative mode"],
  ["创作描述", "Creative brief"],
  ["项目列表", "Projects"],
  ["导入项目", "Import project"],
  ["添加项目", "New project"],
  ["按时间降序", "Newest first"],
  ["按时间升序", "Oldest first"],
  ["项目视图", "Project view"],
  ["网格视图", "Grid view"],
  ["列表视图", "List view"],
  ["最近打开", "Last opened"],
  ["打开项目", "Open project"],
  ["重命名项目", "Rename project"],
  ["删除云端项目", "Delete cloud project"],
  ["删除项目", "Delete project"],
  ["未命名项目", "Untitled project"],
  ["请输入项目名称", "Enter a project name"],
  ["项目名称不能为空", "Project name is required"],
  ["创建项目失败，请重试", "Could not create the project. Try again."],
  ["无法打开项目，请重试", "Could not open the project. Try again."],
  ["读取项目列表失败", "Could not load projects"],
  ["导入项目失败", "Could not import the project"],
  ["重命名项目失败", "Could not rename the project"],
  ["删除项目失败", "Could not delete the project"],
  ["永久删除", "Permanently delete"],
  ["及其素材", "and its assets"],
  ["确定", "Confirm"],
  ["保存", "Save"],
  ["取消", "Cancel"],
  ["删除", "Delete"],
  ["重命名", "Rename"],
  ["设置", "Settings"],
  ["界面设置", "Appearance"],
  ["常规配置", "General"],
  ["文本模型", "Text models"],
  ["媒体模型", "Media models"],
  ["隐私", "Privacy"],
  ["关于", "About"],
  ["模型", "Models"],
  ["其他", "Other"],
  ["设置分类", "Settings categories"],
  ["语言", "Language"],
  ["中文", "Chinese"],
  ["英文", "English"],
  ["让创作空间更合你的习惯，修改会自动保存。", "Make the workspace yours. Changes save automatically."],
  ["外观模式", "Appearance mode"],
  ["浅色", "Light"],
  ["深色", "Dark"],
  ["跟随系统", "System"],
  ["明亮清晰", "Bright and clear"],
  ["沉浸创作", "Focused creation"],
  ["自动切换", "Switch automatically"],
  ["主题颜色", "Accent color"],
  ["用于按钮、选中状态与创作背景。", "Used for buttons, selections, and the creation backdrop."],
  ["自定义主题颜色", "Custom accent color"],
  ["自定义", "Custom"],
  ["字体大小", "Text size"],
  ["统一调整界面、聊天和节点中的文字大小。", "Adjust text across the interface, chat, and nodes."],
  ["较小", "Small"],
  ["默认", "Default"],
  ["较大", "Large"],
  ["界面圆角", "Corner radius"],
  ["直角", "Square"],
  ["圆润", "Rounded"],
  ["每一个灵感，都值得被看见", "Every idea deserves to be seen"],
  ["这是当前颜色、字体与圆角的实际效果。", "A preview of the current color, type, and radius."],
  ["预览", "Preview"],
  ["恢复界面默认设置", "Restore appearance defaults"],
  ["模型由 LinglongLab 的 Google Cloud 部署统一管理", "Models are managed by the LinglongLab Google Cloud deployment"],
  ["浏览器不保存 API Key，也不能修改模型 ID、区域或服务端点。变更请通过部署配置完成。", "The browser stores no API keys and cannot change model IDs, regions, or endpoints. Update deployment configuration instead."],
  ["已由后端启用", "Enabled by backend"],
  ["提供方", "Provider"],
  ["类型", "Type"],
  ["文本", "Text"],
  ["图片", "Image"],
  ["视频", "Video"],
  ["数据收集已关闭", "Data collection is off"],
  ["外部遥测和匿名数据上报在此部署中永久关闭。", "External telemetry and anonymous reporting are permanently disabled in this deployment."],
  ["身份方式", "Identity mode"],
  ["内部无登录视频入口", "Internal video workspace without login"],
  ["后端", "Backend"],
  ["FastAPI · Google Cloud", "FastAPI · Google Cloud"],
  ["退出项目", "Exit project"],
  ["是否退出当前项目并返回首页？", "Exit this project and return home?"],
  ["画布", "Canvas"],
  ["文档", "Document"],
  ["切换画布", "Switch canvas"],
  ["素材库", "Asset library"],
  ["整理画布", "Arrange canvas"],
  ["显示或隐藏地图", "Show or hide minimap"],
  ["网格吸附", "Snap to grid"],
  ["显示或隐藏连线", "Show or hide connections"],
  ["适应视图", "Fit view"],
  ["缩放菜单", "Zoom menu"],
  ["帮助", "Help"],
  ["切换面板", "Switch panel"],
  ["AI 对话", "AI chat"],
  ["新对话", "New chat"],
  ["新建对话", "Start new chat"],
  ["历史对话", "Chat history"],
  ["停靠到右侧", "Dock right"],
  ["停靠到左侧", "Dock left"],
  ["关闭对话", "Close chat"],
  ["开始新对话", "Start a new chat"],
  ["你好，我是 LinglongLab 助手", "Hi, I’m the LinglongLab assistant"],
  ["从一个想法开始", "Start with an idea"],
  ["聊聊你的故事、画面或镜头，让我们一起把想法落到画布上。", "Describe your story, scene, or shot, and we’ll turn it into a canvas."],
  ["搭建创作画布", "Build a creative canvas"],
  ["把创意串成清晰的节点流程", "Turn an idea into a clear node workflow"],
  ["梳理故事分镜", "Plan a storyboard"],
  ["拆解故事，安排画面与镜头", "Break down the story into scenes and shots"],
  ["生成图片素材", "Generate image assets"],
  ["为角色和场景寻找视觉方向", "Explore a visual direction for characters and scenes"],
  ["点击填入提示，也可以直接输入，或粘贴图片、视频。", "Choose a prompt, type your own, or paste images and video."],
  ["消息", "Message"],
  ["输入消息…", "Type a message…"],
  ["选择技能", "Choose skill"],
  ["查看上下文用量", "View context usage"],
  ["发送消息", "Send message"],
  ["推理等级", "Reasoning level"],
  ["低", "Low"],
  ["中", "Medium"],
  ["高", "High"],
  ["选择模型", "Select model"],
  ["正在加载技能…", "Loading skills…"],
  ["加载技能失败，请重新打开重试", "Could not load skills. Reopen to retry."],
  ["没有匹配的技能", "No matching skills"],
  ["暂无可用技能", "No skills available"],
  ["技能指令", "Skill instructions"],
  ["上传素材", "Upload assets"],
  ["新建文件夹", "New folder"],
  ["下载", "Download"],
  ["刷新", "Refresh"],
  ["搜索", "Search"],
  ["暂无素材", "No assets yet"],
  ["音频", "Audio"],
  ["图片生成", "Image generation"],
  ["视频生成", "Video generation"],
  ["3D 导演", "3D director"],
  ["提示词", "Prompt"],
  ["生成", "Generate"],
  ["停止", "Stop"],
  ["重试", "Retry"],
  ["编辑", "Edit"],
  ["复制", "Copy"],
  ["粘贴", "Paste"],
  ["撤销", "Undo"],
  ["重做", "Redo"],
  ["全选", "Select all"],
  ["组合", "Group"],
  ["取消组合", "Ungroup"],
  ["添加节点", "Add node"],
  ["节点搜索", "Search nodes"],
  ["没有找到节点", "No nodes found"],
  ["加载中…", "Loading…"],
  ["加载失败", "Load failed"],
  ["启动失败", "Startup failed"],
  ["无法加载应用，请重试。", "Could not load the app. Try again."],
  ...uiPhraseEntries,
  ...extendedUiPhraseEntries,
  ...nodeUiPhraseEntries,
]);

const originalText = new WeakMap<Text, string>();
const originalAttributes = new WeakMap<Element, Map<string, string>>();
const translatedAttributes = ["aria-label", "title", "placeholder", "aria-description", "alt"];

function translate(value: string) {
  const leading = value.match(/^\s*/u)?.[0] ?? "";
  const trailing = value.match(/\s*$/u)?.[0] ?? "";
  const source = value.slice(leading.length, value.length - trailing.length);
  const exact = phrases.get(source);
  if (exact !== undefined) return `${leading}${exact}${trailing}`;
  const clearShortcut = source.match(/^清除(.+)快捷键$/u);
  if (clearShortcut) return `${leading}Clear ${phrases.get(clearShortcut[1]!) ?? clearShortcut[1]} shortcut${trailing}`;
  const shortcut = source.match(/^(.+)快捷键$/u);
  if (shortcut) return `${leading}${phrases.get(shortcut[1]!) ?? shortcut[1]} shortcut${trailing}`;
  const shortcutConflict = source.match(/^与「(.+)」重复，请换一个快捷键。$/u);
  if (shortcutConflict) return `${leading}Conflicts with “${phrases.get(shortcutConflict[1]!) ?? shortcutConflict[1]}”. Choose a different shortcut.${trailing}`;
  let result = assetUiEnglish(source);
  for (const [pattern, replacement] of dynamicUiTranslations) result = result.replace(pattern, replacement);
  return `${leading}${result}${trailing}`;
}

function shouldSkip(node: Node) {
  const parent = node instanceof Element ? node : node.parentElement;
  return !!parent?.closest("script, style, [contenteditable='true'], .ProseMirror, .messageMarkdown, .messageText, .questionTitle, .questionText, .answerText, .projectName, .projectPath, .conversationName, .conversationTitle, .subAgentName, .historyName, .fileName, .entryName, .assetName, .documentName, .nodeLabel, .nodeFocusName, [data-no-translate]");
}

function translateNode(node: Node, english: boolean) {
  if (node instanceof Text && !shouldSkip(node)) {
    const previous = originalText.get(node);
    if (!english) {
      const target = restoredLocaleText(node.data, previous, previous === undefined ? undefined : translate(previous));
      if (node.data !== target) node.data = target;
      return;
    }
    if (previous === undefined || node.data !== translate(previous)) originalText.set(node, node.data);
    const target = translate(originalText.get(node) ?? node.data);
    if (node.data !== target) node.data = target;
    return;
  }
  if (!(node instanceof Element)) return;
  const skippedContent = shouldSkip(node);
  // Editable roots contain user-authored text, while their ARIA label and
  // placeholder are application chrome and still need localization.
  if (skippedContent && !node.matches("[contenteditable='true'], .ProseMirror")) return;
  let stored = originalAttributes.get(node);
  if (!stored) {
    stored = new Map();
    originalAttributes.set(node, stored);
  }
  for (const name of translatedAttributes) {
    const value = node.getAttribute(name);
    if (value === null) continue;
    if (!english) {
      const source = stored.get(name);
      const target = restoredLocaleText(value, source, source === undefined ? undefined : translate(source));
      if (value !== target) node.setAttribute(name, target);
      continue;
    }
    const source = stored.get(name);
    if (source === undefined || value !== translate(source)) stored.set(name, value);
    const target = translate(stored.get(name) ?? value);
    if (value !== target) node.setAttribute(name, target);
  }
  if (!skippedContent) for (const child of node.childNodes) translateNode(child, english);
}

export function useLegacyLocaleBridge() {
  let cleanupRefresh: (() => void) | undefined;
  let observer: MutationObserver | undefined;
  let applying = false;
  const apply = () => {
    if (!document.body || applying) return;
    applying = true;
    try {
      document.documentElement.lang = interfaceLanguage.value;
      translateNode(document.body, isEnglish.value);
    } finally {
      applying = false;
    }
  };
  const stopLanguage = watch(interfaceLanguage, apply, { flush: "post" });
  onMounted(() => {
    apply();
    // The Vue workspace runs inside a Next.js iframe. Refresh after actions
    // and route changes instead of relying on a cross-realm DOM observer.
    const timers = new Set<number>();
    const schedule = () => {
      requestAnimationFrame(() => requestAnimationFrame(apply));
      for (const delay of [250, 1500]) {
        const timer = window.setTimeout(() => {
          timers.delete(timer);
          apply();
        }, delay);
        timers.add(timer);
      }
    };
    for (const event of ["click", "change", "hashchange"]) window.addEventListener(event, schedule, true);
    const body = document.body;
    const ownerWindow = body?.ownerDocument.defaultView;
    if (body && ownerWindow) {
      observer = new ownerWindow.MutationObserver(records => {
        if (applying) return;
        applying = true;
        try {
          for (const record of records) {
            if (record.type === "attributes" || record.type === "characterData") translateNode(record.target, isEnglish.value);
            else for (const node of record.addedNodes) translateNode(node, isEnglish.value);
          }
        } finally {
          applying = false;
        }
      });
      try {
        observer.observe(body, {
          subtree: true,
          childList: true,
          characterData: true,
          attributes: true,
          attributeFilter: translatedAttributes,
        });
      } catch {
        observer = undefined;
      }
    }
    cleanupRefresh = () => {
      for (const event of ["click", "change", "hashchange"]) window.removeEventListener(event, schedule, true);
      for (const timer of timers) window.clearTimeout(timer);
    };
  });
  onUnmounted(() => {
    observer?.disconnect();
    cleanupRefresh?.();
    stopLanguage();
  });
}
