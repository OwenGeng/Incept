<template>
  <section class="workspaceSearch" aria-label="工作区全文搜索">
    <p class="hint">搜索工作区 Markdown / TXT 文档。区分大小写，按字面匹配；不修改画布、图片或配置文件。</p>
    <p v-if="blocked" class="hint" role="status">正在读取文档，请稍后搜索或替换。</p>
    <el-input v-model="query" maxlength="1000" placeholder="查找文字" aria-label="工作区查找文字" :disabled="busy" @keydown.enter="search" />
    <div class="actions"><el-button size="small" :disabled="!query || busy" @click="search">搜索</el-button><el-button v-if="searching" size="small" @click="controller?.abort()">停止搜索</el-button></div>
    <el-input v-model="replacement" maxlength="10000" placeholder="替换为（留空表示删除）" aria-label="替换文字" :disabled="busy" />
    <template v-if="result">
      <p role="status">已检查 {{ result.scanned }} 个文件，{{ result.files.length }} 个文件匹配。</p>
      <el-alert v-if="result.partial" title="这是部分结果：已停止或达到扫描上限（1000 目录/文件、20 MiB、500 匹配）。" type="warning" :closable="false" />
      <div v-for="file in result.files" :key="file.path" class="searchFile">
        <el-checkbox :model-value="selected.includes(file.path)" :disabled="busy || openPaths.includes(file.path)" @change="toggle(file.path)"><span data-no-translate>{{ file.path }}</span>（{{ file.count }} 处）</el-checkbox>
        <span v-if="openPaths.includes(file.path)" class="hint">关闭此文件的标签后才能批量替换。</span>
        <button v-for="(match, index) in file.matches" :key="index" class="match" :disabled="replacing" @click="emit('openFile', file.path)">{{ match.line }}: {{ match.text }}</button>
        <p v-if="selected.includes(file.path)" class="preview">替换预览：{{ preview(file) }}</p>
      </div>
      <el-button type="primary" size="small" :disabled="busy || !selected.length" @click="replaceSelected">确认替换 {{ selected.length }} 个选中文件</el-button>
    </template>
    <ul v-if="errors.length" class="errors" aria-label="处理错误"><li v-for="error in errors" :key="error">{{ error }}</li></ul>
    <p v-if="outcome" role="status">{{ outcome }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { ElMessageBox } from 'element-plus';
import useWorkspaceFiles from '@/lib/workspaceFiles';
import { replaceLiteral, scanDocuments, replaceSearchFiles, type SearchFile, type SearchResult } from '../search';

const props = defineProps<{ directory?: string; openPaths: string[]; blocked?: boolean }>();
const emit = defineEmits<{ openFile: [path: string] }>();
const query = ref(''), replacement = ref(''), selected = ref<string[]>([]), errors = ref<string[]>([]), outcome = ref('');
const result = ref<SearchResult>();
const searching = ref(false), replacing = ref(false);
const busy = computed(() => searching.value || replacing.value || props.blocked);
let controller: AbortController | undefined;
let generation = 0;
let disposed = false;
let pendingReplacement: Promise<void> = Promise.resolve();
watch(query, () => { result.value = undefined; selected.value = []; outcome.value = ''; });
watch(() => props.directory, () => { generation++; controller?.abort(); searching.value = false; result.value = undefined; selected.value = []; });
watch(() => props.openPaths, paths => { selected.value = selected.value.filter(path => !paths.includes(path)); });

function toggle(path: string) { selected.value = selected.value.includes(path) ? selected.value.filter(item => item !== path) : [...selected.value, path]; }
function preview(file: SearchFile) {
  const text = file.matches[0]?.text ?? '';
  return replaceLiteral(text, query.value, replacement.value).slice(0, 240);
}

async function search() {
  if (busy.value || !query.value || !props.directory) return;
  const request = ++generation;
  controller = new AbortController();
  searching.value = true; errors.value = []; selected.value = []; outcome.value = '';
  try {
    const scanned = await scanDocuments(useWorkspaceFiles(props.directory), query.value, controller.signal);
    if (request !== generation) return;
    result.value = scanned; errors.value = scanned.errors;
  } catch (error) { if (request === generation) errors.value = [error instanceof Error ? error.message : '搜索失败']; }
  finally { if (request === generation) searching.value = false; }
}

async function replaceSelected() {
  if (busy.value) return;
  pendingReplacement = performReplacement();
  await pendingReplacement;
}
async function performReplacement() {
  if (busy.value || !result.value || !props.directory) return;
  const files = result.value.files.filter(file => selected.value.includes(file.path));
  if (!files.length || files.some(file => props.openPaths.includes(file.path))) return;
  const directory = props.directory, find = query.value, replacementText = replacement.value;
  replacing.value = true; errors.value = []; outcome.value = '';
  let succeeded = 0;
  try {
    await ElMessageBox.confirm(`将替换 ${files.length} 个文件中的 ${files.reduce((sum, file) => sum + file.count, 0)} 处文字。此操作逐文件保存，不是原子事务；如发生冲突将停止，其余文件保持原样。请先确认替换预览。`, '确认批量替换', { confirmButtonText: '替换选中文件', cancelButtonText: '取消', type: 'warning' });
    const io = useWorkspaceFiles(directory);
    await replaceSearchFiles(files, find, replacementText,
      (file, text) => io.writeTextSnapshot(file.path, text, file.snapshot),
      path => !disposed && !props.blocked && directory === props.directory && !props.openPaths.includes(path),
      () => { succeeded++; });
    outcome.value = `已替换 ${succeeded} 个文件。请重新搜索查看最新内容。`;
  } catch (error) {
    if (error === 'cancel' || error === 'close') return;
    errors.value = [error instanceof Error ? error.message : '替换失败'];
    outcome.value = `已保存 ${succeeded} 个文件，剩余 ${files.length - succeeded} 个未写入。`;
  } finally {
    replacing.value = false;
    if (succeeded || errors.value.length) { result.value = undefined; selected.value = []; }
  }
}
onBeforeUnmount(() => { disposed = true; generation++; controller?.abort(); });
defineExpose({ flushSave: () => pendingReplacement, isSaving: () => replacing.value });
</script>

<style scoped>
.workspaceSearch { overflow: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; font-size: 12px; }
.hint { margin: 0; color: var(--el-text-color-secondary); line-height: 1.6; }
.actions { display: flex; gap: 8px; }
.searchFile { padding: 8px 0; border-bottom: 1px solid var(--el-border-color-light); display: flex; flex-direction: column; }
.searchFile :deep(.el-checkbox__label) { white-space: normal; overflow-wrap: anywhere; }
.match { border: 0; background: transparent; color: var(--el-text-color-regular); text-align: left; padding: 4px; cursor: pointer; overflow-wrap: anywhere; font: inherit; }
.match:hover, .match:focus-visible { background: var(--el-fill-color); }
.preview { color: var(--el-color-primary); overflow-wrap: anywhere; }
.errors { padding-left: 16px; color: var(--el-color-danger); overflow-wrap: anywhere; }
</style>
