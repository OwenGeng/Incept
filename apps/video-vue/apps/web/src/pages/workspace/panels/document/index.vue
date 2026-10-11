<template>
  <section class="documentWorkspace" aria-label="文档工作区">
    <aside class="sidebar">
      <div class="sidebarModes"><el-button size="small" :type="searchVisible ? 'default' : 'primary'" @click="searchVisible = false">文件</el-button><el-button size="small" :type="searchVisible ? 'primary' : 'default'" @click="searchVisible = true">全文搜索 / 替换</el-button></div>
      <workspaceSearch v-show="searchVisible" ref="searchPanel" :directory="workspaceStore.project?.directory" :openPaths="openPaths" :blocked="tabs.some(tab => tab.loading)" @openFile="path => openSelection({ filePath: path, label: path.split('/').at(-1)! })" />
      <fileTree v-show="!searchVisible" :directory="workspaceStore.project?.directory" @selectNode="openSelection" />
    </aside>
    <div class="documents">
      <div class="layoutToolbar" role="group" aria-label="文档布局">
        <span>{{ tabs.length }} / 12 个标签</span>
        <el-button size="small" :type="layout === 'single' ? 'primary' : 'default'" @click="setLayout('single')">单窗</el-button>
        <el-button size="small" :type="layout === 'horizontal' ? 'primary' : 'default'" @click="setLayout('horizontal')">左右分屏</el-button>
        <el-button size="small" :type="layout === 'vertical' ? 'primary' : 'default'" @click="setLayout('vertical')">上下分屏</el-button>
      </div>
      <div class="tabBar" role="tablist" aria-label="打开的文档">
        <div v-for="tab in tabs" :key="tab.id" class="tab" :class="{ active: activeId === tab.id }">
          <button role="tab" :aria-selected="activeId === tab.id" :title="tab.id" @click="activate(tab.id)">{{ tab.label }}{{ tab.error ? ' · 保存失败' : tab.dirty ? ' · 未保存' : '' }}</button>
          <button :aria-label="`关闭 ${tab.label}`" @click="closeTab(tab.id)">×</button>
        </div>
      </div>
      <div class="paneControls" role="group" aria-label="选择分屏文档">
        <label v-for="pane in paneCount" :key="pane" :class="{ focused: activePane === pane - 1 }" @focusin="activePane = pane - 1">
          {{ layout === 'vertical' ? (pane === 1 ? '上窗' : '下窗') : (pane === 1 ? '左窗' : '右窗') }}
          <el-select :model-value="paneIds[pane - 1]" placeholder="选择标签" size="small" aria-label="选择此窗文档" @change="id => activate(id, pane - 1)">
            <el-option v-for="tab in tabs" :key="tab.id" :label="tab.label" :value="tab.id" />
          </el-select>
        </label>
      </div>
      <div class="editorGrid" :class="layout">
        <div v-for="tab in tabs" v-show="paneIds.slice(0, paneCount).includes(tab.id)" :key="tab.id" class="editorSlot" :style="{ gridArea: paneIds[0] === tab.id ? 'first' : 'second' }" @focusin="activePane = paneIds[0] === tab.id ? 0 : 1" @pointerdown="activePane = paneIds[0] === tab.id ? 0 : 1">
          <documentEditor :ref="instance => setEditor(tab.id, instance)" :readNode="props.readNode" :saveNode="props.saveNode" @state="state => { tab.dirty = state.dirty; tab.error = state.error; tab.filePath = state.textPath; }" />
        </div>
        <div v-for="pane in paneCount" v-show="!paneIds[pane - 1]" :key="`empty-${pane}`" class="emptyPane" :style="{ gridArea: pane === 1 ? 'first' : 'second' }" @pointerdown="activePane = pane - 1">从文件树打开文档，或选择已有标签。</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { useWorkspaceStore } from '@/stores/workspace';
import documentEditor from './documentEditor.vue';
import fileTree, { type TreeSelection } from './components/fileTree.vue';
import workspaceSearch from './components/workspaceSearch.vue';
import { assignPane, canonicalDocumentPath, documentKey, findBackingTab } from './tabs';
import { flushUntilStable } from './saveQueue';
type TextOutput = { id: string; label: string; text: string };
const props = defineProps<{
  readNode: (directory: string, canvasPath: string, nodeId: string) => Promise<{ label: string; outputs: TextOutput[]; textPath?: string }>;
  saveNode: (directory: string, canvasPath: string, nodeId: string, handleId: string, text: string, expectedText?: string) => Promise<void>;
}>();
type Tab = { id: string; label: string; filePath?: string; loading: boolean; dirty: boolean; error: string };
type Layout = 'single' | 'horizontal' | 'vertical';
const workspaceStore = useWorkspaceStore();
const searchPanel = ref<InstanceType<typeof workspaceSearch>>();
const tabs = ref<Tab[]>([]), paneIds = ref<(string | null)[]>([null, null]), activePane = ref(0), layout = ref<Layout>('single'), searchVisible = ref(false);
const editors = new Map<string, InstanceType<typeof documentEditor>>();
const paneCount = computed(() => layout.value === 'single' ? 1 : 2);
const activeId = computed(() => paneIds.value[activePane.value]);
const openPaths = computed(() => tabs.value.flatMap(tab => tab.filePath ? [tab.filePath] : []));
let opening: Promise<unknown> = Promise.resolve();
function setEditor(id: string, instance: unknown) { if (instance) editors.set(id, instance as InstanceType<typeof documentEditor>); else editors.delete(id); }
function activate(id: string, pane = activePane.value) {
  if (!tabs.value.some(tab => tab.id === id)) return;
  paneIds.value = assignPane(paneIds.value, id, pane);
  activePane.value = pane;
}
function setLayout(next: Layout) {
  if (next === 'single') { paneIds.value[0] = activeId.value || paneIds.value[0] || paneIds.value[1] || null; paneIds.value[1] = null; activePane.value = 0; }
  else if (!paneIds.value[1]) paneIds.value[1] = tabs.value.find(tab => tab.id !== paneIds.value[0])?.id ?? null;
  layout.value = next;
}
async function openSelection(selection: TreeSelection, report = true, signal?: AbortSignal) {
  selection = 'filePath' in selection ? { ...selection, filePath: canonicalDocumentPath(selection.filePath) } : { ...selection, canvasPath: canonicalDocumentPath(selection.canvasPath) };
  const task = async () => {
    await searchPanel.value?.flushSave();
    signal?.throwIfAborted();
    const id = documentKey(selection);
    const existing = tabs.value.find(tab => tab.id === id) ?? ('filePath' in selection ? findBackingTab(tabs.value, selection.filePath) : undefined);
    if (existing) { activate(existing.id); return editors.get(existing.id)!; }
    if (tabs.value.length >= 12) throw new Error('最多打开 12 个标签，请先关闭不需要的文档');
    const targetPane = activePane.value;
    const previous = paneIds.value[targetPane];
    tabs.value.push({ id, label: selection.label, ...('filePath' in selection ? { filePath: selection.filePath } : {}), loading: true, dirty: false, error: '' });
    activate(id);
    try {
      await nextTick();
      const editor = editors.get(id);
      if (!editor) throw new Error('文档编辑器尚未准备好');
      await editor.openNode(selection, false, signal);
      const tab = tabs.value.find(tab => tab.id === id);
      if (tab) { tab.loading = false; tab.filePath = editor.getDocument(false).textPath; }
      const backingTab = findBackingTab(tabs.value, tab?.filePath, id);
      if (backingTab) {
        // The temporary editor has only read disk. Reuse the original instance,
        // including its draft and save state; never reload or flush that draft.
        tabs.value = tabs.value.filter(tab => tab.id !== id);
        paneIds.value = paneIds.value.map(current => current === id ? null : current);
        activate(backingTab.id, targetPane);
        return editors.get(backingTab.id)!;
      }
      return editor;
    } catch (error) {
      tabs.value = tabs.value.filter(tab => tab.id !== id);
      paneIds.value = paneIds.value.map((current, pane) => current === id ? (pane === targetPane ? previous ?? null : null) : current);
      throw error;
    }
  };
  const promise = opening.catch(() => {}).then(task);
  opening = promise;
  try { return await promise; }
  catch (error) { if (!report) throw error; ElMessage.error(error instanceof Error ? error.message : '打开文档失败'); }
}
async function closeTab(id: string) {
  try { await editors.get(id)?.flushSave(); }
  catch { ElMessage.error('保存失败，标签已保留。请下载草稿或重新载入后再关闭。'); return; }
  tabs.value = tabs.value.filter(tab => tab.id !== id);
  paneIds.value = paneIds.value.map(current => current === id ? null : current);
  const available = tabs.value.find(tab => !paneIds.value.includes(tab.id));
  if (!paneIds.value[activePane.value] && available) paneIds.value[activePane.value] = available.id;
}
async function flushSave() {
  await flushUntilStable(async () => {
    await opening.catch(() => {});
    await searchPanel.value?.flushSave();
    await Promise.all([...editors.values()].map(editor => editor.flushSave()));
  }, () => tabs.value.some(tab => tab.dirty || tab.loading) || !!searchPanel.value?.isSaving());
}
function getDocument(includeText = true) { return editors.get(activeId.value || '')?.getDocument(includeText) ?? { selection: null, handleId: null, dirty: false, saveError: null, ...(includeText ? { text: '' } : {}) }; }
async function openDocument(args: Record<string, unknown>, signal: AbortSignal) {
  let selection: TreeSelection;
  if (typeof args.path === 'string' && /\.(md|markdown|txt)$/i.test(args.path)) selection = { filePath: args.path, label: args.path.split(/[\\/]/).at(-1)! };
  else if (typeof args.canvasPath === 'string' && typeof args.nodeId === 'string') selection = { canvasPath: args.canvasPath, nodeId: args.nodeId, label: args.nodeId };
  else throw new Error('请指定 Markdown / TXT path 或 canvasPath 与 nodeId');
  const editor = await openSelection(selection, false, signal);
  if (typeof args.handleId === 'string') {
    const current = editor?.getDocument(false).selection;
    if (!current || documentKey(current) !== documentKey(selection)) throw new Error('此底层文件已在另一标签打开，已保留原草稿；请使用当前标签，不要切换节点输出');
    await editor?.openDocument(args, signal);
  }
}
async function writeDocument(args: Record<string, unknown>, signal: AbortSignal) {
  const editor = editors.get(activeId.value || '');
  if (!editor) throw new Error('请先打开文档');
  await editor.writeDocument(args, signal);
}
function cancelSave() { for (const editor of editors.values()) editor.cancelSave(); }
onBeforeUnmount(cancelSave);
defineExpose({ flushSave, cancelSave, getDocument, openDocument, writeDocument });
</script>

<style scoped>
.documentWorkspace { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 12px; width: 100%; height: 100%; box-sizing: border-box; padding: 64px calc(20px + var(--agentWidth, 0px)) 20px 20px; overflow: hidden; background: var(--el-fill-color-light); }
.sidebar { min-height: 0; display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--el-border-color-light); border-radius: var(--ui-radius-large, 12px); background: var(--el-bg-color-overlay); }
.sidebarModes { padding: 8px; display: flex; border-bottom: 1px solid var(--el-border-color-light); }
.sidebar :deep(.fileTree), .sidebar :deep(.workspaceSearch) { flex: 1; min-height: 0; }
.sidebar :deep(.fileTree) { align-self: stretch; border: 0; border-radius: 0; box-shadow: none; }
.documents { min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 8px; }
.layoutToolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 12px; }
.layoutToolbar span { margin-right: auto; }
.tabBar { display: flex; gap: 4px; overflow-x: auto; flex-shrink: 0; }
.tab { display: flex; border: 1px solid var(--el-border-color-light); border-radius: 6px; background: var(--el-bg-color-overlay); }
.tab.active { border-color: var(--el-color-primary); }
.tab button { border: 0; background: transparent; color: var(--el-text-color-regular); cursor: pointer; white-space: nowrap; padding: 8px; font: inherit; font-size: 12px; }
.paneControls { display: flex; gap: 12px; }
.paneControls label { flex: 1; min-width: 0; display: flex; gap: 8px; align-items: center; font-size: 12px; }
.paneControls .focused { color: var(--el-color-primary); }
.paneControls :deep(.el-select) { flex: 1; min-width: 0; }
.editorGrid { display: grid; flex: 1; min-height: 0; min-width: 0; gap: 12px; grid-template-areas: 'first'; grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); }
.editorGrid.horizontal { grid-template-areas: 'first second'; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.editorGrid.vertical { grid-template-areas: 'first' 'second'; grid-template-rows: repeat(2, minmax(0, 1fr)); }
.editorSlot { min-width: 0; min-height: 0; overflow: hidden; }
.emptyPane { display: grid; place-items: center; padding: 16px; font-size: 13px; color: var(--el-text-color-secondary); border: 1px dashed var(--el-border-color); border-radius: 8px; }
@media (max-width: 900px) { .documentWorkspace { grid-template-columns: 200px minmax(0, 1fr); padding-left: 8px; padding-right: calc(8px + var(--agentWidth, 0px)); } .editorGrid.horizontal { grid-template-areas: 'first' 'second'; grid-template-columns: minmax(0, 1fr); grid-template-rows: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 600px) { .documentWorkspace { grid-template-columns: minmax(0, 1fr); grid-template-rows: 180px minmax(0, 1fr); } }
</style>
