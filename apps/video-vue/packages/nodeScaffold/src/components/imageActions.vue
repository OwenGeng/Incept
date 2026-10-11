<template>
  <el-button text :disabled="!source || disabled || busy" title="图片编辑与宫格切分" aria-label="图片编辑与宫格切分" @click.stop="open">编辑图片</el-button>
  <el-dialog v-model="visible" title="图片编辑 · 保留原图，另存新节点" width="min(960px, 95vw)" append-to-body :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" :before-close="close">
    <div class="imageEditor nodrag nopan nowheel" @pointerdown.stop @keydown.stop>
      <div class="toolbar">
        <el-radio-group v-model="mode" :disabled="busy || loading" @change="resetEdits">
          <el-radio-button value="annotate">画笔 / 文字标记</el-radio-button><el-radio-button value="split">宫格切分</el-radio-button><el-radio-button value="mask">局部重绘</el-radio-button>
        </el-radio-group>
        <template v-if="mode !== 'split'">
          <el-select v-model="tool" aria-label="绘制工具" :disabled="busy" style="width:110px">
            <el-option label="画笔" value="brush" /><el-option label="橡皮擦" value="eraser" />
            <el-option v-if="mode === 'annotate'" label="文字" value="text" /><el-option v-if="mode === 'annotate'" label="矩形" value="rectangle" />
          </el-select>
          <input v-if="mode === 'annotate'" v-model="color" type="color" aria-label="标记颜色" :disabled="busy" />
          <el-input-number v-model="brushSize" :min="1" :max="300" aria-label="画笔大小（像素）" :disabled="busy" />
          <el-input v-if="tool === 'text'" v-model="text" maxlength="300" placeholder="输入文字，然后点击图片" aria-label="标记文字" :disabled="busy" />
          <el-button :disabled="!cursor || busy" @click="undo">撤销</el-button><el-button :disabled="cursor >= edits.length || busy" @click="redo">重做</el-button>
          <el-button :disabled="!edits.length || busy" @click="resetEdits">清空标记</el-button>
        </template>
        <template v-else>
          <span>行</span><el-input-number v-model="rows" :min="1" :max="8" :precision="0" :disabled="busy" aria-label="宫格行数" />
          <span>列</span><el-input-number v-model="columns" :min="1" :max="8" :precision="0" :disabled="busy" aria-label="宫格列数" />
        </template>
      </div>
      <p v-if="mode === 'mask'">涂抹要修改的区域。生成会调用当前图片模型；仅修改涂抹区域（由服务端合成保留其余原图像素，并非模型原生蒙版保证）。</p>
      <p v-if="mode === 'split'">{{ rows }} × {{ columns }} 宫格：每块另存独立图片节点，完整保留边缘像素。</p>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <div class="canvasViewport" :aria-busy="loading || busy">
        <canvas ref="preview" aria-label="图片编辑区域，使用指针绘制" @pointerdown="pointerDown" @pointermove="pointerMove" @pointerup="pointerUp" @pointercancel="pointerCancel" />
        <span v-if="loading">读取图片中…</span>
      </div>
      <template v-if="mode === 'mask'">
        <p>当前模型：{{ model?.label || '没有配置可用的 Vertex 图片模型' }}</p>
        <el-input v-model="prompt" type="textarea" :rows="3" maxlength="3000" show-word-limit placeholder="描述选区内要修改的内容" aria-label="局部重绘提示词" :disabled="busy" />
      </template>
    </div>
    <template #footer>
      <el-button :disabled="busy" @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="busy" :disabled="loading || !ready || (mode === 'mask' && (!model || !prompt.trim() || !cursor))" @click="save">
        {{ mode === 'split' ? '切分为新节点' : mode === 'mask' ? '生成局部重绘（调用模型）' : '另存标记图片' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { nextTick, onScopeDispose, ref, watch } from "vue";
import { useNode as useFlowNode, useVueFlow } from "@vue-flow/core";
import { ElButton, ElDialog, ElInput, ElInputNumber, ElOption, ElSelect, ElRadioGroup, ElRadioButton, ElMessage } from "element-plus";
import { useNodeFiles, uploadNodeFile } from "../workspaceFiles";
import { useNodeAi, defaultNodeModel, type NodeMediaModel } from "../nodeAi";
import type { NodeMediaValue } from "../values";
import { gridTiles, canvasPoint, pushEdit, validateImageDimensions, validateEncodedImage, stagedImageRecovery } from "../imageEditing";

const props = defineProps<{ source?: NodeMediaValue; disabled?: boolean }>();
const emit = defineEmits<{ busy: [value: boolean] }>();
const { node } = useFlowNode();
const { addNodes, findNode, nodeTypes } = useVueFlow();
const files = useNodeFiles(), ai = useNodeAi();
const visible = ref(false), busy = ref(false), loading = ref(false), ready = ref(false), error = ref("");
const mode = ref<"annotate" | "split" | "mask">("annotate");
const tool = ref<"brush" | "eraser" | "text" | "rectangle">("brush"), color = ref("#ff3030"), brushSize = ref(24), text = ref("");
const rows = ref(3), columns = ref(3), prompt = ref(""), model = ref<NodeMediaModel>();
const preview = ref<HTMLCanvasElement>();
type Point = { x: number; y: number };
type Edit = { tool: typeof tool.value; points: Point[]; color: string; size: number; text: string };
const edits = ref<Edit[]>([]), cursor = ref(0);
let sourceImage: ImageBitmap | undefined, layer: HTMLCanvasElement | undefined, active: Edit | undefined;
let sourceSnapshot: NodeMediaValue | undefined, disposed = false;
let sourceContent: ArrayBuffer | undefined;
const controller = new AbortController();
watch([rows, columns], () => { try { render(); } catch (issue) { fail(issue); } });
function releaseImage() {
  sourceImage?.close(); sourceImage = undefined;
  if (layer) layer.width = layer.height = 1;
  layer = undefined;
  if (preview.value) preview.value.width = preview.value.height = 1;
  ready.value = false; edits.value = []; cursor.value = 0; active = undefined;
  sourceContent = undefined;
}
watch(visible, value => { if (!value && !busy.value && !loading.value) releaseImage(); });
onScopeDispose(() => { disposed = true; controller.abort(); releaseImage(); });

async function open() {
  if (!props.source || props.disabled || busy.value || loading.value) return;
  sourceSnapshot = { ...props.source };
  visible.value = true; loading.value = true; emit("busy", true); ready.value = false; error.value = "";
  sourceImage?.close(); sourceImage = undefined; resetEdits();
  try {
    if (!nodeTypes?.value?.["remote-imageNode"]) throw new Error("请先启用图片节点插件");
    if (!["image/png", "image/jpeg", "image/webp"].includes(sourceSnapshot.mimeType)) throw new Error("图片编辑支持 PNG、JPEG 和 WebP 格式");
    const content = await files.getWorkspaceFiles().read(sourceSnapshot.url);
    if (!content.byteLength || content.byteLength > 25 * 1024 * 1024) throw new Error("编辑图片须小于 25 MB");
    validateEncodedImage(content, sourceSnapshot.mimeType);
    const image = await createImageBitmap(new Blob([content], { type: sourceSnapshot.mimeType }));
    try { validateImageDimensions(image.width, image.height); } catch (issue) { image.close(); throw issue; }
    if (disposed || !visible.value) { image.close(); return; }
    sourceImage = image;
    sourceContent = content;
    await nextTick();
    if (!preview.value) throw new Error("图片编辑区域未就绪");
    preview.value.width = image.width; preview.value.height = image.height;
    layer = document.createElement("canvas"); layer.width = image.width; layer.height = image.height;
    ready.value = true; render();
    model.value = undefined;
    try { model.value = defaultNodeModel((await ai.getMediaModels(AbortSignal.timeout(10000))).filter(item => item.type === "image" && item.providerId === "google-vertex-ai")); }
    catch { /* 本地标记与切分不依赖模型服务，读取失败仅禁用付费重绘。 */ }
  } catch (issue) { fail(issue); }
  finally { loading.value = false; emit("busy", false); if (!visible.value) releaseImage(); }
}
function close(done: () => void) { if (!busy.value) done(); }
function resetEdits() { edits.value = []; cursor.value = 0; active = undefined; if (mode.value === "mask" && tool.value !== "eraser") tool.value = "brush"; render(); }
function undo() { cursor.value--; render(); }
function redo() { cursor.value++; render(); }
function draw(context: CanvasRenderingContext2D, edit: Edit) {
  const first = edit.points[0]; if (!first) return;
  context.save(); context.globalCompositeOperation = edit.tool === "eraser" ? "destination-out" : "source-over";
  context.strokeStyle = context.fillStyle = mode.value === "mask" ? "#ffffff" : edit.color;
  context.lineWidth = edit.size; context.lineCap = context.lineJoin = "round";
  if (edit.tool === "text") { context.font = `${edit.size}px sans-serif`; context.fillText(edit.text, first.x, first.y); }
  else if (edit.tool === "rectangle") { const end = edit.points.at(-1)!; context.strokeRect(first.x, first.y, end.x - first.x, end.y - first.y); }
  else if (edit.points.length === 1) { context.beginPath(); context.arc(first.x, first.y, edit.size / 2, 0, Math.PI * 2); context.fill(); }
  else { context.beginPath(); context.moveTo(first.x, first.y); for (const point of edit.points.slice(1)) context.lineTo(point.x, point.y); context.stroke(); }
  context.restore();
}
function render() {
  if (!preview.value || !sourceImage || !layer) return;
  const context = preview.value.getContext("2d")!, overlay = layer.getContext("2d")!;
  overlay.clearRect(0, 0, layer.width, layer.height);
  for (const edit of edits.value.slice(0, cursor.value)) draw(overlay, edit);
  if (active) draw(overlay, active);
  context.clearRect(0, 0, preview.value.width, preview.value.height); context.drawImage(sourceImage, 0, 0);
  context.globalAlpha = mode.value === "mask" ? 0.55 : 1; context.drawImage(layer, 0, 0); context.globalAlpha = 1;
  if (mode.value === "split") {
    context.strokeStyle = "#ff3030"; context.lineWidth = Math.max(1, sourceImage.width / 500);
    for (const tile of gridTiles(sourceImage.width, sourceImage.height, rows.value, columns.value)) context.strokeRect(tile.x, tile.y, tile.width, tile.height);
  }
}
function point(event: PointerEvent) { return canvasPoint(event.clientX, event.clientY, preview.value!.getBoundingClientRect(), preview.value!.width, preview.value!.height); }
function pointerDown(event: PointerEvent) {
  if (!ready.value || busy.value || mode.value === "split" || active || event.button !== 0) return;
  if (edits.value.length >= 128 && cursor.value === edits.value.length) return void ElMessage.warning("已达到 128 次标记上限，请保存后继续编辑");
  if (tool.value === "text" && !text.value.trim()) return void ElMessage.warning("请先输入标记文字");
  preview.value!.setPointerCapture(event.pointerId);
  active = { tool: tool.value, points: [point(event)], color: color.value, size: brushSize.value, text: text.value };
  render();
}
function pointerMove(event: PointerEvent) {
  if (!active) return;
  // 长笔画逐步降采样，保留整个路径而非截断尾部，限定历史内存与重绘量。
  if (active.points.length >= 512) active.points = active.points.filter((_value, index) => index % 2 === 0);
  active.points.push(point(event)); render();
}
function pointerUp(event: PointerEvent) {
  if (!active) return;
  if (preview.value?.hasPointerCapture(event.pointerId)) preview.value.releasePointerCapture(event.pointerId);
  const next = pushEdit(edits.value, cursor.value, active, 128); edits.value = next.history; cursor.value = next.cursor; active = undefined; render();
}
function pointerCancel() { active = undefined; render(); }
function blob(canvas: HTMLCanvasElement) { return new Promise<Blob>((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error("无法导出 PNG")), "image/png")); }
function assertCurrent() {
  controller.signal.throwIfAborted();
  if (findNode(node.id) !== node || !nodeTypes?.value?.["remote-imageNode"]) throw new Error("画布已变化，请重新打开图片编辑");
}
async function save() {
  if (!ready.value || !sourceImage || !sourceSnapshot || busy.value) return;
  busy.value = true; emit("busy", true); error.value = "";
  let workspace: ReturnType<typeof files.getWorkspaceFiles> | undefined;
  const staged: string[] = [];
  let paidRequestStarted = false;
  const results: { id: string; path: string; mimeType: string; label: string; row: number; column: number }[] = [];
  try {
    workspace = files.getWorkspaceFiles();
    assertCurrent(); render();
    const label = String(node.data.label || "图片");
    if (mode.value === "mask") {
      if (!model.value || !prompt.value.trim() || !cursor.value) throw new Error("请涂抹修改区域并填写提示词");
      const id = crypto.randomUUID(); staged.push(id);
      const mask = document.createElement("canvas"); mask.width = sourceImage.width; mask.height = sourceImage.height;
      const context = mask.getContext("2d")!; context.fillStyle = "black"; context.fillRect(0, 0, mask.width, mask.height); context.drawImage(layer!, 0, 0);
      const pixels = context.getImageData(0, 0, mask.width, mask.height).data;
      if (!pixels.some((value, index) => index % 4 === 0 && value >= 128)) throw new Error("蒙版为空，请涂抹需要修改的区域");
      const maskPath = await uploadNodeFile(workspace, id, new File([await blob(mask)], "mask.png", { type: "image/png" }));
      // 保存打开编辑器时的源文件快照，防止外部写入在生成前改变选区对应图片。
      const extension = sourceSnapshot.mimeType === "image/jpeg" ? "jpg" : sourceSnapshot.mimeType.split("/")[1]!;
      const sourcePath = await uploadNodeFile(workspace, id, new File([sourceContent!], `source.${extension}`, { type: sourceSnapshot.mimeType }));
      const { directory } = await workspace.list(); assertCurrent();
      // 提交后网络错误不代表生成失败；不能删除可能已收费生成的素材。
      paidRequestStarted = true;
      const response = await fetch("/api/ai/media/inpaint", { method: "POST", headers: { "Content-Type": "application/json", "x-linglonglabVideo-workspace": "1" },
        signal: controller.signal, body: JSON.stringify({ directory, sourcePath, maskPath, prompt: prompt.value.trim(), providerId: model.value.providerId, modelId: model.value.modelId, outputDirectory: `assets/${id}` }) });
      const result = await response.json();
      if (!response.ok || result.code !== 200) throw new Error(result.message || "局部重绘失败");
      const output = result.data?.[0];
      if (!output?.path?.startsWith(`assets/${id}/`) || output.mimeType !== "image/png") throw new Error("局部重绘未返回有效的新图片");
      results.push({ id, path: output.path, mimeType: output.mimeType, label: `${label} · 局部重绘`, row: 0, column: 0 });
    } else {
      const tiles = mode.value === "split" ? gridTiles(sourceImage.width, sourceImage.height, rows.value, columns.value)
        : [{ x: 0, y: 0, width: sourceImage.width, height: sourceImage.height, row: 0, column: 0 }];
      for (const tile of tiles) {
        assertCurrent(); const id = crypto.randomUUID(); staged.push(id);
        const canvas = document.createElement("canvas"); canvas.width = tile.width; canvas.height = tile.height;
        const context = canvas.getContext("2d")!;
        context.drawImage(mode.value === "split" ? sourceImage : preview.value!, tile.x, tile.y, tile.width, tile.height, 0, 0, tile.width, tile.height);
        const path = await uploadNodeFile(workspace, id, new File([await blob(canvas)], "image.png", { type: "image/png" }));
        canvas.width = canvas.height = 1;
        results.push({ id, path, mimeType: "image/png", label: `${label} · ${mode.value === "split" ? `宫格 ${tile.row + 1}-${tile.column + 1}` : "标记"}`, row: tile.row, column: tile.column });
      }
    }
    assertCurrent();
    addNodes(results.map(result => ({ id: result.id, type: "remote-imageNode", position: { x: node.computedPosition.x + node.dimensions.width + 40 + result.column * 290, y: node.computedPosition.y + result.row * 290 },
      data: { label: result.label, outputs: { image: { dataType: "IMAGE", value: { url: result.path, mimeType: result.mimeType } } } } })));
    staged.length = 0; visible.value = false; ElMessage.success(`已创建 ${results.length} 个独立图片节点，原图未修改`);
  } catch (issue) {
    fail(issue);
    const recovery = stagedImageRecovery(staged, paidRequestStarted);
    if (recovery.warning) error.value += ` ${recovery.warning}`;
  }
  finally {
    for (const directory of stagedImageRecovery(staged, paidRequestStarted).cleanup) await workspace?.remove(directory, true).catch(() => {});
    busy.value = false; emit("busy", false); if (!visible.value) releaseImage();
  }
}
function fail(issue: unknown) { error.value = issue instanceof Error ? issue.message : "图片编辑失败"; }
</script>

<style scoped>
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.canvasViewport { overflow: auto; max-height: 55vh; background: #222; text-align: center; }
canvas { max-width: 100%; max-height: 52vh; object-fit: contain; touch-action: none; cursor: crosshair; }
.error { color: var(--el-color-danger); }
</style>
