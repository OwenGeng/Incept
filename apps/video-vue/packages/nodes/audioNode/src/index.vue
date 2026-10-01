<template>
  <nodeSkeleton
    v-bind="nodeProps"
    v-model:bottomVisible="node.selected"
    :topVisible="node.selected"
    topWidth="max-content"
    :bottomWidth="660"
    :downloadUrl="previewUrl"
    :downloadName="outputFile?.url.split(/[\\/]/).at(-1)"
    style="width: 320px">
    <template #topActions>
      <el-button :icon="IconTransfer" :loading="uploading" :disabled="generating || deleting" text title="替换音频" aria-label="替换音频" @click.stop="fileInput?.click()" />
    </template>
    <div v-loading="generating || uploading" class="audioContent nopan" :aria-busy="generating || uploading">
      <audio
        v-if="previewUrl"
        class="audioPreview nodrag nowheel"
        :src="previewUrl"
        controls
        preload="metadata"
        draggable="false"
        @pointerdown.stop
        @mousedown.stop
        @dblclick.stop
        aria-label="节点音频"
        @loadedmetadata="updateNodeInternals"
        @error="ElMessage.error('无法预览该音频')" />
      <input ref="fileInput" class="fileInput" type="file" accept="audio/*" aria-label="选择音频" :disabled="uploading || generating || deleting" @change="uploadAudio" />
      <el-button
        v-if="!outputs.audio"
        class="uploadButton"
        text
        :loading="uploading"
        :disabled="generating || deleting"
        title="上传音频"
        aria-label="上传音频"
        @dblclick.stop
        @click="fileInput?.click()">
        <icon-upload v-if="!uploading" :size="48" stroke="1.5" />
      </el-button>
    </div>
    <template #bottom>
      <el-card class="promptCard" shadow="never" :bodyStyle="{ padding: '14px 16px 12px' }">
        <el-input
          v-model="data.prompt"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          maxlength="12000"
          showWordLimit
          resize="none"
          placeholder="输入要转换为语音的文本"
          aria-label="语音文本"
          :disabled="generating || deleting" />
        <div class="promptFooter">
          <el-select
            v-model="data.model"
            class="modelSelect"
            filterable
            :loading="modelsLoading"
            :disabled="generating || deleting"
            placeholder="选择 TTS 模型"
            aria-label="TTS 模型"
            noDataText="当前部署没有可用的 TTS 模型"
            placement="top-start"
            @visible-change="(visible) => visible && loadModels().catch((error) => showError(error, '模型读取失败'))">
            <template #prefix><icon-sparkles :size="17" /></template>
            <el-option-group v-for="provider in modelGroups" :key="provider.id" :label="provider.label">
              <el-option v-for="item in provider.models" :key="item.modelId" :label="item.label" :value="JSON.stringify([item.providerId, item.modelId])" />
            </el-option-group>
          </el-select>
          <el-select v-model="data.voice" class="voiceSelect" :disabled="generating || deleting || !selectedModel" aria-label="音色" placeholder="音色">
            <el-option v-for="voice in voiceOptions" :key="voice.voice" :label="voice.title" :value="voice.voice" />
          </el-select>
          <el-select v-model="data.format" class="formatSelect" :disabled="generating || deleting || !selectedModel" aria-label="音频格式">
            <el-option v-for="format in formatOptions" :key="format" :label="format.toUpperCase()" :value="format" />
          </el-select>
          <el-input-number v-model="data.speed" :min="0.25" :max="4" :step="0.05" :precision="2" controlsPosition="right" :disabled="generating || deleting" aria-label="语速" />
          <el-button
            class="sendButton"
            :icon="generating ? IconPlayerStop : IconArrowUp"
            :disabled="deleting || uploading || (!generating && (!data.prompt.trim() || !selectedModel))"
            :title="generating ? '停止生成' : '生成语音'"
            :aria-label="generating ? '停止生成' : '生成语音'"
            @click="generating ? generationController?.abort() : startGeneration().catch((error) => showError(error, '语音生成失败'))" />
        </div>
      </el-card>
    </template>
  </nodeSkeleton>
</template>

<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref, watch } from "vue";
import { IconArrowUp, IconMusic, IconPlayerStop, IconSparkles, IconUpload, IconTransfer } from "@tabler/icons-vue";
import { ElButton, ElCard, ElInput, ElInputNumber, ElLoading, ElMessage, ElOption, ElOptionGroup, ElSelect } from "element-plus";
import {
  defaultNodeModel,
  groupNodeModels,
  nodeSkeleton,
  nodeTools,
  useNode,
  useNodeGeneration,
  z,
  type NodeAudioRequest,
  type NodeHandle,
  type NodeMediaModel,
} from "@linglonglab/video-nodes-scaffold/runtime";

defineOptions({
  inheritAttrs: false,
  icon: IconMusic,
  handles: [{ id: "audio", type: "source", dataType: "AUDIO", label: "音频输出" }] satisfies NodeHandle[],
});
const vLoading = ElLoading.directive;
const { id, node, nodeProps, outputs, nodeEvent, files, ai, updateNodeInternals } = useNode({ label: "音频" });
const data = computed(() => node.data as { prompt: string; model: string; voice: string; speed: number; format: string });
data.value.prompt ??= "";
data.value.model ??= "";
data.value.voice ??= "";
data.value.speed ??= 1;
data.value.format ??= "mp3";

const fileInput = ref<HTMLInputElement>();
const uploading = ref(false);
const deleting = ref(false);
const disposed = ref(false);
const models = ref<NodeMediaModel[]>([]);
const modelsLoading = ref(false);
let modelsRequest: Promise<void> | undefined;
let generationController: AbortController | undefined;
let generation: Promise<void> | undefined;
const generationState = useNodeGeneration(outputs, () => generationController?.abort());
const { generating } = generationState;
const selectedModel = computed(() => models.value.find(item => JSON.stringify([item.providerId, item.modelId]) === data.value.model));
const modelGroups = computed(() => groupNodeModels(models.value));
const voiceOptions = computed(() => selectedModel.value?.voices?.length ? selectedModel.value.voices : [{ title: "Default", voice: "alloy" }]);
const formatOptions = computed(() => selectedModel.value?.providerId === "openai"
  ? ["mp3", "wav", "opus", "aac", "flac", "pcm"]
  : ["mp3", "wav", "ogg"]);

watch(selectedModel, () => {
  if (!voiceOptions.value.some(item => item.voice === data.value.voice)) data.value.voice = voiceOptions.value[0]!.voice;
  if (!formatOptions.value.includes(data.value.format)) data.value.format = "mp3";
}, { flush: "sync" });

const outputFile = computed(() => outputs.value.audio?.dataType === "AUDIO" ? outputs.value.audio.value : undefined);
const previewUrl = files.useFileUrl(outputFile, error => showError(error, "音频读取失败"));

onMounted(() => loadModels().catch(error => showError(error, "模型读取失败")));
onScopeDispose(() => {
  disposed.value = true;
  generationController?.abort();
});

function loadModels() {
  if (modelsRequest) return modelsRequest;
  modelsLoading.value = true;
  modelsRequest = ai.getMediaModels().then(items => {
    if (generating.value || deleting.value) return;
    models.value = items.filter(item => item.type === "audio");
    if (!data.value.model) {
      const choice = defaultNodeModel(models.value);
      data.value.model = choice ? JSON.stringify([choice.providerId, choice.modelId]) : "";
    }
  }).finally(() => {
    modelsLoading.value = false;
    modelsRequest = undefined;
  });
  return modelsRequest;
}

async function startGeneration() {
  const choice = selectedModel.value;
  if (generating.value) throw new Error("语音正在生成，请等待完成");
  if (uploading.value) throw new Error("音频正在上传，请等待完成");
  if (deleting.value) throw new Error("节点正在删除");
  if (!choice) throw new Error("请先选择 TTS 模型");
  if (!data.value.prompt.trim()) throw new Error("请输入要转换为语音的文本");
  const workspace = files.getWorkspaceFiles();
  const controller = new AbortController();
  const input: Omit<NodeAudioRequest, "directory"> = {
    providerId: choice.providerId,
    modelId: choice.modelId,
    prompt: data.value.prompt.trim(),
    outputDirectory: `assets/${id}`,
    voice: data.value.voice,
    speed: data.value.speed,
    format: data.value.format,
  };
  generationController = controller;
  generation = generationState.run(() => workspace.list()
    .then(({ directory }) => ai.generateAudio({ ...input, directory }, controller.signal))
    .then(([result]) => {
      controller.signal.throwIfAborted();
      if (!result) throw new Error("供应商未返回音频");
      outputs.value.audio = { dataType: "AUDIO", value: { url: result.path, mimeType: result.mimeType } };
    }))
    .catch(error => showError(error, "语音生成失败"))
    .finally(() => { generationController = undefined; });
  return { status: "generating" };
}

nodeEvent.on("save", reason => {
  if (reason === "reload" && (generating.value || uploading.value || deleting.value)) throw new Error("音频处理中，请完成后再刷新节点");
});
nodeEvent.on("delete", async () => {
  if (uploading.value) throw new Error("音频上传中，请稍后删除节点");
  deleting.value = true;
  generationController?.abort();
  try {
    await generation;
    await files.removeNodeFiles();
  } finally {
    deleting.value = false;
  }
});

nodeTools.register({
  name: "getConfig",
  description: "读取此音频节点的当前 TTS 模型、音色、语速、格式及可选模型，不含密钥",
  parameters: z.strictObject({}),
  async execute(_args, { signal }) {
    signal?.throwIfAborted();
    await loadModels();
    return getConfig();
  },
});

function getConfig() {
  return {
    config: { providerId: selectedModel.value?.providerId ?? "", modelId: selectedModel.value?.modelId ?? "", voice: data.value.voice, speed: data.value.speed, format: data.value.format },
    models: models.value,
  };
}

nodeTools.register({
  name: "setConfig",
  description: "修改此音频节点的 TTS 模型、音色、语速或格式；先用 getConfig 查询可选能力，不启动生成",
  parameters: z.strictObject({
    providerId: z.string().min(1).optional(),
    modelId: z.string().min(1).optional(),
    voice: z.string().min(1).optional(),
    speed: z.number().min(0.25).max(4).optional(),
    format: z.string().min(1).optional(),
  }).refine(args => (args.providerId === undefined) === (args.modelId === undefined), "providerId 与 modelId 必须同时提供"),
  async execute(args, { signal }) {
    signal?.throwIfAborted();
    if (generating.value || deleting.value) throw new Error("节点正在生成或删除，请稍后修改配置");
    await loadModels();
    const choice = args.modelId === undefined ? selectedModel.value
      : models.value.find(item => item.providerId === args.providerId && item.modelId === args.modelId);
    if (!choice) throw new Error("请选择 getConfig 返回的有效 TTS 模型");
    const voices = choice.voices?.length ? choice.voices : [{ title: "Default", voice: "alloy" }];
    const formats = choice.providerId === "openai" ? ["mp3", "wav", "opus", "aac", "flac", "pcm"] : ["mp3", "wav", "ogg"];
    if (args.voice !== undefined && !voices.some(item => item.voice === args.voice)) throw new Error("当前模型不支持所选音色");
    if (args.format !== undefined && !formats.includes(args.format)) throw new Error("当前模型不支持所选音频格式");
    data.value.model = JSON.stringify([choice.providerId, choice.modelId]);
    if (args.voice !== undefined) data.value.voice = args.voice;
    if (args.speed !== undefined) data.value.speed = args.speed;
    if (args.format !== undefined) data.value.format = args.format;
    return getConfig();
  },
});

nodeTools.register({
  name: "setPrompt",
  description: "修改此音频节点要转换为语音的文本，不启动生成",
  parameters: z.strictObject({ prompt: z.string().max(12000) }),
  execute({ prompt }) {
    if (deleting.value) throw new Error("节点正在删除，请稍后修改");
    data.value.prompt = prompt;
    return { prompt };
  },
});

nodeTools.register({
  name: "generateAudio",
  description: "使用当前文本、TTS 模型、音色、语速和格式启动语音生成",
  parameters: z.strictObject({}),
  execute(_args, { signal }) {
    signal?.throwIfAborted();
    return startGeneration();
  },
});

nodeTools.register({
  name: "setAudio",
  description: "选择工作区内已有的音频文件作为此节点的输出，path 使用工作区相对路径",
  parameters: z.strictObject({ path: z.string().min(1).max(4096), mimeType: z.string().regex(/^audio\/[a-zA-Z0-9.+-]+$/) }),
  async execute({ path, mimeType }, { signal }) {
    signal?.throwIfAborted();
    if (uploading.value || generating.value) throw new Error("音频处理中，请稍后重试");
    uploading.value = true;
    try {
      const content = await files.getWorkspaceFiles().read(path);
      signal?.throwIfAborted();
      if (!content.byteLength || content.byteLength > 100 * 1024 * 1024) throw new Error("音频不能为空且不能超过 100 MB");
      outputs.value.audio = { dataType: "AUDIO", value: { url: path, mimeType } };
      return outputs.value.audio;
    } finally {
      uploading.value = false;
    }
  },
});

async function uploadAudio(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || uploading.value || generating.value || deleting.value || disposed.value) return;
  if (!file.type.startsWith("audio/")) return void ElMessage.error("请选择音频文件");
  if (!file.size || file.size > 100 * 1024 * 1024) return void ElMessage.error("音频不能为空且不能超过 100 MB");
  uploading.value = true;
  try {
    const workspace = files.getWorkspaceFiles();
    const url = await files.uploadFile(file);
    if (disposed.value) {
      await workspace.remove(url);
      return;
    }
    outputs.value.audio = { dataType: "AUDIO", value: { url, mimeType: file.type } };
  } catch (error) {
    showError(error, "音频替换失败");
  } finally {
    uploading.value = false;
  }
}

function showError(error: unknown, fallback: string) {
  if (error instanceof Error && error.name === "AbortError") return;
  const message = (error as { response?: { data?: { message?: string } } })?.response?.data?.message;
  ElMessage.error(message || (error instanceof Error ? error.message : fallback));
}
</script>

<style scoped lang="scss">
.audioContent {
  position: relative;
  min-height: 144px;
  display: flex;
  align-items: center;
  .audioPreview { display: block; width: 100%; border-radius: var(--el-border-radius-base); }
  .fileInput { display: none; }
  .uploadButton {
    width: 100%;
    height: 144px;
    padding: 0;
    color: var(--el-text-color-placeholder);
    &:hover { color: var(--el-color-primary); }
  }
}
.promptCard {
  .promptFooter { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
  .modelSelect { flex: 1; min-width: 180px; }
  .voiceSelect { width: 112px; }
  .formatSelect { width: 92px; }
  :deep(.el-input-number) { width: 110px; }
  .sendButton { flex: 0 0 32px; width: 32px; height: 32px; padding: 0; }
}
</style>
