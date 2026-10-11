<template>
  <el-dialog v-model="visible" class="websiteAssetsDialog" title="客户网站素材" width="min(1080px, calc(100vw - 24px))" align-center append-to-body destroy-on-close @opened="load">
    <section class="websiteAssets" aria-label="客户网站素材库" :aria-busy="busy">
      <el-form class="websiteForm" @submit.prevent="discover">
        <el-input v-model="websiteUrl" aria-label="客户官网或产品页面URL" placeholder="https://客户官网 / 产品页面 / Best seller页面" :disabled="busy" />
        <el-button native-type="submit" type="primary" :loading="discovering" :disabled="busy || !websiteUrl.trim()">发现素材</el-button>
      </el-form>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon role="alert" />
      <el-alert v-if="notice" :title="notice" type="info" :closable="false" show-icon role="status" />
      <el-alert v-if="validation" :title="validation" type="warning" :closable="false" show-icon role="status" />
      <p class="scopeNotice" data-no-translate>{{ t('勾选需要的素材后导入，或添加到对话。不会自动发送；商业投放前请确认客户授权。', 'Select assets to import or attach to chat. Nothing is sent automatically; confirm client usage rights before advertising.') }}</p>
      <details class="scopeNotice" data-no-translate>
        <summary>{{ t('采集、分析与费用说明', 'Collection, analysis and cost details') }}</summary>
        <p>{{ t('仅采集公开网页中的媒体，不绕过登录或视频保护。热销标签不等于已核验销量排名，素材名称和描述不是画面分析结论。', 'Collects public webpage media only; no login or video protection bypass. Bestseller labels are not verified sales rankings. Names and descriptions are not visual analysis results.') }}</p>
        <p>{{ t('预览、勾选、导入不调用模型。发送附件进行分析才消耗媒体 token；导入或分析不代表选入成片。', 'Previewing, selecting and importing do not call a model. Sending attachments for analysis uses media tokens; importing or analyzing does not add assets to the final video.') }}</p>
        <p>{{ t('图片可能缩放。Gemini 使用视频输入或分析副本；OpenAI / Claude 使用带时间戳的采样帧，不读取音频、不覆盖全部帧。实际分析范围以附件回执为准，原始文件保持不变。', 'Images may be resized. Gemini uses video input or analysis copies; OpenAI / Claude use timestamped sample frames without audio or full-frame coverage. Attachment receipts describe actual coverage; originals remain unchanged.') }}</p>
      </details>
      <el-collapse v-if="profile">
        <el-collapse-item title="Moloco CTV制作规格 · 已确认客户配置" name="specs">
          <p>16:9 · MP4 · 推荐 {{ profile.recommended_resolution.join('×') }} · 接受1280×720 · ≥{{ profile.minimum_fps }} FPS · ≤{{ profile.max_file_bytes / 1_000_000 }}MB · {{ profile.duration_seconds.minimum }}–{{ profile.duration_seconds.maximum }}秒 · 推荐{{ profile.duration_seconds.recommended.join('/') }}秒</p>
          <p v-for="warning in profile.warnings" :key="warning">{{ warning }}</p>
          <p>通用视频指南的End card：JPEG/JPG/PNG/GIF，方向与视频一致，宽高均≥320px；≤500KB，GIF≤1MB。CTV是否使用独立End card需另行确认。</p>
          <a :href="profile.source" target="_blank" rel="noopener noreferrer">Moloco通用视频指南</a>
          <span> · </span><a :href="profile.ctv_reference.url" target="_blank" rel="noopener noreferrer">Moloco Performance CTV</a>
        </el-collapse-item>
      </el-collapse>
      <div class="catalogFilters">
        <el-select v-model="filter" :aria-label="t('素材类型筛选', 'Filter asset type')" class="kindFilter" data-no-translate>
          <el-option v-for="(label, kind) in kinds" :key="kind" :value="kind" :label="label" />
        </el-select>
        <el-select v-model="statusFilter" :aria-label="t('素材状态', 'Asset status')" class="kindFilter" data-no-translate>
          <el-option :label="t('全部状态', 'All statuses')" value="all" />
          <el-option v-for="(label, status) in statuses" :key="status" :label="label" :value="status" />
        </el-select>
        <el-input v-model="search" class="catalogSearch" :placeholder="t('搜索名称或商品链接', 'Search name or product URL')" :aria-label="t('搜索素材', 'Search assets')" clearable data-no-translate />
        <el-button :disabled="busy" @click="load">刷新</el-button>
      </div>
      <div class="catalogToolbar">
        <span class="catalogCount" role="status" data-no-translate>{{ t(`${assets.length}项 · 已选择${selected.length}项`, `${assets.length} assets · ${selected.length} selected`) }}</span>
        <div class="catalogActions">
        <el-button type="primary" :loading="importing" :disabled="busy || !selected.length" @click="importSelected">导入选中素材</el-button>
        <el-button :disabled="busy || !selected.length" data-no-translate @click="attachSelected">{{ t('所选素材添加到对话', 'Attach selection to chat') }}</el-button>
        <el-button :disabled="busy || !selected.length" data-no-translate @click="selected = []">{{ t('清空选择', 'Clear selection') }}</el-button>
        </div>
      </div>
      <p class="scopeNotice" data-no-translate>{{ t('最多选择20项；每批导入12项。', 'Select up to 20 assets; import batches contain up to 12.') }}</p>
      <el-scrollbar max-height="420px">
        <el-empty v-if="!filteredAssets.length && !busy" :description="assets.length ? '没有此类素材' : '填写客户网页发现素材，或让Agent采集后点击刷新。'" />
        <div class="assetGrid">
          <article v-for="item in pageAssets" :key="item.id" class="websiteAsset" :class="{ isSelected: selected.includes(item.id) }">
            <div class="assetVisual">
              <video v-if="item.kind === 'video' && item.status === 'imported' && item.path" :src="assetUrl(item.path)" :aria-label="item.name" controls playsinline preload="metadata" />
              <el-image v-else-if="item.status === 'imported' && item.path" :src="assetUrl(item.path)" :alt="item.name" fit="contain" :preview-src-list="[assetUrl(item.path)]" preview-teleported loading="lazy">
                <template #error><span>预览不可用</span></template>
              </el-image>
              <video v-else-if="item.kind === 'video' && previewUrl(item.source_url) && !previewErrors.includes(item.id)" :src="previewUrl(item.source_url)" :aria-label="item.name" controls playsinline preload="none" crossorigin="anonymous" @error="previewErrors.push(item.id)" />
              <img v-else-if="item.kind !== 'video' && previewUrl(item.source_url) && !previewErrors.includes(item.id)" :src="previewUrl(item.source_url)" :alt="item.name" loading="lazy" referrerpolicy="no-referrer" crossorigin="anonymous" @error="previewErrors.push(item.id)" />
              <div v-else class="pendingVisual"><component :is="item.kind === 'video' ? IconVideo : IconPhoto" :size="28" /><span>预览不可用</span></div>
            </div>
            <div class="assetInfo">
              <div class="assetHeading">
                <el-checkbox data-no-translate :model-value="selected.includes(item.id)" :disabled="busy || (selected.length >= 20 && !selected.includes(item.id))" :aria-label="t('选择 ', 'Select ') + item.name" @change="toggle(item.id, !!$event)" />
                <h3 class="assetName" :title="item.name" data-no-translate>{{ item.name }}</h3>
              </div>
              <p v-if="item.description" class="assetDescription" :title="item.description" data-no-translate>{{ item.description }}</p>
              <p v-else class="assetDescription">官网未提供描述</p>
              <div class="assetTags"><el-tag size="small" data-no-translate>{{ kinds[item.kind] }}</el-tag><el-tag size="small" data-no-translate :type="item.status === 'imported' ? 'success' : item.status === 'failed' ? 'danger' : 'info'">{{ statuses[item.status] }}</el-tag></div>
              <p class="rightsNotice" data-no-translate>{{ t('授权待确认', 'Usage rights require confirmation') }}</p>
              <p v-if="item.bestseller_evidence" class="bestseller" data-no-translate>{{ item.bestseller_evidence }}</p>
              <p v-if="item.size">{{ (item.size / 1_000_000).toFixed(2) }}MB · {{ item.mime_type }}</p>
              <p v-if="item.error" class="assetError" role="alert">{{ item.error }}</p>
              <div class="assetLinks"><a :href="item.page_url" target="_blank" rel="noopener noreferrer">{{ item.product_url ? '产品页面' : '来源网页' }}</a>
              <span> · </span><a :href="item.source_url" target="_blank" rel="noopener noreferrer">原始素材</a>
              </div>
              <div v-if="item.path || item.workspace_path" class="assetActions">
              <el-button v-if="item.path" text size="small" @click="download(item)">下载</el-button>
              <el-button v-if="item.path" text size="small" @click="attach(item)">交给Agent</el-button>
              <el-button v-if="item.kind === 'video' && item.workspace_path" text size="small" :disabled="busy" @click="checkVideo(item)">检查CTV交付规格</el-button>
              </div>
            </div>
          </article>
        </div>
      </el-scrollbar>
      <el-pagination v-model:current-page="page" :page-size="24" :total="filteredAssets.length" layout="prev, pager, next" size="small" />
    </section>
    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import axios from "axios";
import { IconPhoto, IconVideo } from "@tabler/icons-vue";
import { ElMessage } from "element-plus";
import { t } from '@/i18n';
import { filterAssets, importBatches, selectAssetIds, previewUrl } from './websiteSelection';

type WebsiteAsset = { id: string; kind: "image" | "video" | "logo" | "icon"; name: string; description: string; source_url: string; page_url: string; product_url?: string; bestseller_evidence?: string; status: "discovered" | "imported" | "failed"; rights_status: "unverified"; path?: string; workspace_path?: string; mime_type?: string; size?: number; error?: string };
type Profile = { recommended_resolution: number[]; minimum_fps: number; max_file_bytes: number; duration_seconds: { minimum: number; maximum: number; recommended: number[] }; warnings: string[]; source: string; ctv_reference: { url: string } };
const props = defineProps<{ directory: string }>();
const visible = defineModel<boolean>({ default: false });
const emit = defineEmits<{ changed: [] }>();
const assets = ref<WebsiteAsset[]>([]), selected = ref<string[]>([]), websiteUrl = ref("");
const previewErrors = ref<string[]>([]);
const profile = ref<Profile>();
const discovering = ref(false), importing = ref(false), loading = ref(false);
const busy = computed(() => discovering.value || importing.value || loading.value);
const error = ref(""), notice = ref(""), validation = ref("");
const kinds = computed(() => ({ all: t("全部", "All"), image: t("图片", "Images"), video: t("视频", "Videos"), logo: "Logo", icon: t("图标", "Icons") }));
const statuses = computed(() => ({ discovered: t("待导入", "Discovered"), imported: t("已导入", "Imported"), failed: t("导入失败", "Import failed") }));
const filter = ref("all");
const statusFilter = ref('all'), search = ref(''), page = ref(1);
const filteredAssets = computed(() => filterAssets(assets.value, filter.value, statusFilter.value, search.value));
const pageAssets = computed(() => filteredAssets.value.slice((page.value-1)*24, page.value*24));
watch([filter, statusFilter, search], () => { page.value = 1; });
let requestVersion = 0;
onBeforeUnmount(() => { requestVersion++; });
watch(() => props.directory, () => { requestVersion++; discovering.value = false; importing.value = false; loading.value = false; assets.value = []; selected.value = []; previewErrors.value = []; page.value = 1; websiteUrl.value = ""; error.value = ""; notice.value = ""; validation.value = ""; if (visible.value) void load(); });
function assetUrl(path: string) { return `/api/assets/read?directory=${encodeURIComponent(props.directory)}&path=${encodeURIComponent(path)}`; }
function showError(value: unknown) { error.value = axios.isAxiosError(value) ? value.response?.data?.detail?.message ?? value.message : value instanceof Error ? value.message : "素材操作失败"; }
function toggle(id: string, checked: boolean) { selected.value = selectAssetIds(selected.value, id, checked); }
async function load() {
  const version = ++requestVersion, directory = props.directory;
  loading.value = true; error.value = "";
  try {
    const [catalog, specs] = await Promise.all([axios.get<{ data: { assets: WebsiteAsset[] } }>("/api/assets/website", { params: { directory, limit: 200 } }), axios.get<{ data: Profile }>("/api/assets/creative-profile")]);
    if (version !== requestVersion) return;
    assets.value = catalog.data.data.assets; profile.value = specs.data.data;
    selected.value = selected.value.filter(id => assets.value.some(item=>item.id===id));
    page.value = Math.min(page.value, Math.max(1, Math.ceil(filteredAssets.value.length/24)));
  } catch (value) { if (version === requestVersion) showError(value); }
  finally { if (version === requestVersion) loading.value = false; }
}
async function discover() {
  if (busy.value) return;
  try { if (new URL(websiteUrl.value.trim()).protocol !== "https:") throw new Error(); }
  catch { error.value = "请输入完整的HTTPS客户网页地址"; return; }
  const version = ++requestVersion, directory = props.directory;
  discovering.value = true; error.value = ""; notice.value = "";
  try {
    const { data } = await axios.post<{ data: { assets: WebsiteAsset[]; warnings: string[]; pages_inspected: number } }>("/api/assets/website/discover", { directory, url: websiteUrl.value.trim() });
    if (version !== requestVersion) return;
    assets.value = data.data.assets; selected.value = [];
    notice.value = `检查了${data.data.pages_inspected}个页面，发现目录共${assets.value.length}项。${data.data.warnings.join(' ')}`;
    emit("changed");
  } catch (value) { if (version === requestVersion) showError(value); }
  finally { if (version === requestVersion) discovering.value = false; }
}
async function importSelected() {
  if (busy.value || !selected.value.length) return;
  const version = ++requestVersion, directory = props.directory;
  importing.value = true; error.value = ""; notice.value = "";
  try {
    let importedCount = 0, failedCount = 0;
    for (const asset_ids of importBatches(assets.value, selected.value)) {
      const { data } = await axios.post<{ data: { assets: WebsiteAsset[]; imported_count: number; failed_count: number } }>("/api/assets/website/import", { directory, asset_ids });
      if (version !== requestVersion) return;
      const updates = new Map(data.data.assets.map(item => [item.id, item]));
      assets.value = assets.value.map(item => updates.get(item.id) ?? item);
      importedCount += data.data.imported_count; failedCount += data.data.failed_count;
      emit("changed");
    }
    notice.value = `已导入${importedCount}项，失败${failedCount}项。已保存到素材库website文件夹；授权待客户确认。`;
  } catch (value) { if (version === requestVersion) showError(value); }
  finally { if (version === requestVersion) importing.value = false; }
}
async function attachSelected() {
  if (busy.value || !selected.value.length) return;
  const directory = props.directory;
  await importSelected();
  if (directory !== props.directory || error.value || busy.value) return;
  for (const item of assets.value.filter(item=>selected.value.includes(item.id) && item.status==='imported')) {
    if (!attach(item)) break;
  }
}
function download(item: WebsiteAsset) { if (item.path) window.open(`${assetUrl(item.path)}&download=true`, "_blank", "noopener,noreferrer"); }
async function checkVideo(item: WebsiteAsset) {
  if (busy.value || !item.workspace_path) return;
  const version = ++requestVersion, directory = props.directory;
  loading.value = true; error.value = ""; validation.value = "";
  try {
    const { data } = await axios.post<{ data: { technical_checks_passed: boolean; errors: string[]; warnings: string[] } }>("/api/assets/creative-check", { directory, path: item.workspace_path });
    if (version !== requestVersion) return;
    validation.value = `${item.name}：${data.data.technical_checks_passed ? '已通过客户CTV配置技术检查（不代表广告使用权或平台审核已获批准）' : '未通过CTV交付技术检查（源素材可继续用于剪辑）'}。${[...data.data.errors, ...data.data.warnings].join('；')}`;
  } catch (value) { if (version === requestVersion) showError(value); }
  finally { if (version === requestVersion) loading.value = false; }
}
function attach(item: WebsiteAsset) {
  if (!item.workspace_path) return false;
  const detail = { directory: props.directory, attachment: { name: item.name, path: item.workspace_path, mimeType: item.mime_type ?? "application/octet-stream" }, accepted: false };
  window.dispatchEvent(new CustomEvent("linglonglabVideo:attach-website-asset", { detail }));
  if (detail.accepted) ElMessage.success("已添加到当前Agent输入框；不会自动发送。");
  else ElMessage.warning("请先打开一个Agent对话，并确保输入框可添加附件。");
  return detail.accepted;
}
</script>

<style scoped>
.websiteAssets { display: flex; flex-direction: column; gap: 16px; min-width: 0; font-family: var(--el-font-family, system-ui, sans-serif); font-size: var(--el-font-size-base, 14px); line-height: 1.5; }
.websiteForm, .catalogToolbar, .catalogActions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.websiteForm .el-input { flex: 1; min-width: 200px; }
.catalogFilters { display: grid; grid-template-columns: 132px 156px minmax(0, 1fr) auto; gap: 8px; align-items: center; }
.catalogSearch { min-width: 0; }
.catalogActions .el-button + .el-button { margin-left: 0; }
.catalogToolbar { padding: 12px 0; border-top: 1px solid var(--el-border-color-lighter); border-bottom: 1px solid var(--el-border-color-lighter); }
.scopeNotice, .assetDescription, .catalogCount { color: var(--el-text-color-secondary); font-size: var(--el-font-size-small); margin: 0; }
.scopeNotice summary { cursor: pointer; }
.kindFilter { width: 100%; min-width: 0; }
.catalogCount { flex: 1; }
.assetGrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr)); gap: 12px; }
.websiteAsset { display: flex; flex-direction: column; border: 1px solid var(--el-border-color); border-radius: var(--el-border-radius-base); overflow: hidden; min-width: 0; background: var(--el-bg-color); }
.websiteAsset.isSelected { border-color: var(--el-color-primary); box-shadow: inset 0 0 0 1px var(--el-color-primary); }
.assetVisual { height: 180px; flex: 0 0 180px; min-height: 0; overflow: hidden; border-bottom: 1px solid var(--el-border-color-lighter); background: var(--el-fill-color-light); display: flex; align-items: center; justify-content: center; }
.assetVisual video, .assetVisual img, .assetVisual .el-image { display: block; width: 100%; height: 100%; max-height: 100%; min-height: 0; min-width: 0; object-fit: contain; }
.assetVisual :deep(.el-image__inner) { width: 100%; height: 100%; object-fit: contain; }
.pendingVisual { display: flex; flex-direction: column; align-items: center; gap: 8px; color: var(--el-text-color-secondary); }
.assetInfo { display: flex; flex: 1; flex-direction: column; gap: 8px; padding: 16px; min-width: 0; overflow-wrap: anywhere; }
.assetHeading { display: flex; gap: 8px; align-items: flex-start; min-width: 0; }
.assetHeading :deep(.el-checkbox) { flex: 0 0 auto; height: 20px; margin: 0; }
.assetName { flex: 1; min-width: 0; margin: 0; font-size: 14px; font-weight: 600; line-height: 20px; height: 40px; }
.assetName, .assetDescription { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.assetDescription { line-height: 18px; height: 36px; }
.assetTags { display: flex; flex-wrap: wrap; gap: 8px; }
.rightsNotice { color: var(--el-color-warning-dark-2); font-size: 12px; margin: 0; }
.assetLinks { margin-top: auto; font-size: 12px; }
.assetActions { display: flex; gap: 8px; flex-wrap: wrap; padding-top: 8px; border-top: 1px solid var(--el-border-color-lighter); }
.assetActions .el-button { margin: 0; }
.assetInfo p { margin: 0; }
.assetError { color: var(--el-color-danger); }
a { color: var(--el-color-primary); }
@media (max-width: 640px) {
  .catalogFilters { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .catalogSearch { grid-column: 1 / -1; }
  .catalogCount { flex-basis: 100%; }
  .websiteForm .el-input { flex-basis: 100%; min-width: 0; }
  .catalogActions { width: 100%; }
  .catalogActions .el-button { white-space: normal; height: auto; min-height: 32px; max-width: 100%; }
}
:global(.websiteAssetsDialog) { max-height: calc(100dvh - 24px); overflow-y: auto; font-family: var(--el-font-family, system-ui, sans-serif); }
</style>
