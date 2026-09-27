<template>
  <el-container class="home">
    <bg class="pageBackground" />
    <el-header class="pageHeader">
      <el-button round size="large" :icon="IconSettings" aria-label="设置" @click="settingsVisible = true">设置</el-button>
      <div class="headerActions">
        <language-switch />
        <el-button round size="large" tag="a" href="/" target="_top">返回 LinglongLab</el-button>
      </div>
    </el-header>
    <el-main class="pageContent">
      <section ref="heroStage" class="heroStage" aria-label="创建项目">
        <div ref="heroCopy" class="creationPanel">
          <div class="studioLabel">
            <span class="studioLabelDot" />
            {{ studioLabel }}
          </div>
          <div class="brand">
            <el-image class="brandLogo" :src="logoUrl" fit="contain" alt="LinglongLab" />
            <h1>{{ heroTitle }}</h1>
          </div>
          <p class="heroIntroduction">{{ heroIntroduction }}</p>
          <div class="promptArea">
            <span class="arrowHint inspirationHint">
              灵感创作模式
              <svg viewBox="0 0 60 60" fill="none" aria-hidden="true">
                <path d="M4 9C21 0 44 5 40 23C36 39 14 34 22 20C30 7 49 21 47 52M38 43L47 52L54 42" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
            <el-card class="promptCard" shadow="never" :bodyStyle="{ padding: '20px' }" :footerStyle="{ padding: '12px 16px' }">
              <el-input v-model="prompt" data-no-translate type="textarea" :rows="4" resize="none" :disabled="creating || opening" :placeholder="promptPlaceholder" :aria-label="t('创作描述', 'Creative brief')" />
              <template #footer>
                <div class="composerFooter">
                  <span class="cloudWorkspaceHint">云端项目 · 自动保存</span>
                  <el-space class="sendActions" :size="12">
                    <modelPopover v-model="selectedModel" v-model:reasoningEffort="reasoningEffort" class="modelSelect" :disabled="creating || opening" />
                    <el-button class="sendButton" type="primary" circle :icon="IconArrowUp" :loading="creating" :disabled="creating || opening" aria-label="创建项目并发送" @click="createProject()" />
                  </el-space>
                </div>
              </template>
            </el-card>
          </div>
        </div>
        <aside ref="filmPreview" class="filmPreview" aria-hidden="true">
          <div class="filmHeader">
            <span>{{ filmPreviewLabel }}</span>
            <span class="filmStatus"><i />{{ filmStatusLabel }} <em>01—04</em></span>
          </div>
          <div class="filmViewport">
            <span class="filmPerforation filmPerforationTop" />
            <span class="filmPerforation filmPerforationBottom" />
            <div class="filmRail">
              <div class="filmShot filmShotSunset">
                <div class="filmScene"><i class="filmSun" /><i class="filmDune" /></div>
                <span class="filmShotMeta"><b>01</b>{{ t("暮色", "DUSK") }}</span>
              </div>
              <div class="filmShot filmShotCity">
                <div class="filmScene"><i class="filmMoon" /><i class="filmSkyline" /></div>
                <span class="filmShotMeta"><b>02</b>{{ t("城市", "CITY") }}</span>
              </div>
              <div class="filmShot filmShotPortrait">
                <div class="filmScene"><i class="filmSubject" /><i class="filmLight" /></div>
                <span class="filmShotMeta"><b>03</b>{{ t("人物", "PORTRAIT") }}</span>
              </div>
              <div class="filmShot filmShotProduct">
                <div class="filmScene"><i class="filmProduct" /><i class="filmShadow" /></div>
                <span class="filmShotMeta"><b>04</b>{{ t("产品", "PRODUCT") }}</span>
              </div>
            </div>
            <span class="filmFocus"><i /><i /><i /><i /></span>
            <span class="filmPlay"><i /></span>
          </div>
          <div class="filmFooter">
            <span>{{ featuredFramesLabel }}</span>
            <span class="filmProgress"><i /></span>
            <span>16:9 · 24 FPS</span>
          </div>
        </aside>
      </section>
      <section ref="projectListElement" class="projectList" aria-labelledby="projectListTitle">
        <div class="sectionHeader">
          <h2 id="projectListTitle">项目列表</h2>
          <el-space wrap>
            <el-button :icon="iconFolderOpen" :disabled="creating || opening" @click="importInput?.click()">导入项目</el-button>
            <input ref="importInput" type="file" accept=".zip,application/zip" hidden @change="importProject" />
            <el-button :icon="IconFolderPlus" :disabled="creating || opening" @click="createProject(false)">添加项目</el-button>
            <el-button circle :icon="sortDescending ? IconSortDescending : IconSortAscending" :aria-label="sortDescending ? '按时间降序' : '按时间升序'" @click="sortDescending = !sortDescending" />
            <el-radio-group v-model="viewMode" aria-label="项目视图">
              <el-radio-button value="grid" aria-label="网格视图"><icon-layout-grid :size="16" /></el-radio-button>
              <el-radio-button value="list" aria-label="列表视图"><icon-list :size="16" /></el-radio-button>
            </el-radio-group>
          </el-space>
        </div>
        <div class="projectItems" :class="{ listView: viewMode === 'list' }">
          <el-card v-for="(project, index) in sortedProjects" :key="project.directory" class="projectCard" shadow="never" :bodyStyle="{ padding: '0' }">
            <button class="projectEntry" type="button" :disabled="creating || opening" :aria-label="`打开项目 ${project.name}`" @click="openProject(project)">
              <span class="projectVisual" aria-hidden="true">
                <span class="projectFrameIndex">{{ String(index + 1).padStart(2, "0") }}</span>
                <span class="projectFrameLines"><i /><i /><i /></span>
                <icon-folder class="projectIcon" :size="24" />
              </span>
              <span class="projectInfo">
                <span class="projectName" :title="project.name">{{ project.name }}</span>
                <span class="projectPath" :title="project.directory">{{ project.directory }}</span>
                <span class="projectTime">最近打开 {{ formatLastOpened(project.lastOpenedAt) }}</span>
              </span>
            </button>
            <div class="projectActions">
              <el-button text :icon="IconEdit" :disabled="creating || opening" :aria-label="`重命名项目 ${project.name}`" title="重命名" @click="renameProject(project)" />
              <el-button text type="danger" :icon="IconTrash" :disabled="creating || opening" :aria-label="`删除项目 ${project.name}`" title="删除云端项目" @click="removeProject(project)" />
            </div>
          </el-card>
        </div>
      </section>
    </el-main>
    <settings v-model="settingsVisible" />
  </el-container>
</template>

<script setup lang="ts">
import axios from "axios";
import { createTimeline } from "animejs/timeline";
import { storeToRefs } from "pinia";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  IconSettings,
  IconArrowUp, IconLayoutGrid,
  IconList, IconSortDescending,
  IconSortAscending, IconFolder, IconEdit,
  IconTrash, IconFolderPlus, IconFolderOpen as iconFolderOpen,
} from "@tabler/icons-vue";
import modelPopover from "@/components/modelPopover.vue";
import logoUrl from "@linglonglab/video-assets/logo.png";
import { useWorkspaceStore, type Project } from "@/stores/workspace";
import settings from "@/components/settings/index.vue";
import languageSwitch from "@/components/languageSwitch.vue";
import { interfaceLanguage, t } from "@/i18n";
import bg from "./bg.vue";

const settingsVisible = ref(false);
const router = useRouter();
const creating = ref(false);
const opening = ref(false);
const importInput = ref<HTMLInputElement>();
const heroStage = ref<HTMLElement>();
const heroCopy = ref<HTMLElement>();
const filmPreview = ref<HTMLElement>();
const projectListElement = ref<HTMLElement>();
const prompt = ref("");
const workspaceStore = useWorkspaceStore();
const { project, projectList } = storeToRefs(workspaceStore);
const chinesePlaceholderPhrases = [
  "描述你想创作的内容，让灵感从这里开始…",
  "把一个故事灵感，变成一段精彩的短片…",
  "为你的主角设计独特的外形和性格…",
  "创作一段雨夜街头的电影感镜头…",
  "把这段文字拆解成连贯的分镜画面…",
  "为一场奇幻冒险生成场景和角色…",
  "为你的画面配上一段合适的音乐…",
  "写一段温暖的旁白，讲述这个故事…",
  "设计一支富有想象力的产品宣传片…",
  "从一句话开始，搭建你的创作工作流…",
];
const englishPlaceholderPhrases = [
  "Describe what you want to create and start from here…",
  "Turn a story idea into a memorable short film…",
  "Design a distinctive look and personality for your lead…",
  "Create a cinematic shot on a rain-soaked street at night…",
  "Break this text into a coherent visual storyboard…",
  "Generate scenes and characters for a fantasy adventure…",
  "Find the right music for your visuals…",
  "Write a warm voice-over that tells this story…",
  "Design an imaginative product film…",
  "Start with one sentence and build a creative workflow…",
];
const placeholderPhrases = computed(() => interfaceLanguage.value === "en" ? englishPlaceholderPhrases : chinesePlaceholderPhrases);
const promptPlaceholder = ref(placeholderPhrases.value[0]!);
const studioLabel = computed(() => interfaceLanguage.value === "en" ? "Video production studio" : "视频创作工作台");
const heroTitle = computed(() => interfaceLanguage.value === "en" ? "Turn ideas into moving images" : "让灵感成为镜头");
const heroIntroduction = computed(() => interfaceLanguage.value === "en"
  ? "Start with one sentence, then shape story, image and sound in one creative flow."
  : "从一句话开始，让故事、画面和声音在同一个工作流里成形。"
);
const filmPreviewLabel = computed(() => interfaceLanguage.value === "en" ? "LINGLONGLAB FILM" : "LINGLONGLAB 影片");
const filmStatusLabel = computed(() => interfaceLanguage.value === "en" ? "ROLLING" : "播放中");
const featuredFramesLabel = computed(() => interfaceLanguage.value === "en" ? "FEATURED FRAMES" : "精选镜头");
let entranceTimeline: ReturnType<typeof createTimeline> | undefined;
let filmTimeline: ReturnType<typeof createTimeline> | undefined;
let filmStartTimer: ReturnType<typeof setTimeout> | undefined;
let filmEvents: AbortController | undefined;
let filmVisibilityObserver: IntersectionObserver | undefined;

onMounted(() => {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (reducedMotion.matches) return;
  const copy = heroCopy.value;
  const preview = filmPreview.value;
  const projects = projectListElement.value;
  if (!copy || !preview || !projects) return;

  const frames = preview.querySelectorAll<HTMLElement>(".filmShot");
  entranceTimeline = createTimeline({ defaults: { ease: "out(3)" } })
    .add(copy, { opacity: [0, 1], y: [18, 0], duration: 620 }, 0)
    .add(preview, { opacity: [0, 1], x: [24, 0], duration: 680 }, 100)
    .add(projects, { opacity: [0, 1], y: [14, 0], duration: 520 }, 300);

  const [sunset, city, portrait, product] = Array.from(frames);
  const progress = preview.querySelector<HTMLElement>(".filmProgress i");
  if (!sunset || !city || !portrait || !product || !progress) return;

  const shotWidth = sunset.getBoundingClientRect().width;
  const position = (offset: number, scale: number) => `translate3d(${Math.round(shotWidth * offset)}px, 0, 0) scale(${scale})`;
  const center = position(-0.5, 1);
  const right = position(0.58, 0.86);
  const farRight = position(1.66, 0.74);
  const left = position(-1.58, 0.86);
  const farLeft = position(-2.66, 0.74);
  const move = { duration: 860, ease: "inOut(3)" };

  Object.assign(sunset.style, { transform: center, opacity: "1", zIndex: "3" });
  Object.assign(city.style, { transform: right, opacity: "0.38", zIndex: "1" });
  Object.assign(portrait.style, { transform: farRight, opacity: "0", zIndex: "1" });
  Object.assign(product.style, { transform: left, opacity: "0.38", zIndex: "1" });

  filmTimeline = createTimeline({ autoplay: false, loop: true, loopDelay: 720 })
    .add(progress, { transform: ["scaleX(0)", "scaleX(1)"], duration: 10800, ease: "linear" }, 0)
    .add(sunset, { zIndex: 1, duration: 1 }, 1600)
    .add(city, { zIndex: 3, duration: 1 }, 1600)
    .add(sunset, { transform: left, opacity: 0.38, ...move }, 1700)
    .add(city, { transform: center, opacity: 1, ...move }, 1700)
    .add(portrait, { transform: right, opacity: 0.38, ...move }, 1700)
    .add(product, { transform: farLeft, opacity: 0, ...move }, 1700)
    .add(city, { zIndex: 1, duration: 1 }, 3800)
    .add(portrait, { zIndex: 3, duration: 1 }, 3800)
    .add(sunset, { transform: farLeft, opacity: 0, ...move }, 3900)
    .add(city, { transform: left, opacity: 0.38, ...move }, 3900)
    .add(portrait, { transform: center, opacity: 1, ...move }, 3900)
    .add(product, { transform: right, opacity: 0.38, ...move }, 3900)
    .add(sunset, { transform: farRight, opacity: 0, duration: 1 }, 5950)
    .add(portrait, { zIndex: 1, duration: 1 }, 6100)
    .add(product, { zIndex: 3, duration: 1 }, 6100)
    .add(sunset, { transform: right, opacity: 0.38, ...move }, 6200)
    .add(city, { transform: farLeft, opacity: 0, ...move }, 6200)
    .add(portrait, { transform: left, opacity: 0.38, ...move }, 6200)
    .add(product, { transform: center, opacity: 1, ...move }, 6200)
    .add(city, { transform: farRight, opacity: 0, duration: 1 }, 8450)
    .add(product, { zIndex: 1, duration: 1 }, 8600)
    .add(sunset, { zIndex: 3, duration: 1 }, 8600)
    .add(sunset, { transform: center, opacity: 1, ...move }, 8700)
    .add(city, { transform: right, opacity: 0.38, ...move }, 8700)
    .add(portrait, { transform: farLeft, opacity: 0, ...move }, 8700)
    .add(product, { transform: left, opacity: 0.38, ...move }, 8700)
    .add(portrait, { transform: farRight, opacity: 0, duration: 1 }, 10650);

  filmEvents = new AbortController();
  let pageFocused = true;
  let filmStarted = false;
  let filmVisible = true;
  let filmHovered = false;
  const syncFilmPlayback = () => {
    if (!filmTimeline || !filmStarted) return;
    if (reducedMotion.matches || document.hidden || !pageFocused || !filmVisible || filmHovered) filmTimeline.pause();
    else filmTimeline.resume();
  };
  filmVisibilityObserver = new IntersectionObserver(([entry]) => {
    filmVisible = entry?.isIntersecting ?? true;
    syncFilmPlayback();
  }, { threshold: 0.15 });
  filmVisibilityObserver.observe(preview);
  preview.addEventListener("mouseenter", () => { filmHovered = true; syncFilmPlayback(); }, { signal: filmEvents.signal });
  preview.addEventListener("mouseleave", () => { filmHovered = false; syncFilmPlayback(); }, { signal: filmEvents.signal });
  window.addEventListener("blur", () => { pageFocused = false; syncFilmPlayback(); }, { signal: filmEvents.signal });
  window.addEventListener("focus", () => { pageFocused = true; syncFilmPlayback(); }, { signal: filmEvents.signal });
  document.addEventListener("visibilitychange", syncFilmPlayback, { signal: filmEvents.signal });
  reducedMotion.addEventListener("change", () => {
    if (reducedMotion.matches) filmTimeline?.seek(0).pause();
    else syncFilmPlayback();
  }, { signal: filmEvents.signal });
  filmStartTimer = setTimeout(() => {
    filmStarted = true;
    if (!reducedMotion.matches && !document.hidden && pageFocused && filmVisible && !filmHovered) filmTimeline?.play();
  }, 950);
});

onBeforeUnmount(() => {
  if (filmStartTimer) clearTimeout(filmStartTimer);
  filmEvents?.abort();
  filmVisibilityObserver?.disconnect();
  filmTimeline?.revert();
  entranceTimeline?.revert();
});

onMounted(() => {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let phraseIndex = 0;
  watch([() => !!prompt.value, interfaceLanguage], ([hasInput], _previous, onCleanup) => {
    if (hasInput) return;
    let characterCount = 0;
    let deleting = false;
    let timer: ReturnType<typeof setTimeout>;
    promptPlaceholder.value = "";

    function typePlaceholder() {
      const phrases = placeholderPhrases.value;
      const phrase = phrases[phraseIndex]!;
      characterCount += deleting ? -1 : 1;
      promptPlaceholder.value = phrase.slice(0, characterCount);
      let delay = deleting ? 35 : 85;
      if (characterCount === phrase.length) {
        deleting = true;
        delay = 1800;
      } else if (characterCount === 0) {
        deleting = false;
        phraseIndex = (phraseIndex + 1) % phrases.length;
        delay = 300;
      }
      timer = setTimeout(typePlaceholder, delay);
    }

    timer = setTimeout(typePlaceholder, 300);
    onCleanup(() => clearTimeout(timer));
  }, { immediate: true });
});

onMounted(() => {
  void workspaceStore.refreshProjects().catch(error => {
    ElMessage.error(error instanceof Error ? error.message : "读取项目列表失败");
  });
});

const selectedModel = ref("");
const reasoningEffort = ref("");
const sortDescending = ref(true);
const viewMode = ref("grid");
const sortedProjects = computed(() => [...projectList.value].sort((left, right) =>
  sortDescending.value ? right.lastOpenedAt - left.lastOpenedAt : left.lastOpenedAt - right.lastOpenedAt
));

function formatLastOpened(timestamp: number) {
  return new Date(timestamp).toLocaleString(interfaceLanguage.value === "en" ? "en-US" : "zh-CN", { hour12: false });
}

async function openProject(project: Project) {
  if (creating.value || opening.value) return;
  opening.value = true;
  try {
    await workspaceStore.openProject(project.directory);
    await router.push("/workspace");
  } catch (err) {
    ElMessage.error(axios.isAxiosError<{ message?: string }>(err)
      ? err.response?.data.message || "无法打开项目，请重试"
      : err instanceof Error ? err.message : "无法打开项目，请重试");
  } finally { opening.value = false; }
}

async function renameProject(project: Project) {
  const result = await ElMessageBox.prompt("请输入项目名称", "重命名项目", {
    inputValue: project.name, confirmButtonText: "保存", cancelButtonText: "取消",
    inputValidator: value => !!value?.trim() || "项目名称不能为空",
  }).catch(() => null);
  if (!result) return;
  try { await workspaceStore.renameProject(project.directory, result.value); }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : "重命名项目失败"); }
}

async function createProject(fromPrompt = true) {
  if (creating.value || opening.value) return;
  creating.value = true;
  try {
    const idea = prompt.value.trim();
    const locale = interfaceLanguage.value === "en" ? "en-US" : "zh-CN";
    const name = fromPrompt && idea
      ? idea.slice(0, 36)
      : `${t("未命名项目", "Untitled project")} ${new Date().toLocaleDateString(locale)}`;
    const created = await workspaceStore.createProject(name, idea);
    await workspaceStore.openProject(created.directory);
    if (fromPrompt && prompt.value.trim()) {
      workspaceStore.pendingAgentMessage = { directory: workspaceStore.project!.directory, prompt: prompt.value, model: selectedModel.value, reasoningEffort: reasoningEffort.value };
    }
    await router.push("/workspace");
  } catch (err) {
    ElMessage.error(axios.isAxiosError<{ message?: string }>(err)
      ? err.response?.data.message || "创建项目失败，请重试"
      : err instanceof Error ? err.message : "创建项目失败，请重试");
  } finally {
    creating.value = false;
  }
}

async function importProject(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || creating.value || opening.value) return;
  opening.value = true;
  try {
    const form = new FormData();
    form.append("file", file);
    const { data } = await axios.post<{ id: string }>("/api/incept/video-studio/projects/import", form);
    await workspaceStore.refreshProjects();
    const imported = workspaceStore.projectList.find(item => item.directory === data.id);
    if (imported) {
      await workspaceStore.openProject(imported.directory);
      await router.push("/workspace");
    }
  } catch (error) {
    ElMessage.error(axios.isAxiosError<{ detail?: string }>(error) ? error.response?.data?.detail || "导入项目失败" : "导入项目失败");
  } finally { opening.value = false; }
}

async function removeProject(project: Project) {
  const confirmed = await ElMessageBox.confirm(`确定永久删除云端项目“${project.name}”及其素材？`, "删除项目", {
    type: "warning", confirmButtonText: "删除", cancelButtonText: "取消",
  }).then(() => true, () => false);
  if (!confirmed) return;
  try { await workspaceStore.removeProject(project.directory); }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : "删除项目失败"); }
}
</script>

<style lang="scss" scoped>
.home {
  position: relative;
  isolation: isolate;
  min-height: 100dvh;
  color: var(--el-text-color-primary);

  .pageBackground {
    position: absolute;
    inset: 0;
    z-index: -1;
    pointer-events: none;
  }

  .arrowHint {
    position: absolute;
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--el-color-primary);
    font-size: 13px;
    white-space: nowrap;
    pointer-events: none;

    svg {
      width: 56px;
      height: 30px;
      flex-shrink: 0;
    }

  }

  .pageHeader {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 72px;
    padding: 0 clamp(20px, 4vw, 56px);

    a {
      text-decoration: none;
    }

    .headerActions {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .githubAction {
      position: relative;

      .starHint {
        top: 0;
        right: calc(100% + 12px);
        height: 100%;

        @media (max-width: 560px) {
          top: calc(100% + 6px);
          right: 0;
          height: auto;

          svg { transform: rotate(-45deg); }
        }
      }
    }
  }

  .pageContent {
    padding: 24px clamp(20px, 4vw, 56px) 56px;

    .heroStage {
      display: grid;
      grid-template-columns: minmax(0, 1.16fr) minmax(300px, 0.84fr);
      align-items: center;
      gap: clamp(40px, 6vw, 92px);
      width: min(1180px, 100%);
      min-height: 480px;
      margin: clamp(18px, 4vh, 42px) auto 76px;
    }

    .creationPanel {
      min-width: 0;

      .studioLabel {
        display: flex;
        align-items: center;
        gap: 9px;
        margin-bottom: 22px;
        color: var(--el-text-color-regular);
        font-size: 11px;
        font-weight: 650;
        letter-spacing: 0.16em;
        text-transform: uppercase;

        .studioLabelDot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: var(--el-color-primary);
          box-shadow: 0 0 0 5px color-mix(in srgb, var(--el-color-primary) 12%, transparent);
        }
      }

      .brand {
        display: flex;
        align-items: center;
        gap: 16px;

        .brandLogo {
          width: 50px;
          height: 50px;

          .dark & { filter: invert(1); }
        }

        h1 {
          max-width: 650px;
          margin: 0;
          font-size: clamp(38px, 4.5vw, 62px);
          font-weight: 620;
          line-height: 1.03;
          letter-spacing: -0.045em;
        }
      }

      .heroIntroduction {
        max-width: 620px;
        margin: 20px 0 54px 66px;
        color: var(--el-text-color-regular);
        font-size: 15px;
        line-height: 1.75;
      }

      .promptArea {
        position: relative;

        .inspirationHint {
          bottom: calc(100% + 4px);
          left: 16px;
          height: 30px;
          padding-right: 44px;

          svg {
            position: absolute;
            top: -2px;
            right: 0;
            width: 36px;
            height: 36px;
          }
        }

        .promptCard {
          overflow: visible;
          border-color: color-mix(in srgb, var(--el-border-color) 76%, transparent);
          border-radius: calc(var(--ui-radius) * 2.5);
          background: color-mix(in srgb, var(--el-bg-color) 90%, transparent);
          box-shadow: 0 20px 55px -38px color-mix(in srgb, var(--el-text-color-primary) 42%, transparent);
          backdrop-filter: blur(18px);
          transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;

          &:focus-within {
            border-color: color-mix(in srgb, var(--el-color-primary) 52%, var(--el-border-color));
            box-shadow: 0 24px 60px -36px color-mix(in srgb, var(--el-color-primary) 34%, transparent);
          }

          :deep(.el-textarea__inner) {
            padding: 4px 0;
            box-shadow: none;
            background: transparent;
            font-size: 15px;
            line-height: 1.8;
          }

          :deep(.el-card__footer) {
            background: color-mix(in srgb, var(--el-fill-color-extra-light) 72%, transparent);
          }

          .composerFooter {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;

            .cloudWorkspaceHint {
              color: var(--el-text-color-secondary);
              font-size: 12px;
            }

            .sendActions {
              margin-left: auto;

              .modelSelect { width: 190px; }

              .sendButton {
                width: 36px;
                height: 36px;
                transition: transform 140ms ease, box-shadow 140ms ease;

                &:active { transform: scale(0.96); }
              }
            }
          }
        }
      }
    }

    .filmPreview {
      position: relative;
      min-height: 398px;
      padding: 16px;
      overflow: hidden;
      border: 1px solid color-mix(in srgb, var(--el-border-color) 65%, transparent);
      border-radius: 26px;
      background: color-mix(in srgb, var(--el-bg-color) 78%, transparent);
      box-shadow: 0 38px 80px -52px color-mix(in srgb, var(--el-text-color-primary) 50%, transparent);
      backdrop-filter: blur(20px);
      transform: rotate(0.7deg);

      &::before {
        position: absolute;
        inset: -16px 24px 16px -16px;
        z-index: -1;
        border: 1px solid color-mix(in srgb, var(--el-color-primary) 13%, transparent);
        border-radius: 30px;
        content: "";
        transform: rotate(-1.6deg);
      }

      .filmHeader,
      .filmFooter {
        position: relative;
        z-index: 4;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        color: var(--el-text-color-secondary);
        font-size: 9px;
        font-weight: 650;
        letter-spacing: 0.16em;
      }

      .filmHeader {
        height: 26px;
        padding-inline: 4px;

        .filmStatus {
          display: flex;
          align-items: center;
          gap: 6px;

          i {
            width: 5px;
            height: 5px;
            border-radius: 50%;
            background: #c34f49;
            box-shadow: 0 0 0 4px color-mix(in srgb, #c34f49 11%, transparent);
          }

          em { margin-left: 4px; font-style: normal; }
        }
      }

      .filmViewport {
        position: relative;
        height: 316px;
        overflow: hidden;
        border: 1px solid color-mix(in srgb, var(--el-text-color-primary) 12%, transparent);
        border-radius: 18px;
        background: color-mix(in srgb, var(--el-text-color-primary) 92%, #18202d);
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);
      }

      .filmPerforation {
        position: absolute;
        right: 0;
        left: 0;
        z-index: 4;
        height: 24px;
        background: repeating-linear-gradient(90deg, transparent 0 12px, rgba(255, 255, 255, 0.34) 12px 24px, transparent 24px 34px);
        mask: linear-gradient(#000 0 0) center / 100% 8px no-repeat;
        opacity: 0.55;
      }

      .filmPerforationTop { top: 2px; }
      .filmPerforationBottom { bottom: 2px; }

      .filmRail { position: absolute; inset: 0; }

      .filmShot {
        position: absolute;
        top: 34px;
        left: 50%;
        z-index: 1;
        width: 58%;
        height: 248px;
        padding: 7px;
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 10px;
        background: rgba(255, 255, 255, 0.08);
        box-shadow: 0 22px 42px rgba(0, 0, 0, 0.28);
        opacity: 0.38;
        will-change: transform, opacity;

        &:nth-child(1) { z-index: 3; opacity: 1; transform: translate3d(-50%, 0, 0) scale(1); }
        &:nth-child(2) { transform: translate3d(58%, 0, 0) scale(0.86); }
        &:nth-child(3) { opacity: 0; transform: translate3d(166%, 0, 0) scale(0.74); }
        &:nth-child(4) { transform: translate3d(-158%, 0, 0) scale(0.86); }

        .filmScene {
          position: relative;
          height: calc(100% - 27px);
          overflow: hidden;
          border-radius: 6px;

          i { position: absolute; display: block; }
        }

        .filmShotMeta {
          display: flex;
          align-items: center;
          gap: 7px;
          height: 27px;
          padding-inline: 2px;
          color: rgba(255, 255, 255, 0.72);
          font-size: 8px;
          font-weight: 650;
          letter-spacing: 0.15em;

          b { color: color-mix(in srgb, var(--el-color-primary) 70%, #fff); }
        }
      }

      .filmShotSunset .filmScene {
        background: linear-gradient(155deg, #f5dba8, #dd9177 62%, #775f72);

        .filmSun {
          top: 17%;
          left: 18%;
          width: 42px;
          height: 42px;
          border-radius: 50%;
          background: #fff1c5;
          box-shadow: 0 0 42px rgba(255, 237, 180, 0.7);
        }

        .filmDune {
          right: -12%;
          bottom: -22%;
          width: 90%;
          height: 62%;
          border-radius: 50% 0 0 0;
          background: #4d4259;
          transform: rotate(-7deg);
        }
      }

      .filmShotCity .filmScene {
        background: linear-gradient(180deg, #253b59, #6a7183 60%, #d0a07c);

        .filmMoon {
          top: 16%;
          right: 18%;
          width: 30px;
          height: 30px;
          border-radius: 50%;
          background: #f4e7c6;
          box-shadow: 0 0 34px rgba(244, 231, 198, 0.48);
        }

        .filmSkyline {
          right: -5%;
          bottom: 0;
          left: -5%;
          height: 42%;
          background: linear-gradient(90deg, #182333 0 12%, transparent 12% 15%, #182333 15% 34%, transparent 34% 38%, #182333 38% 55%, transparent 55% 59%, #182333 59% 78%, transparent 78% 82%, #182333 82%);
          clip-path: polygon(0 34%, 12% 34%, 12% 8%, 22% 8%, 22% 46%, 34% 46%, 34% 23%, 45% 23%, 45% 0, 56% 0, 56% 54%, 68% 54%, 68% 17%, 80% 17%, 80% 40%, 100% 40%, 100% 100%, 0 100%);
        }
      }

      .filmShotPortrait .filmScene {
        background: linear-gradient(145deg, #91aaba, #2d4a62);

        .filmSubject {
          right: 25%;
          bottom: -5%;
          z-index: 1;
          width: 31%;
          height: 73%;
          border-radius: 55% 55% 16% 16%;
          background: #172433;
        }

        .filmLight {
          top: -30%;
          left: 5%;
          width: 82%;
          height: 114%;
          background: linear-gradient(112deg, rgba(255, 240, 198, 0.7), transparent 56%);
          clip-path: polygon(0 0, 34% 0, 100% 100%, 52% 100%);
        }
      }

      .filmShotProduct .filmScene {
        background: linear-gradient(135deg, #dad3df, #9683a4);

        .filmProduct {
          top: 18%;
          left: 38%;
          z-index: 1;
          width: 25%;
          height: 58%;
          border: 1px solid rgba(255, 255, 255, 0.72);
          border-radius: 6px 6px 13px 13px;
          background: linear-gradient(145deg, rgba(255, 255, 255, 0.86), rgba(255, 255, 255, 0.25));
        }

        .filmShadow {
          right: 15%;
          bottom: 13%;
          width: 58%;
          height: 18%;
          border-radius: 50%;
          background: rgba(48, 31, 57, 0.25);
          filter: blur(8px);
        }
      }

      .filmFocus {
        position: absolute;
        top: 38px;
        left: 50%;
        z-index: 5;
        width: calc(58% - 16px);
        height: 204px;
        border-radius: 5px;
        box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.24), 0 0 0 999px rgba(9, 12, 18, 0.04);
        transform: translateX(-50%);
        pointer-events: none;

        i {
          position: absolute;
          width: 14px;
          height: 14px;
          border-color: rgba(255, 255, 255, 0.82);
          border-style: solid;
        }

        i:nth-child(1) { top: 8px; left: 8px; border-width: 1px 0 0 1px; }
        i:nth-child(2) { top: 8px; right: 8px; border-width: 1px 1px 0 0; }
        i:nth-child(3) { right: 8px; bottom: 8px; border-width: 0 1px 1px 0; }
        i:nth-child(4) { bottom: 8px; left: 8px; border-width: 0 0 1px 1px; }
      }

      .filmPlay {
        position: absolute;
        top: 50%;
        left: 50%;
        z-index: 6;
        display: grid;
        width: 34px;
        height: 34px;
        border: 1px solid rgba(255, 255, 255, 0.42);
        border-radius: 50%;
        background: rgba(16, 19, 26, 0.38);
        opacity: 0;
        place-items: center;
        transform: translate(-50%, -50%);
        transition: opacity 180ms ease;

        i {
          width: 0;
          height: 0;
          margin-left: 2px;
          border-top: 5px solid transparent;
          border-bottom: 5px solid transparent;
          border-left: 8px solid #fff;
        }
      }

      .filmFooter {
        height: 28px;
        padding-inline: 4px;

        .filmProgress {
          position: relative;
          flex: 1;
          height: 2px;
          overflow: hidden;
          border-radius: 999px;
          background: color-mix(in srgb, var(--el-text-color-primary) 8%, transparent);

          i {
            position: absolute;
            inset: 0;
            display: block;
            border-radius: inherit;
            background: var(--el-color-primary);
            transform: scaleX(0);
            transform-origin: left center;
          }
        }
      }

    }

    .projectList {
      max-width: 1180px;
      margin: 0 auto;

      .projectItems {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(min(100%, 310px), 1fr));
        gap: 16px;
        margin-top: 20px;

        &.listView { grid-template-columns: 1fr; }

        .projectCard {
          position: relative;
          overflow: hidden;
          border-color: color-mix(in srgb, var(--el-border-color) 70%, transparent);
          border-radius: calc(var(--ui-radius) * 1.8);
          background: color-mix(in srgb, var(--el-bg-color) 88%, transparent);
          box-shadow: none;
          transition: transform 180ms cubic-bezier(0.16, 1, 0.3, 1), border-color 180ms ease, box-shadow 180ms ease;

          .projectActions {
            position: absolute;
            top: 12px;
            right: 8px;
            display: flex;
            gap: 4px;

            .el-button { width: 32px; height: 32px; margin: 0; padding: 0; }
          }
        }

        .projectEntry {
          display: flex;
          align-items: center;
          gap: 16px;
          width: 100%;
          min-height: 132px;
          padding: 18px 84px 18px 18px;
          border: 0;
          background: transparent;
          color: inherit;
          font: inherit;
          text-align: left;
          cursor: pointer;

          &:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: -2px; }
          &:disabled { cursor: wait; opacity: 0.6; }

          .projectVisual {
            position: relative;
            display: block;
            flex: 0 0 94px;
            height: 94px;
            overflow: hidden;
            border-radius: calc(var(--ui-radius) * 1.25);
            background:
              radial-gradient(circle at 68% 28%, color-mix(in srgb, #f6d782 72%, transparent) 0 10px, transparent 11px),
              linear-gradient(145deg, color-mix(in srgb, var(--el-color-primary) 16%, var(--el-fill-color-light)), var(--el-fill-color));
            box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--el-color-primary) 12%, transparent);

            &::after {
              position: absolute;
              right: -12px;
              bottom: -16px;
              width: 76px;
              height: 48px;
              border-radius: 50% 0 0 0;
              background: color-mix(in srgb, var(--el-color-primary) 20%, var(--el-text-color-primary));
              content: "";
              opacity: 0.55;
              transform: rotate(-8deg);
            }

            .projectFrameIndex {
              position: absolute;
              top: 8px;
              left: 9px;
              z-index: 2;
              color: color-mix(in srgb, var(--el-text-color-primary) 64%, transparent);
              font-size: 9px;
              font-weight: 700;
              letter-spacing: 0.1em;
            }

            .projectFrameLines {
              position: absolute;
              top: 9px;
              right: 9px;
              display: flex;
              gap: 3px;

              i {
                width: 3px;
                height: 3px;
                border-radius: 50%;
                background: color-mix(in srgb, var(--el-text-color-primary) 34%, transparent);
              }
            }

            .projectIcon {
              position: absolute;
              bottom: 10px;
              left: 10px;
              z-index: 2;
              color: color-mix(in srgb, var(--el-bg-color) 80%, #fff);
              filter: drop-shadow(0 1px 4px rgba(25, 18, 32, 0.2));
            }
          }

          .projectInfo {
            display: flex;
            flex-direction: column;
            gap: 6px;
            min-width: 0;

            .projectName, .projectPath {
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
            }

            .projectName { font-size: 15px; font-weight: 650; }
            .projectPath { font-size: 12px; color: var(--el-text-color-regular); }
            .projectTime { font-size: 12px; color: var(--el-text-color-secondary); }
          }
        }

        &.listView {
          .projectEntry { min-height: 104px; }
          .projectVisual { flex-basis: 68px; height: 68px; }
        }
      }

      .sectionHeader {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 16px;
        padding-bottom: 16px;
        border-bottom: 1px solid var(--el-border-color-lighter);

        h2 {
          margin: 0;
          font-size: 18px;
          font-weight: 600;
        }
      }
    }
  }

  @media (hover: hover) and (pointer: fine) {
    .filmPreview:hover .filmPlay { opacity: 1; }

    .projectCard:hover {
      border-color: color-mix(in srgb, var(--el-color-primary) 28%, var(--el-border-color));
      box-shadow: 0 18px 42px -32px color-mix(in srgb, var(--el-color-primary) 38%, transparent);
      transform: translateY(-3px);
    }
  }

  @media (max-width: 980px) {
    .pageContent {
      .heroStage {
        grid-template-columns: 1fr;
        gap: 42px;
        max-width: 760px;
      }

      .filmPreview {
        width: min(560px, 86%);
        min-height: 350px;
        margin: 0 auto;

        .filmViewport { height: 268px; }
        .filmShot { height: 200px; }
        .filmFocus { height: 156px; }
      }
    }
  }

  @media (max-width: 620px) {
    .pageHeader {
      height: auto;
      min-height: 64px;
      gap: 10px;
      padding-block: 10px;

      .headerActions { gap: 6px; }
      :deep(.el-button) { padding-inline: 12px; }
    }

    .pageContent {
      padding-top: 14px;

      .heroStage { min-height: auto; margin-top: 20px; margin-bottom: 56px; }

      .creationPanel {
        .brand {
          align-items: flex-start;

          .brandLogo { width: 40px; height: 40px; margin-top: 3px; }
          h1 { font-size: clamp(34px, 11vw, 48px); }
        }

        .heroIntroduction { margin: 16px 0 52px; }

        .promptArea .promptCard .composerFooter .sendActions {
          width: 100%;
          margin-left: 0;

          .modelSelect { width: calc(100% - 48px); }
        }
      }

      .filmPreview {
        width: 94%;
        min-height: 300px;
        padding: 10px;

        .filmHeader, .filmFooter { font-size: 8px; }
        .filmViewport { height: 240px; }
        .filmShot { top: 31px; width: 64%; height: 178px; }
        .filmFocus { top: 35px; width: calc(64% - 16px); height: 134px; }
      }

      .projectList .sectionHeader { align-items: flex-start; }
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .filmPreview,
    .projectCard,
    .promptCard,
    .sendButton { transition: none !important; }

    .projectCard:hover { transform: none; }
    .filmProgress { visibility: hidden; }
    .filmPlay { display: none; }
  }
}

</style>
