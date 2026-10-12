<template>
  <div class="agentConversation">
    <chat-list class="messageList" :clearHistory="false">
      <chat-item v-if="!messages.length && !disabled" role="assistant" variant="text">
        <template #content>
          <section class="welcomeMessage" aria-label="开始新对话">
            <div class="welcomeHeader">
              <span class="welcomeIcon" aria-hidden="true"><span class="welcomeLogo" :style="{ maskImage: `url(${logoUrl})` }" /></span>
              <div>
                <p class="welcomeLabel">你好，我是 LinglongLab 助手</p>
                <h3>从一个想法开始</h3>
              </div>
            </div>
            <p class="welcomeDescription">聊聊你的故事、画面或镜头，让我们一起把想法落到画布上。</p>
            <div class="welcomeSuggestions">
              <el-button v-for="item in welcomeSuggestions" :key="item.label" class="welcomeSuggestion" text bg :disabled="locked" :aria-label="`填入提示：${item.label}`" @click="fillPrompt(item.prompt)">
                <component :is="item.icon" :size="19" aria-hidden="true" />
                <span class="suggestionContent"><strong>{{ item.label }}</strong><span>{{ item.description }}</span></span>
                <icon-arrow-up-right class="suggestionArrow" :size="15" aria-hidden="true" />
              </el-button>
            </div>
            <p class="welcomeHint">点击填入提示，也可以上传、拖入或粘贴客户图片和视频。</p>
          </section>
        </template>
      </chat-item>
      <div v-for="item in messages" :key="item.id" class="messageRow" :class="{ userMessage: item.role === 'user', editingMessage: editingId === item.id }">
        <chat-item :role="item.role" :variant="item.role === 'user' ? 'base' : 'text'" :textLoading="!!item.streaming && !compacting && !item.parts?.some(part => part.type === 'tool' || part.content)" animation="moving">
          <template #content>
            <div class="messageContent">
              <div v-if="item.report" class="reportHeader"><icon-users-group :size="14" />{{ item.report.name }} 上报</div>
              <template v-for="part in item.parts" :key="part.id">
                <chat-reasoning v-if="part.type === 'thinking' && part.content" class="messageReasoning" :collapsed="part.collapsed ?? true" expandIconPlacement="left" @update:collapsed="part.collapsed = $event">
                  <template #header>
                    <span class="reasoningHeader">
                      <icon-atom :size="14" />
                      <span data-no-translate>{{ t('思考', 'Thinking') }}</span>
                      <span v-if="part.duration !== undefined" class="thinkingDuration" data-no-translate>{{ part.duration.toFixed(1) }} {{ t('秒', 's') }}</span>
                    </span>
                  </template>
                  <messageMarkdown v-if="!(part.collapsed ?? true)" :content="part.content" :streaming="!!item.streaming" />
                </chat-reasoning>
                <toolMessage v-else-if="part.type === 'tool'" :tool="part.tool" :directory="directory" :sessionFile="part.tool.question?.sessionFile ?? sessionFile" :runId="part.tool.question?.runId ?? currentRunId" @copy="copyMessage" />
                <messageMarkdown v-else-if="part.type === 'text' && part.content" :content="part.content" :streaming="!!item.streaming" />
              </template>
              <attachmentList v-if="item.attachments?.length" :attachments="item.attachments" :directory="directory" />
              <el-input v-if="item.role === 'user' && editingId === item.id" v-model="editingText" type="textarea" :autosize="{ minRows: 2, maxRows: 10 }" :disabled="locked" aria-label="编辑消息" @keydown.esc.prevent="cancelEdit" />
              <div v-else-if="item.role === 'user'" class="messageText">{{ item.content }}</div>
              <div v-if="item.pendingInstruction" class="messageError" role="status" data-no-translate>{{ t('执行已中断；如需继续，请重新发送这条指令', 'Interrupted; resend this instruction to continue.') }}</div>
              <div v-if="item.error" class="messageError" role="alert">{{ nativeSystemText(item.error, interfaceLanguage) }}</div>
            </div>
          </template>
        </chat-item>
        <div v-if="!item.streaming" class="messageActions">
          <template v-if="editingId === item.id">
            <el-button text size="small" :disabled="busy || deletingId !== undefined" @click="cancelEdit"><icon-x :size="14" />取消</el-button>
            <el-button type="primary" size="small" :loading="busy" :disabled="locked || (!editingText.trim() && !item.attachments?.length)" @click="sendMessage(item)"><icon-arrow-up v-if="!busy" :size="14" />重发</el-button>
          </template>
          <template v-else>
            <el-button v-if="item.role === 'assistant' && item.error" text size="small" :disabled="locked || remoteRunning" @click="retryMessage(item)">重试上一条消息</el-button>
            <el-button v-if="item.content" class="messageAction" text circle aria-label="复制消息" title="复制消息" @click="copyMessage(item.content)"><icon-copy :size="14" /></el-button>
            <el-button v-if="item.pendingInstruction" text size="small" :disabled="locked || remoteRunning" @click="fillPrompt(item.content)" data-no-translate>{{ t('填入输入框', 'Copy to message') }}</el-button>
            <template v-if="item.role === 'user' && !item.pendingInstruction">
              <el-button class="messageAction" text circle :disabled="locked || remoteRunning" aria-label="编辑消息" title="编辑消息" @click="editMessage(item)"><icon-pencil :size="14" /></el-button>
            </template>
            <el-button v-if="!item.report && !item.pendingInstruction" class="messageAction" text circle :loading="deletingId === item.id" :disabled="locked || remoteRunning" aria-label="删除消息" title="删除消息" @click="deleteMessage(item)"><icon-trash v-if="deletingId !== item.id" :size="14" /></el-button>
          </template>
        </div>
      </div>
    </chat-list>
    <div v-if="compacting" class="compactionStatus" role="status">
      <el-icon class="is-loading" aria-hidden="true"><icon-loader-2 :size="14" /></el-icon>
      <span data-no-translate>{{ t('正在压缩上下文…', 'Compacting context…') }}</span>
    </div>
    <div v-if="progress && (busy || remoteRunning)" class="compactionStatus" role="status" aria-live="polite" data-no-translate>{{ progressText(progress, interfaceLanguage) }}</div>
    <div class="messageInput" :class="{ draggingAttachments }" @dragover="dragAttachments" @dragleave="leaveAttachments" @drop="dropAttachments">
      <div v-if="draggingAttachments" class="attachmentDropHint" role="status">松开添加图片或视频 · 不会自动发送</div>
      <div
        class="senderResizeHandle"
        role="separator"
        aria-orientation="horizontal"
        aria-label="调整输入框高度"
        aria-valuemin="44"
        :aria-valuemax="senderMaxHeight"
        :aria-valuenow="senderHeight"
        tabindex="0"
        title="拖动调整输入框高度"
        @focus="senderHeight = sender?.chatElement.rollBox.clientHeight ?? 44"
        @pointerdown="startSenderResize"
        @pointermove="moveSenderResize"
        @pointerup="stopSenderResize"
        @pointercancel="stopSenderResize"
        @lostpointercapture="stopSenderResize"
        @keydown.up.prevent="setSenderHeight((sender?.chatElement.rollBox.clientHeight ?? 44) + 16)"
        @keydown.down.prevent="setSenderHeight((sender?.chatElement.rollBox.clientHeight ?? 44) - 16)" />
      <attachmentList v-if="draftAttachments.length" class="draftAttachments" :attachments="draftAttachments" :directory="directory" removable @remove="draftAttachments.splice($event, 1)" />
      <div ref="senderElement" class="senderEditor" @keydown.capture="skillMenuRef?.handleKeydown($event)"></div>
      <div class="senderActions">
        <input ref="attachmentPicker" type="file" accept="image/*,video/*" multiple hidden :disabled="!canAddAttachments" @change="pickAttachments" />
        <el-button class="uploadButton" text circle size="small" :disabled="!canAddAttachments" aria-label="上传素材" title="每条最多 20 个附件；图片上传限额 100 MiB，视频 450 MB（450,000,000 字节）；分析与并发限制由服务端校验" @click="attachmentPicker?.click()"><icon-paperclip :size="16" aria-hidden="true" /></el-button>
        <modelPopover v-model="selectedModel" :showReasoning="false" :active="active" :disabled="disabled" />
        <el-select v-if="thinkingLevels.length" v-model="thinkingLevel" class="thinkingSelect" size="small" :disabled="busy || remoteRunning || disabled" :aria-label="t('思考强度', 'Thinking level')" :title="`${t('思考强度', 'Thinking level')} · ${thinkingLabel(thinkingLevel)}`">
          <template #label><icon-atom :size="16" aria-hidden="true" /></template>
          <el-option v-for="level in thinkingLevels" :key="level" :value="level" :label="thinkingLabel(level)" />
        </el-select>
        <skillMenu ref="skillMenuRef" :directory="directory" :active="active" :disabled="locked || editingId !== undefined || !directory" :query="skillQuery" :editor="senderElement" @select="selectSkill" @dismiss="skillQuery = undefined" />
        <el-popover
          v-model:visible="contextMenuVisible"
          trigger="click"
          placement="top"
          :width="280"
          :offset="10"
          :showArrow="false"
          popperClass="agentContextPopover">
          <template #reference>
            <el-button class="contextButton" text circle aria-label="查看上下文用量" title="查看上下文用量">
              <icon-circle-dashed :size="14" />
            </el-button>
          </template>
          <div class="contextUsage">
            <div class="contextHeader"><span>上下文用量</span><span class="contextHint">估算</span></div>
            <template v-if="contextUsage?.tokens != null">
              <div class="contextTokens">
                <span>{{ contextUsage.tokens.toLocaleString() }} / {{ contextWindow.toLocaleString() }} tok</span>
                <span>{{ contextPercent.toFixed(1) }}%</span>
              </div>
              <el-progress :percentage="Math.min(100, contextPercent)" :showText="false" />
            </template>
            <span v-else class="contextHint">{{ contextUsage ? "等待下一次回复更新用量" : "尚无用量数据" }}</span>
            <div v-if="stats" class="contextStats">
              <div class="contextHeader" data-no-translate>{{ t('对话累计用量', 'Conversation usage') }}</div>
              <div class="contextTokens"><span data-no-translate>{{ t('输入', 'Input') }}</span><span>{{ inputTokens.toLocaleString() }} tok</span></div>
              <div class="contextTokens"><span data-no-translate>{{ t('输出', 'Output') }}</span><span>{{ statsSummary.tokens.output.toLocaleString() }} tok</span></div>
              <div v-if="inputTokens > 0" class="contextTokens"><span data-no-translate>{{ t('缓存命中', 'Cache hit') }}</span><span>{{ (statsSummary.tokens.cacheRead / inputTokens * 100).toFixed(1) }}%</span></div>
              <div class="contextTokens"><span>{{ t('模型费用', 'Model cost') }}</span><span>{{ costLabel(statsSummary.cost, interfaceLanguage) }}</span></div>
              <div v-if="statsSummary.elapsedMs !== undefined" class="contextTokens"><span>{{ t('耗时', 'Elapsed') }}</span><span>{{ (statsSummary.elapsedMs / 1000).toFixed(1) }} s</span></div>
              <template v-if="statsSummary.children.length">
                <div class="contextTokens"><span>{{ t('当前会话用量', 'This session tokens') }}</span><span>{{ statsSummary.ownTokens.total.toLocaleString() }} tok</span></div>
                <div class="contextTokens"><span>{{ t('子代理用量', 'Child agent tokens') }}</span><span>{{ statsSummary.childTokens.total.toLocaleString() }} tok</span></div>
                <div class="contextTokens"><span>{{ t('父子合计', 'Total including children') }}</span><span>{{ statsSummary.tokens.total.toLocaleString() }} tok</span></div>
                <div v-for="(child, index) in statsSummary.children" :key="index" class="contextTokens"><span>{{ child.name || t('子代理', 'Child agent') }}</span><span>{{ child.tokens ? `${child.tokens.total.toLocaleString()} tok` : t('用量待确认', 'Usage pending') }} · {{ costLabel(child.cost, interfaceLanguage) }}</span></div>
              </template>
              <div v-if="statsSummary.modelBudget" class="contextTokens"><span>{{ t('模型调用预算', 'Model call budget') }}</span><span>{{ statsSummary.modelBudget.used }} / {{ statsSummary.modelBudget.limit }}</span></div>
              <div v-if="capabilityBudget" class="contextTokens"><span>{{ t('上下文／输出预算', 'Context / output budget') }}</span><span>{{ capabilityBudget.contextTokens?.toLocaleString() ?? '—' }} / {{ capabilityBudget.outputTokens?.toLocaleString() ?? '—' }} tok</span></div>
              <div v-if="statsSummary.tokensPerSecond !== undefined" class="contextTokens"><span data-no-translate>{{ t('生成速度', 'Generation speed') }}</span><span>{{ statsSummary.tokensPerSecond.toFixed(1) }} tok/s</span></div>
            </div>
          </div>
        </el-popover>
        <el-select v-if="busy || remoteRunning" v-model="streamingBehavior" size="small" class="runningAction" :aria-label="t('追加方式', 'Instruction mode')">
          <el-option value="steer" :label="t('立即纠正', 'Steer now')" />
          <el-option value="followUp" :label="t('完成后继续', 'Queue next')" />
        </el-select>
        <el-button v-if="busy || remoteRunning" text circle :aria-label="t('停止生成', 'Stop generation')" :title="t('停止生成', 'Stop generation')" @click="stopMessage()"><icon-player-stop-filled :size="14" /></el-button>
        <el-button class="sendButton" type="primary" circle :loading="controlling" :disabled="props.disabled || snapshotLoading || deletingId !== undefined || editingId !== undefined || controlling" :aria-label="t('发送消息', 'Send message')" :title="t('发送消息', 'Send message')" @click="sendMessage()">
          <icon-arrow-up :size="16" />
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import axios from "axios";
import {
  IconArrowUp, IconAtom, IconCopy,
  IconCircleDashed, IconPencil, IconPlayerStopFilled, IconX, IconLoader2,
  IconTrash, IconLayoutGrid, IconMovie, IconPhoto, IconArrowUpRight, IconUsersGroup, IconPaperclip,
} from "@tabler/icons-vue";
import { ElMessage } from "element-plus";
import logoUrl from "@linglonglab/video-assets/logo.png";
import modelPopover from "@/components/modelPopover.vue";
import skillMenu from "./skillMenu.vue";
import toolMessage from "./toolMessage.vue";
import attachmentList from "./attachmentList.vue";
import useWorkspaceFiles from "@/lib/workspaceFiles";
import { writeClipboardText } from "@/lib/clipboard";
import anonymousData from "@/lib/anonymousData";
import { modelChoices, saveSettings } from "@/stores/settings";
import { useWorkspaceStore } from "@/stores/workspace";
import { interfaceLanguage, t } from "@/i18n";
import type { AgentAttachment, AgentConversation, AgentMessage } from "./types";
import type { AgentEvent } from "@linglonglab/video-runtime-types/agent/types";
import { usageSummary } from "./usageSummary";
import { canApplyDelegatedSnapshot } from "./delegatedLifecycle";
import { createConversationStream, readAgentEvents } from "./replyStream";
import { selectAttachments } from "./attachmentInput";
import { attachmentWarnings, messagePrompt, recoverDraft, resendMessageId, cancelPayload, type AgentRunScope } from "./conversationInput";
import { nativeSystemText } from "@linglonglab/video-runtime-types/agent/locale";
import { progressText } from './progressLocale';
import type { CanvasContext } from "@linglonglab/video-tool-canvas/runtime";
import chatList from "@tdesign-vue-next/chat/es/chat-list";
import chatItem from "@tdesign-vue-next/chat/es/chat-item";
import chatReasoning from "@tdesign-vue-next/chat/es/chat-reasoning";
import messageMarkdown from "@/components/messageMarkdown.vue";
import xSender from "x-sender";
import { costLabel, eventCursor, runEventURL, supportedThinkingLevels, type ThinkingCapability } from "./runtimeControls";
import "tdesign-vue-next/es/style/index.css";
import "@tdesign-vue-next/chat/es/style/index.css";
import "x-sender/lib/XSender.css";

const props = defineProps<{ active: boolean; initialSession: AgentConversation | null; sessionFile?: string; disabled: boolean }>();
const emit = defineEmits<{ session: [file: string]; sent: [prompt: string]; event: [event: AgentEvent] }>();
const workspaceStore = useWorkspaceStore();
const directory = computed(() => workspaceStore.project?.directory);
const draftAttachments = ref<AgentAttachment[]>([]);
const createCanvasContext = inject<(() => CanvasContext | undefined) | undefined>("canvas", undefined);
const messages = ref<AgentMessage[]>((props.initialSession?.messages ?? []).map(message => ({ ...message })));
const researchQuestion = ref(props.initialSession?.researchQuestion ?? null);
watch(() => props.initialSession?.researchQuestion, question => { researchQuestion.value = question ?? null; });
const stream = createConversationStream(messages);
const remoteRunning = ref(props.initialSession?.running ?? false);
const parentObserved = ref(props.initialSession?.parentObserved ?? false);
const stats = ref(props.initialSession?.stats);
const contextUsage = ref(props.initialSession?.contextUsage);
const busy = ref(false);
const snapshotLoading = ref(false);
const compacting = ref(false);
const progress = ref("");
const deletingId = ref<string>();
const locked = computed(() => props.disabled || busy.value || deletingId.value !== undefined);
const inputLocked = computed(() => props.disabled || snapshotLoading.value || deletingId.value !== undefined);
const controlling = ref(false);
const streamingBehavior = ref<"steer" | "followUp">("steer");
const thinkingLevel = ref(props.initialSession?.thinkingLevel ?? "off");
const capabilityModels = ref<ThinkingCapability[]>([]);
const capabilityBudget = ref<{ modelCalls?: number; children?: number; seconds?: number; contextTokens?: number; outputTokens?: number }>();
const statsSummary = computed(() => usageSummary(stats.value));
const currentRunId = ref(props.initialSession?.runId);
let lastSequence = props.initialSession?.lastSequence ?? 0;
const canvasResults = new Map<string, { result?: unknown; error?: string }>();
const editingId = ref<string>();
const attachmentPicker = ref<HTMLInputElement>();
const draggingAttachments = ref(false);
const canAddAttachments = computed(() => props.active && !!directory.value && !locked.value && editingId.value === undefined && draftAttachments.value.length < 20);
const editingText = ref("");
let sender: xSender | undefined;
let controller: AbortController | undefined;
let activeRun: AgentRunScope | undefined;
const senderElement = ref<HTMLElement>();
const skillMenuRef = ref<InstanceType<typeof skillMenu>>();
const skillQuery = ref<string>();
const senderHeight = ref(44);
const senderMaxHeight = ref(Math.max(44, window.innerHeight / 2));
let senderResize: { pointerId: number; y: number; height: number } | undefined;
const pendingMessage = props.initialSession?.parentFile ? undefined : workspaceStore.pendingAgentMessage;
const selectedModel = ref(pendingMessage?.model ?? (props.initialSession?.providerId && props.initialSession.modelId
  ? JSON.stringify([props.initialSession.providerId, props.initialSession.modelId]) : ""));
const contextMenuVisible = ref(false);
const selectedModelChoice = computed(() => modelChoices.value.find(item => item.value === selectedModel.value));
const thinkingLevels = computed(() => supportedThinkingLevels(capabilityModels.value, selectedModelChoice.value?.providerId, selectedModelChoice.value?.modelId));
watch(thinkingLevels, levels => { if (levels.length && !levels.includes(thinkingLevel.value)) thinkingLevel.value = levels.includes("off") ? "off" : levels[0]!; });
function thinkingLabel(level: string) {
  const names: Record<string, [string, string]> = { off: ["默认设置", "Default setting"], minimal: ["最少思考", "Minimal"], low: ["低强度", "Low"], medium: ["中等强度", "Medium"], high: ["高强度", "High"], xhigh: ["最高强度", "Extra high"] };
  return names[level] ? t(...names[level]) : level;
}
const contextWindow = computed(() => contextUsage.value?.contextWindow ?? selectedModelChoice.value?.contextWindow ?? 262144);
const contextPercent = computed(() => (contextUsage.value?.tokens ?? 0) / contextWindow.value * 100);
const inputTokens = computed(() => statsSummary.value.tokens.input + statsSummary.value.tokens.cacheRead + statsSummary.value.tokens.cacheWrite);
const welcomeSuggestions = computed(() => interfaceLanguage.value === "en" ? [
  { label: "Build a creative canvas", description: "Turn an idea into a clear node workflow", icon: IconLayoutGrid, prompt: "Help me build a creative canvas. First confirm the nodes and workflow I need." },
  { label: "Plan a storyboard", description: "Break down the story into scenes and shots", icon: IconMovie, prompt: "Help me turn my story into a storyboard. First confirm the story, duration, and visual style." },
  { label: "Generate image assets", description: "Explore a visual direction for characters and scenes", icon: IconPhoto, prompt: "Help me generate image assets. First confirm the subject, style, and model to use." },
] : [
  { label: "搭建创作画布", description: "把创意串成清晰的节点流程", icon: IconLayoutGrid, prompt: "帮我搭建一个创作画布，先和我确认需要的节点与流程。" },
  { label: "梳理故事分镜", description: "拆解故事，安排画面与镜头", icon: IconMovie, prompt: "帮我把故事整理成分镜，先和我确认故事内容、时长和画面风格。" },
  { label: "生成图片素材", description: "为角色和场景寻找视觉方向", icon: IconPhoto, prompt: "帮我生成图片素材，先和我确认画面内容、风格和使用的模型。" },
]);
watch([inputLocked, editingId, () => props.active], ([locked, editingId, active]) => {
  if (!active || locked || editingId !== undefined) sender?.disable();
  else sender?.enable();
});
watch(() => props.active, active => {
  if (!active) contextMenuVisible.value = false;
});

function applyEvent(event: AgentEvent) {
  const cursor = eventCursor(lastSequence, event.sequence);
  if (!cursor.accept) return;
  lastSequence = cursor.sequence;
  if (event.type === "done" || event.type === "error") { remoteRunning.value = false; progress.value = ""; }
  if (event.type === "done") window.dispatchEvent(new CustomEvent("linglonglabVideo:assets-updated", { detail: { directory: directory.value } }));
  switch (event.type) {
    case 'researchQuestion': researchQuestion.value = event.question; break;
    case "subAgent":
    case "subAgentEvent": emit("event", event); break;
    case "report":
      if (event.parentFile !== props.sessionFile) { emit("event", event); break; }
      if (!messages.value.some(message => message.id === event.id)) messages.value.push({
        id: event.id, role: "assistant", content: event.content,
        parts: [{ id: event.id, type: "text", content: event.content }], report: { file: event.file, name: event.name },
      });
      break;
    case "compaction": compacting.value = event.active; break;
    case "progress": progress.value = event.content; break;
    case "session":
      remoteRunning.value = true;
      if (event.runId) currentRunId.value = event.runId;
      if (directory.value && event.runId) activeRun = { directory: directory.value, sessionFile: event.file, runId: event.runId };
      emit("session", event.file); break;
    case "stats": stats.value = event.stats; contextUsage.value = event.contextUsage; break;
    default: stream.receive(event);
  }
}

function receiveEvent(event: AgentEvent) {
  if (!eventCursor(lastSequence, event.sequence).accept) return;
  if (event.type === "done" || event.type === "error") {
    remoteRunning.value = false;
    compacting.value = false;
    progress.value = "";
  } else if (["userMessage", "text", "thinking", "tool"].includes(event.type)) remoteRunning.value = true;
  applyEvent(event);
}

function beginDelegatedRun() {
  if (!canApplyDelegatedSnapshot(true, busy.value, !!controller)) return false;
  if (parentObserved.value && remoteRunning.value) return true;
  parentObserved.value = true;
  remoteRunning.value = true;
  lastSequence = 0;
  currentRunId.value = undefined;
  activeRun = undefined;
  return true;
}
function receiveDelegatedEvent(event: AgentEvent) {
  if (!canApplyDelegatedSnapshot(parentObserved.value, busy.value, !!controller)) return false;
  receiveEvent(event);
  return true;
}
function finishDelegatedRun() {
  if (!canApplyDelegatedSnapshot(parentObserved.value, busy.value, !!controller)) return false;
  receiveEvent({ type: "done" });
  snapshotLoading.value = true;
  currentRunId.value = undefined;
  activeRun = undefined;
  return true;
}
function applySnapshot(session: AgentConversation) {
  if (!canApplyDelegatedSnapshot(parentObserved.value, busy.value, !!controller)) return false;
  stream.finish();
  messages.value = session.messages.map(message => ({ ...message }));
  stats.value = session.stats;
  contextUsage.value = session.contextUsage;
  researchQuestion.value = session.researchQuestion ?? null;
  currentRunId.value = session.runId;
  lastSequence = session.lastSequence ?? 0;
  remoteRunning.value = !!session.running;
  if (session.providerId && session.modelId) selectedModel.value = JSON.stringify([session.providerId, session.modelId]);
  if (session.thinkingLevel) thinkingLevel.value = session.thinkingLevel;
  parentObserved.value = false;
  snapshotLoading.value = false;
  if (session.running && directory.value) {
    const scope = { directory: directory.value, sessionFile: session.file, runId: session.runId };
    activeRun = scope;
    const observer = new AbortController();
    controller = observer;
    void observeRun(scope, createCanvasContext?.(), observer.signal).finally(() => { if (controller === observer) controller = undefined; });
  }
  return true;
}
function releaseSnapshotLoading() { snapshotLoading.value = false; }
defineExpose({ receiveEvent, beginDelegatedRun, receiveDelegatedEvent, finishDelegatedRun, applySnapshot, releaseSnapshotLoading });

async function selectSkill(name: string) {
  const instance = sender;
  if (!instance || locked.value || editingId.value !== undefined) return;
  const draft = instance.getText().replace(skillQuery.value !== undefined ? /^\/\S*/ : /^\s*\/skill:\S+(?:\s+|$)/, "");
  skillQuery.value = undefined;
  const text = `/skill:${name} ${draft}`;
  await instance.reset({ clearHistory: false, chatNode: text.split("\n").map(text => [{ type: "Write", text }]) });
  if (sender === instance) instance.focus("last");
}

async function fillPrompt(prompt: string) {
  const instance = sender;
  if (!instance || locked.value) return;
  await instance.reset({ clearHistory: false, chatNode: [[{ type: "Write", text: prompt }]] });
  if (sender === instance) instance.focus("last");
}

async function copyMessage(content: string) {
  try {
    await writeClipboardText(content);
    ElMessage.success("已复制");
  } catch {
    ElMessage.error("复制失败，请重试");
  }
}

function editMessage(item: AgentMessage) {
  if (locked.value || remoteRunning.value || item.role !== "user") return;
  editingId.value = item.id;
  editingText.value = item.content;
}

function cancelEdit() {
  if (busy.value || deletingId.value !== undefined) return;
  editingId.value = undefined;
  editingText.value = "";
}

async function retryMessage(item: AgentMessage) {
  const index = messages.value.findIndex(message => message.id === item.id);
  const source = messages.value.slice(0, index).findLast(message => message.role === "user");
  if (!source) return;
  if (source.entryId) { void sendMessage(source); return; }
  // Requests rejected before acknowledgement have no persisted branch to resend.
  draftAttachments.value = recoverDraft(draftAttachments.value, source.attachments ?? []);
  await fillPrompt(source.content);
  messages.value = messages.value.filter(message => message !== source && message !== item);
  void sendMessage();
}

async function deleteMessage(item: AgentMessage) {
  if (locked.value || remoteRunning.value || item.streaming || item.report) return;
  deletingId.value = item.id;
  try {
    if (item.entryId || item.replyTo) {
      if (!directory.value || !props.sessionFile) throw new Error("请重新打开对话后再删除");
      const { data } = await axios.delete<{ code: number; data: AgentConversation; message?: string }>("/api/agent/message", {
        data: {
          directory: directory.value, sessionFile: props.sessionFile,
          ...(item.replyTo ? { replyTo: item.replyTo } : { entryIds: [item.entryId!] }),
        },
        headers: { "x-linglonglabVideo-workspace": "1" },
      });
      if (data.code !== 200) throw new Error(data.message || "删除消息失败");
      if (!Array.isArray(data.data?.messages)) throw new Error("服务端未返回更新后的对话，请重新载入会话");
      messages.value = data.data.messages.map(message => ({ ...message }));
      researchQuestion.value = data.data.researchQuestion ?? null;
      stats.value = data.data.stats;
      contextUsage.value = data.data.contextUsage;
    } else messages.value = messages.value.filter(message => message.id !== item.id);
    if (editingId.value && !messages.value.some(message => message.id === editingId.value)) {
      editingId.value = undefined;
      editingText.value = "";
    }
  } catch (error) {
    const message = axios.isAxiosError<{ message?: string }>(error) ? error.response?.data?.message : undefined;
    ElMessage.error(message || (error instanceof Error ? error.message : "删除消息失败"));
  } finally {
    deletingId.value = undefined;
  }
}

function setSenderHeight(height: number) {
  if (!sender) return;
  senderMaxHeight.value = Math.max(44, window.innerHeight / 2);
  senderHeight.value = Math.max(44, Math.min(senderMaxHeight.value, Math.round(height)));
  sender.chatElement.rollBox.style.height = `${senderHeight.value}px`;
}

function startSenderResize(event: PointerEvent) {
  if (event.button !== 0 || senderResize || !sender) return;
  event.preventDefault();
  senderResize = { pointerId: event.pointerId, y: event.clientY, height: sender.chatElement.rollBox.getBoundingClientRect().height };
  senderHeight.value = senderResize.height;
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function moveSenderResize(event: PointerEvent) {
  if (senderResize?.pointerId !== event.pointerId) return;
  setSenderHeight(senderResize.height + senderResize.y - event.clientY);
}

function stopSenderResize(event: PointerEvent) {
  if (senderResize?.pointerId === event.pointerId) senderResize = undefined;
}

async function cancelRun(scope: AgentRunScope | undefined) {
  const payload = cancelPayload(scope);
  if (!payload) throw new Error("未取得运行标识，请重新打开对话后停止生成");
  const response = await fetch("/api/agent/cancel", {
    method: "POST", headers: { "Content-Type": "application/json", "x-linglonglabVideo-workspace": "1" },
    body: JSON.stringify(payload), keepalive: true,
  });
  if (!response.ok) throw new Error("服务端停止请求失败，请重新打开对话后重试");
}

async function stopMessage() {
  const scope = activeRun ?? (directory.value && props.sessionFile ? { directory: directory.value, sessionFile: props.sessionFile, runId: currentRunId.value } : undefined);
  if (!scope?.runId && controller && !remoteRunning.value) { controller.abort(); stream.finish(); progress.value = ""; return; }
  try {
    await cancelRun(scope);
    controller?.abort();
    remoteRunning.value = false;
    stream.finish();
    progress.value = "";
    activeRun = undefined;
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : "停止生成失败"); }
}

async function uploadAttachments(attachments: AgentAttachment[], directory: string, signal: AbortSignal) {
  if (!attachments.some(item => item.file)) return;
  const files = useWorkspaceFiles(directory);
  for (const path of ["assets", "assets/chat"]) {
    await files.mkdir(path).catch(error => {
      if (error?.response?.data?.data?.code !== "EEXIST") throw error;
    });
    signal.throwIfAborted();
  }
  for (const attachment of attachments) {
    if (!attachment.file) continue;
    const extension = attachment.name.match(/\.[a-zA-Z0-9]{1,10}$/)?.[0].toLowerCase() ?? "";
    const path = `assets/chat/${crypto.randomUUID()}${extension}`;
    await files.write(path, attachment.file, true, signal);
    attachment.path = path;
    attachment.file = undefined;
    signal.throwIfAborted();
  }
}

async function sendCanvasResult(event: Extract<AgentEvent, { type: "canvasCall" }>, canvasContext: CanvasContext | undefined, signal: AbortSignal, requestDirectory: string) {
  let payload: { result?: unknown; error?: string } = canvasResults.get(event.callId) ?? {};
  if (!canvasResults.has(event.callId)) try {
    if (!canvasContext) throw new Error("当前页面没有激活的画布");
    const result = await canvasContext.call(event, signal);
    payload = { result: JSON.parse(JSON.stringify(result ?? null)) };
  } catch (error) {
    payload = { error: (error instanceof Error && error.message ? error.message : "画布操作失败").slice(0, 8000) };
  }
  canvasResults.set(event.callId, payload);
  const cancelled = signal.aborted;
  if (cancelled) payload = { error: "画布操作已取消" };
  const response = await fetch("/api/agent/canvasResult", {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-linglonglabVideo-workspace": "1" },
    body: JSON.stringify({ directory: requestDirectory, callId: event.callId, ...payload }),
    keepalive: cancelled,
    signal: cancelled ? AbortSignal.timeout(5000) : signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.message || "画布操作结果回传失败");
  }

}


async function sendMessage(source?: AgentMessage, researchResume?: { id: string; prompt: string }) {
  const instance = sender;
  const text = researchResume?.prompt ?? ((source ? editingId.value === source.id ? editingText.value : source.content : instance?.getText())?.trim() ?? "");
  const attachments = reactive((researchResume ? [] : source ? source.attachments ?? [] : draftAttachments.value).map(item => ({ ...item })));
  const prompt = messagePrompt(text, attachments.length);
  if (snapshotLoading.value || (!source && editingId.value !== undefined)) return;
  const resendIndex = source ? messages.value.findIndex(item => item.id === source.id) : -1;
  if (source && (source.role !== "user" || resendIndex < 0)) return;
  const resendFrom = source ? resendMessageId(source) : undefined;
  if (!source && (busy.value || remoteRunning.value)) { await sendInstruction(text); return; }
  if (locked.value || !instance || (!prompt && !attachments.length)) return;
  const model = selectedModelChoice.value;
  const requestDirectory = directory.value;
  if (!requestDirectory) return ElMessage.warning("请先打开项目");
  if (!model) return ElMessage.warning("请先选择模型");
  const warnings = attachmentWarnings(model.providerId, attachments);
  if (warnings.length) ElMessage.warning({ message: warnings.join(' '), duration: 10000 });

  const requestController = new AbortController();
  let requestRun: AgentRunScope | undefined;
  const canvasContext = createCanvasContext?.();
  controller = requestController;
  if (!remoteRunning.value) { currentRunId.value = undefined; activeRun = undefined; }
  busy.value = true;
  compacting.value = false;
  progress.value = "正在准备请求…";
  if (source) source.error = undefined;
  instance.enable();
  const reply = reactive<AgentMessage>({ id: crypto.randomUUID(), role: "assistant", content: "", parts: [], streaming: true });
  const userMessage = reactive<AgentMessage>({ id: crypto.randomUUID(), role: "user", content: prompt, attachments });
  let ownsStream = !remoteRunning.value;
  let forwarded = false;
  if (!source) {
    messages.value.push(userMessage);
    if (ownsStream) messages.value.push(reply);
    if (!researchResume) draftAttachments.value = [];
  }
  let accepted = false;
  if (ownsStream) stream.begin(reply);
  canvasResults.clear();
  lastSequence = 0;
  const finishStats = anonymousData.startAgent();
  try {
    if (!source && !researchResume) await instance.reset();
    // Finish language/model preference saves before the host captures this turn.
    await saveSettings();
    requestController.signal.throwIfAborted();
    await uploadAttachments(attachments, requestDirectory, requestController.signal);
    await canvasContext?.prepare?.();
    requestController.signal.throwIfAborted();
    const response = await fetch("/api/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-linglonglabVideo-workspace": "1" },
      body: JSON.stringify({ prompt, researchQuestionId: researchResume?.id, attachments: attachments.map(({ name, path, mimeType }) => ({ name, path, mimeType })), directory: requestDirectory, providerId: model.providerId, modelId: model.modelId, thinkingLevel: thinkingLevels.value.length ? thinkingLevel.value : undefined, sessionFile: props.sessionFile, resendFrom, canvas: canvasContext ? { id: canvasContext.id, tools: canvasContext.tools } : undefined }),
      signal: requestController.signal,
    });
    for await (const event of readAgentEvents(response, requestController.signal, interfaceLanguage.value)) {
      // 子任务复用发起委派时的画布与取消通道，界面切换不改变工具执行目标。
      let toolEvent: AgentEvent = event;
      while (toolEvent.type === "subAgentEvent") toolEvent = toolEvent.event;

      if (toolEvent.type === "canvasCall") {
        await sendCanvasResult(toolEvent, canvasContext, requestController.signal, requestDirectory);
        continue;
      }
      switch (event.type) {
        case "session":
          if (!researchResume) researchQuestion.value = null;
          progress.value = t("正在执行…", "Running…");
          requestRun = { directory: requestDirectory, sessionFile: event.file, runId: event.runId ?? requestRun?.runId ?? currentRunId.value };
          activeRun = requestRun;
          remoteRunning.value = true;
          currentRunId.value = requestRun.runId;
          applyEvent(event);
          break;
        case "accepted":
          forwarded = true;
          if (ownsStream) {
            stream.finish();
            messages.value = messages.value.filter(message => message !== reply);
          }
          break;
        case "userMessage":
          if (accepted) { applyEvent(event); break; }
          if (!ownsStream) {
            messages.value.push(reply);
            stream.begin(reply);
          }
          userMessage.entryId = event.id;
          if (event.attachments) userMessage.attachments = event.attachments;
          reply.replyTo = event.id;
          if (source && !accepted) {
            messages.value.splice(resendIndex, messages.value.length - resendIndex, userMessage, reply);
            stats.value = undefined;
            contextUsage.value = undefined;
            editingId.value = undefined;
            editingText.value = "";
          }
          accepted = true;
          ownsStream = true;
          applyEvent(event);
          break;
        case "stats":
          if (source && !accepted) break;
          applyEvent(event);
          break;
        default: applyEvent(event);
      }
    }
    if (source && !accepted) throw new Error("服务端未确认重发，请重新打开对话后重试");
    finishStats("success");
    emit("sent", prompt || attachments[0]?.name || t("新对话", "New conversation"));
  } catch (error) {
    if (requestRun && remoteRunning.value && !requestController.signal.aborted) {
      progress.value = t("连接中断，正在恢复…", "Connection lost, reconnecting…");
      await observeRun(requestRun, canvasContext, requestController.signal);
      finishStats("success");
      return;
    }
    if (requestController.signal.aborted) { finishStats("cancelled"); return; }
    finishStats("failed");
    const responseMessage = (error as { response?: { data?: { message?: string } } })?.response?.data?.message;
    const message = requestController.signal.aborted ? "已停止生成" : responseMessage || (error instanceof Error ? error.message : "发送失败，请重试");
    if ((source && !accepted) || !ownsStream) { (source ?? userMessage).error = message; ElMessage.error(message); }
    else reply.error = message;
    if (!source && !accepted) {
      draftAttachments.value = recoverDraft(draftAttachments.value, attachments);
      if (!requestController.signal.aborted && !researchResume) await instance.reset({ clearHistory: false, chatNode: text.split("\n").map(text => [{ type: "Write", text }]) });
    }
    if (ownsStream && props.initialSession?.parentFile && props.sessionFile) {
      emit("event", { type: "subAgentEvent", file: props.sessionFile, event: { type: "error", message } });
    }
  } finally {
    if (ownsStream && !forwarded && !remoteRunning.value) stream.finish();
    compacting.value = false;
    progress.value = "";
    busy.value = false;
    controller = undefined;
    if (!remoteRunning.value) activeRun = undefined;
  }
}

function addAttachments(files: File[]) {
  if (!canAddAttachments.value) return;
  const result = selectAttachments(files, draftAttachments.value.length);
  for (const { file, mimeType } of result.accepted) draftAttachments.value.push({ name: file.name, path: '', mimeType, file });
  if (result.errors.length) ElMessage.warning(result.errors.join('；'));
}

function attachWebsiteAsset(event: Event) {
  const detail = (event as CustomEvent<{ directory: string; attachment: AgentAttachment; accepted: boolean }>).detail;
  if (detail.accepted || detail.directory !== directory.value || !canAddAttachments.value) return;
  if (!draftAttachments.value.some(item => item.path === detail.attachment.path)) draftAttachments.value.push(detail.attachment);
  detail.accepted = true;
}
watch(() => props.active, (active, _previous, onCleanup) => {
  if (!active) return;
  window.addEventListener("linglonglabVideo:attach-website-asset", attachWebsiteAsset);
  onCleanup(() => window.removeEventListener("linglonglabVideo:attach-website-asset", attachWebsiteAsset));
}, { immediate: true });
function pickAttachments(event: Event) {
  const input = event.target as HTMLInputElement;
  addAttachments(Array.from(input.files ?? []));
  input.value = ''; // Selecting the same file again must trigger change.
}
function dragAttachments(event: DragEvent) {
  if (!event.dataTransfer?.types.includes('Files')) return;
  event.preventDefault(); event.stopPropagation();
  event.dataTransfer.dropEffect = canAddAttachments.value ? 'copy' : 'none';
  draggingAttachments.value = canAddAttachments.value;
}
function leaveAttachments(event: DragEvent) {
  if (event.relatedTarget instanceof Node && (event.currentTarget as HTMLElement).contains(event.relatedTarget)) return;
  draggingAttachments.value = false;
}
function dropAttachments(event: DragEvent) {
  draggingAttachments.value = false;
  if (!event.dataTransfer?.types.includes('Files')) return;
  event.preventDefault(); event.stopPropagation();
  addAttachments(Array.from(event.dataTransfer.files));
}
function pasteAttachments(event: ClipboardEvent) {
  const files = Array.from(event.clipboardData?.files ?? []);
  if (!files.length) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  addAttachments(files);
}

watch(senderElement, (element, _previous, onCleanup) => {
  if (!element) return;
  const instance = new xSender(element, {
    autoFocus: props.active,
    placeholder: "输入消息…",
    chatStyle: { minHeight: "44px", maxHeight: "50vh", fontSize: "14px", lineHeight: "24px" },
    keyboardSendFun: event => event.key === "Enter" && !event.shiftKey && !event.isComposing,
    keyboardWrapFun: event => event.key === "Enter" && event.shiftKey && !event.isComposing,
  });
  sender = instance;
  if (!props.active || inputLocked.value || editingId.value !== undefined) instance.disable();
  instance.bus.on("agentConversation", xSender.EventSet.EVENT_COMMON_SEND, () => void sendMessage());
  instance.bus.on("agentConversation", xSender.EventSet.EVENT_COMMON_CHANGE, () => {
    skillQuery.value = /^\/([^\s/]*)$/.exec(instance.getText())?.[1];
  });
  const editor = instance.chatElement.richText;
  editor.setAttribute("role", "textbox");
  editor.setAttribute("aria-label", "消息");
  editor.setAttribute("aria-multiline", "true");
  element.addEventListener("paste", pasteAttachments, true);
  onCleanup(() => {
    controller?.abort();
    sender = undefined;
    senderResize = undefined;
    element.removeEventListener("paste", pasteAttachments, true);
    instance.destroy();
  });
});

async function sendInstruction(prompt: string) {
  const scope = activeRun ?? (directory.value && props.sessionFile ? { directory: directory.value, sessionFile: props.sessionFile, runId: currentRunId.value } : undefined);
  if (!prompt || controlling.value || props.disabled) return;
  if (!scope?.runId) { ElMessage.info(t("正在建立会话，请稍后提交追加指令", "Starting this run; send the instruction again when it is ready.")); return; }
  if (draftAttachments.value.length) { ElMessage.warning(t("追加指令请使用文字，素材可在本次执行结束后发送", "Use text for live instructions; send attachments after this run.")); return; }
  controlling.value = true;
  try {
    const { data } = await axios.post("/api/agent/control", { ...scope, action: streamingBehavior.value, prompt }, { headers: { "x-linglonglabVideo-workspace": "1" } });
    if (data.code !== 200) throw new Error(data.message || t("追加失败", "Instruction failed"));
    await sender?.reset();
    ElMessage.success(streamingBehavior.value === "steer" ? t("纠正指令已提交", "Steering instruction sent") : t("已排队，完成后继续", "Queued for the next turn"));
  } catch (error) { ElMessage.error(axios.isAxiosError(error) ? error.response?.data?.message || error.message : String(error)); }
  finally { controlling.value = false; }
}

async function observeRun(scope: AgentRunScope, canvasContext: CanvasContext | undefined, signal: AbortSignal) {
  let retries = 0;
  while (!signal.aborted && remoteRunning.value) {
    try {
      const response = await fetch(runEventURL(scope, lastSequence), { headers: { "x-linglonglabVideo-workspace": "1" }, signal });
      if (!response.ok && [400, 401, 403, 422].includes(response.status)) {
        const failure = await response.json().catch(() => null);
        applyEvent({ type: "error", message: failure?.message || failure?.detail?.message || t("无法恢复运行，请重新打开对话", "Unable to resume this run. Reopen the conversation.") });
        return;
      }
      // Missing or terminated runs require reloading their final database snapshot.
      if (response.status === 404 || response.status === 409 || response.status === 410) {
        const { data } = await axios.get("/api/agent/get", { params: { directory: scope.directory, sessionFile: scope.sessionFile }, headers: { "x-linglonglabVideo-workspace": "1" }, signal });
        if (data.code !== 200) throw new Error(data.message || "读取对话失败");
        stream.finish();
        messages.value = data.data.messages;
        stats.value = data.data.stats;
        contextUsage.value = data.data.contextUsage;
        remoteRunning.value = !!data.data.running;
        lastSequence = data.data.lastSequence ?? lastSequence;
        if (!remoteRunning.value) { progress.value = ""; return; }
        throw new Error("运行正在恢复");
      }
      for await (const event of readAgentEvents(response, signal, interfaceLanguage.value)) {
        retries = 0;
        if (event.sequence !== undefined && event.sequence <= lastSequence) continue;
        let toolEvent = event;
        while (toolEvent.type === "subAgentEvent") toolEvent = toolEvent.event;
        if (toolEvent.type === "canvasCall") {
          await sendCanvasResult(toolEvent, canvasContext, signal, scope.directory);
          lastSequence = Math.max(lastSequence, event.sequence ?? 0);
        } else applyEvent(event);
      }
    } catch (error) {
      if (signal.aborted) return;
      if (axios.isAxiosError(error) && error.response && error.response.status >= 400 && error.response.status < 500) {
        applyEvent({ type: "error", message: error.response.data?.message || error.message });
        return;
      }
      progress.value = t("连接中断，正在恢复…", "Connection lost, reconnecting…");
      await new Promise<void>(resolve => {
        const finish = () => { clearTimeout(timer); signal.removeEventListener("abort", finish); resolve(); };
        const timer = setTimeout(finish, Math.min(10000, 1000 * 2 ** Math.min(retries++, 4)));
        signal.addEventListener("abort", finish, { once: true });
      });
    }
  }
}

onMounted(async () => {
  void axios.get("/api/agent/capabilities", { params: { directory: directory.value }, headers: { "x-linglonglabVideo-workspace": "1" } }).then(({ data }) => {
    capabilityModels.value = data.data?.models ?? [];
    capabilityBudget.value = data.data?.budgets;
  }).catch(() => { /* Sending remains available when optional capabilities cannot be read. */ });
  if (!remoteRunning.value || !directory.value || !props.sessionFile || controller || parentObserved.value) return;
  const scope = { directory: directory.value, sessionFile: props.sessionFile, runId: currentRunId.value };
  activeRun = scope;
  const observer = new AbortController();
  controller = observer;
  await observeRun(scope, createCanvasContext?.(), observer.signal);
  if (controller === observer) controller = undefined;
});
onBeforeUnmount(() => controller?.abort());

watch(() => !props.initialSession?.parentFile && !!workspaceStore.pendingAgentMessage && props.active && !locked.value && !!senderElement.value && !!createCanvasContext?.(), async ready => {
  const message = workspaceStore.pendingAgentMessage;
  const instance = sender;
  if (!ready || !message || !instance || message.directory !== directory.value) return;
  workspaceStore.pendingAgentMessage = null;
  await fillPrompt(message.prompt);
  if (sender === instance && props.active) void sendMessage();
}, { flush: "post" });
</script>

<style lang="scss">
.agentConversation {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;

  .messageList {
    flex: 1;
    min-height: 0;

    .t-chat__list {
      padding: 12px;
    }

    .welcomeMessage {
      display: flex;
      flex-direction: column;
      gap: 18px;
      padding: 28px 4px 16px;
      color: var(--el-text-color-primary);

      .welcomeHeader {
        display: flex;
        align-items: center;
        gap: 12px;

        .welcomeIcon {
          display: grid;
          place-items: center;
          flex-shrink: 0;
          width: 42px;
          height: 42px;
          border-radius: var(--ui-radius-large);
          background: var(--el-color-primary-light-9);
          color: var(--el-color-primary);

          .welcomeLogo {
            width: 28px;
            height: 28px;
            background: currentColor;
            mask-size: contain;
            mask-position: center;
            mask-repeat: no-repeat;
          }
        }

        .welcomeLabel { margin: 0 0 4px; font-size: 12px; color: var(--el-text-color-secondary); }
        h3 { margin: 0; font-size: 18px; font-weight: 600; line-height: 1.4; }
      }

      .welcomeDescription { margin: 0; font-size: 13px; line-height: 1.7; color: var(--el-text-color-regular); }

      .welcomeSuggestions {
        display: flex;
        flex-direction: column;
        gap: 8px;

        .welcomeSuggestion {
          height: auto;
          margin: 0;
          padding: 12px;
          text-align: left;
          white-space: normal;
          line-height: 1.5;

          > span { display: flex; align-items: center; gap: 12px; width: 100%; min-width: 0; }
          svg { flex-shrink: 0; color: var(--el-text-color-secondary); }
          .suggestionContent {
            display: flex;
            flex: 1;
            flex-direction: column;
            gap: 2px;
            min-width: 0;
            strong { font-size: 13px; font-weight: 500; }
            span { font-size: 12px; color: var(--el-text-color-secondary); }
          }
          .suggestionArrow { color: var(--el-text-color-placeholder); }
        }
      }

      .welcomeHint { margin: 0; font-size: 12px; line-height: 1.6; color: var(--el-text-color-secondary); }
    }

    .messageRow {
      margin-bottom: 12px;

      .messageActions {
        display: flex;
        align-items: center;
        gap: 4px;
        margin-top: 4px;

        .el-button {
          margin: 0;

          .tabler-icon {
            flex-shrink: 0;
          }
        }

        .messageAction {
          width: 24px;
          height: 24px;
          padding: 0;
          color: var(--el-text-color-secondary);
        }
      }

      &.userMessage .messageActions {
        justify-content: flex-end;
      }

      &.editingMessage .t-chat__inner.user .t-chat__content .t-chat__detail {
        width: 100%;
        max-width: 100%;
        padding: 0;
        background: transparent;
      }
    }

    .t-chat__inner {
      margin-bottom: 0;

      .t-chat__content {
        min-width: 0;
        padding-top: 0;

        .t-chat__detail {
          width: 100%;
          max-width: 100%;
          padding: 0;
        }
      }

      &.user .t-chat__content .t-chat__detail {
        width: auto;
        max-width: 80%;
        padding: 6px 10px;
        border-radius: calc(var(--ui-radius) * 1.25);
        background: color-mix(in srgb, var(--el-text-color-secondary) 12%, var(--el-bg-color));
      }
    }

    .messageContent {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
      overflow-wrap: anywhere;
      color: var(--el-text-color-primary);

      .messageReasoning {
        padding-top: 0;

        .t-collapse-panel__wrapper {
          background: transparent;

          .t-collapse-panel__header {
            padding: 2px 0;
            font-size: 13px;
            line-height: 20px;
          }

          .t-collapse-panel__icon {
            width: 16px;
            height: 20px;
            margin-right: 6px;

            .t-fake-arrow {
              transform: rotate(-90deg);
            }

            &.t-collapse-panel__icon--active .t-fake-arrow {
              transform: rotate(0deg);
            }
          }

          .t-collapse-panel__body {
            background: transparent;

            .t-collapse-panel__content {
              padding: 4px 0 4px 22px;
              background: transparent;
              color: var(--el-text-color-secondary);
            }
          }
        }
      }

      .reasoningHeader {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: var(--el-text-color-secondary);

        .thinkingDuration {
          font-variant-numeric: tabular-nums;
        }
      }

      .messageText {
        white-space: pre-wrap;
        font-size: 13px;
        line-height: 1.6;
      }

      .messageError {
        color: var(--el-color-danger);
        font-size: 12px;
      }

      .reportHeader {
        display: flex;
        align-items: center;
        gap: 6px;
        color: var(--el-text-color-secondary);
        font-size: 12px;
      }

      .messageMarkdown {
        display: block;
        min-width: 0;
        max-width: 100%;
        font-size: 13px;
        line-height: 1.6;
      }
    }
  }

  .compactionStatus {
    display: flex;
    flex-shrink: 0;
    align-items: center;
    gap: 6px;
    margin: 0 12px 8px;
    color: var(--el-text-color-secondary);
    font-size: 12px;
  }

  .messageInput {
    --chat-text: var(--el-text-color-primary);
    --chat-text-placeholder: var(--el-text-color-placeholder);
    --chat-rect-padding: 12px;
    position: relative;
    flex-shrink: 0;
    margin: 0 12px 8px;
    border: 1px solid var(--el-border-color-light);
    border-radius: calc(var(--ui-radius) * 2.75);
    background: var(--el-bg-color);
    box-shadow: 0 4px 16px rgb(0 0 0 / 8%);

    &:focus-within {
      border-color: var(--el-color-primary-light-5);
    }

    &.draggingAttachments { outline: 2px dashed var(--el-color-primary); outline-offset: 2px; }
    .attachmentDropHint { padding: 8px 12px; font-size: 12px; color: var(--el-color-primary); pointer-events: none; }

    .senderResizeHandle {
      position: absolute;
      z-index: 12;
      top: -4px;
      right: 12px;
      left: 12px;
      height: 8px;
      border-radius: 4px;
      cursor: ns-resize;
      touch-action: none;
      user-select: none;

      &:focus-visible {
        outline: 2px solid var(--el-color-primary);
        outline-offset: 2px;
      }
    }

    .draftAttachments {
      padding: 12px 12px 0;
    }

    .senderEditor .chat-placeholder-wrap {
      font-size: 14px;
      font-style: normal;
      line-height: 24px;
    }

    .senderActions {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
      padding: 2px 8px 6px;

      > .el-button {
        margin-left: 0;
      }

      .thinkingSelect {
        width: 28px;
        flex-shrink: 0;
        .el-select__wrapper {
          min-height: 28px;
          padding: 4px;
          background-color: transparent;
          box-shadow: none;
          &.is-hovering { background-color: var(--el-fill-color-light); }
          &.is-focused { box-shadow: 0 0 0 1px var(--el-color-primary) inset; }
        }
        .el-select__selected-item { display: flex; align-items: center; justify-content: center; }
        .el-select__suffix { display: none; }
      }
      .runningAction { width: 110px; flex-shrink: 0; }
      .modelPopover {
        flex: 1;
        margin-right: auto;
      }
      .uploadButton { width: 28px; height: 28px; padding: 0; flex-shrink: 0; }

      .contextButton {
        width: 24px;
        height: 24px;
        margin: 0;
        padding: 0;

        &.is-text {
          background-color: transparent;
        }
      }

      .sendButton {
        width: 34px;
        height: 34px;
        border: none;
        transform: translateY(-2px);
      }
    }
  }

}
.agentContextPopover {
  .contextUsage {
    display: flex;
    flex-direction: column;
    gap: 12px;

    .contextStats {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .contextHeader,
    .contextTokens {
      display: flex;
      justify-content: space-between;
      gap: 8px;
    }

    .contextHeader {
      color: var(--el-text-color-primary);
    }

    .contextTokens {
      font-size: 12px;
      font-variant-numeric: tabular-nums;
    }

    .contextHint {
      color: var(--el-text-color-secondary);
      font-size: 12px;
    }
  }
}
</style>
