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
        <aside ref="storyboardPreview" class="storyboardPreview" aria-hidden="true">
          <div class="previewHeader">
            <span>STORYBOARD</span>
            <span>01—03</span>
          </div>
          <div class="storyFrame storyFrameOne">
            <div class="frameScene"><i class="frameSun" /><i class="frameHorizon" /></div>
            <div class="frameMeta"><b>01</b><span>{{ t("开场", "OPEN") }}</span><em>00:00</em></div>
          </div>
          <div class="storyFrame storyFrameTwo">
            <div class="frameScene"><i class="frameSubject" /><i class="frameLight" /></div>
            <div class="frameMeta"><b>02</b><span>{{ t("场景", "SCENE") }}</span><em>00:06</em></div>
          </div>
          <div class="storyFrame storyFrameThree">
            <div class="frameScene"><i class="frameProduct" /><i class="frameShadow" /></div>
            <div class="frameMeta"><b>03</b><span>{{ t("收束", "CLOSE") }}</span><em>00:12</em></div>
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
import { stagger } from "animejs/utils";
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
const storyboardPreview = ref<HTMLElement>();
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
let entranceTimeline: ReturnType<typeof createTimeline> | undefined;

onMounted(() => {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const copy = heroCopy.value;
  const preview = storyboardPreview.value;
  const projects = projectListElement.value;
  if (!copy || !preview || !projects) return;

  const frames = preview.querySelectorAll<HTMLElement>(".storyFrame");
  entranceTimeline = createTimeline({ defaults: { ease: "out(3)" } })
    .add(copy, { opacity: [0, 1], y: [18, 0], duration: 620 }, 0)
    .add(preview, { opacity: [0, 1], x: [24, 0], duration: 680 }, 100)
    .add(frames, { opacity: [0, 1], y: [28, 0], rotate: [-1.5, 0], duration: 560, delay: stagger(85) }, 150)
    .add(projects, { opacity: [0, 1], y: [14, 0], duration: 520 }, 300);
});

onBeforeUnmount(() => entranceTimeline?.revert());

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

    .storyboardPreview {
      position: relative;
      display: grid;
      grid-template-columns: 1fr 0.88fr;
      grid-template-rows: auto 1fr 0.82fr;
      gap: 12px;
      min-height: 398px;
      padding: 16px;
      border: 1px solid color-mix(in srgb, var(--el-border-color) 65%, transparent);
      border-radius: 26px;
      background: color-mix(in srgb, var(--el-bg-color) 75%, transparent);
      box-shadow: 0 38px 80px -52px color-mix(in srgb, var(--el-text-color-primary) 50%, transparent);
      backdrop-filter: blur(20px);
      transform: rotate(1.2deg);

      &::before {
        position: absolute;
        inset: -14px 22px 14px -14px;
        z-index: -1;
        border: 1px solid color-mix(in srgb, var(--el-color-primary) 14%, transparent);
        border-radius: 30px;
        content: "";
        transform: rotate(-2.2deg);
      }

      .previewHeader {
        grid-column: 1 / -1;
        display: flex;
        justify-content: space-between;
        padding: 2px 4px 5px;
        color: var(--el-text-color-secondary);
        font-size: 10px;
        font-weight: 650;
        letter-spacing: 0.17em;
      }

      .storyFrame {
        min-width: 0;
        padding: 8px;
        border: 1px solid color-mix(in srgb, var(--el-border-color) 70%, transparent);
        border-radius: 14px;
        background: color-mix(in srgb, var(--el-bg-color) 92%, transparent);
        box-shadow: 0 12px 24px -20px color-mix(in srgb, var(--el-text-color-primary) 38%, transparent);

        .frameScene {
          position: relative;
          height: calc(100% - 28px);
          min-height: 96px;
          overflow: hidden;
          border-radius: 9px;
          background: var(--el-fill-color-light);

          i { position: absolute; display: block; }
        }

        .frameMeta {
          display: grid;
          grid-template-columns: auto 1fr auto;
          align-items: center;
          gap: 7px;
          padding: 8px 2px 0;
          font-size: 9px;
          letter-spacing: 0.1em;

          b { color: var(--el-color-primary); }
          span { color: var(--el-text-color-regular); font-weight: 650; }
          em { color: var(--el-text-color-secondary); font-style: normal; }
        }
      }

      .storyFrameOne {
        grid-row: 2 / 4;

        .frameScene {
          min-height: 250px;
          background: linear-gradient(155deg, #f4d79f, #df8e73 64%, #785d71);

          &::after {
            position: absolute;
            right: -12%;
            bottom: -24%;
            width: 86%;
            height: 58%;
            border-radius: 50% 0 0 0;
            background: #4d4259;
            content: "";
            transform: rotate(-7deg);
          }
        }

        .frameSun {
          top: 19%;
          left: 18%;
          width: 42px;
          height: 42px;
          border-radius: 50%;
          background: #fff1c5;
          box-shadow: 0 0 42px rgba(255, 237, 180, 0.75);
        }

        .frameHorizon {
          right: -8%;
          bottom: 22%;
          width: 90%;
          height: 2px;
          background: rgba(255, 255, 255, 0.42);
          transform: rotate(-9deg);
        }
      }

      .storyFrameTwo .frameScene {
        background: linear-gradient(145deg, #88a6b8, #314f68);

        .frameSubject {
          right: 20%;
          bottom: -4%;
          width: 34%;
          height: 74%;
          border-radius: 55% 55% 16% 16%;
          background: #172433;
        }

        .frameLight {
          top: -28%;
          left: 8%;
          width: 80%;
          height: 110%;
          background: linear-gradient(112deg, rgba(255, 240, 198, 0.7), transparent 56%);
          clip-path: polygon(0 0, 34% 0, 100% 100%, 52% 100%);
        }
      }

      .storyFrameThree .frameScene {
        background: linear-gradient(135deg, #d7cfdc, #9b88a8);

        .frameProduct {
          top: 20%;
          left: 38%;
          z-index: 1;
          width: 28%;
          height: 56%;
          border: 1px solid rgba(255, 255, 255, 0.7);
          border-radius: 6px 6px 12px 12px;
          background: linear-gradient(145deg, rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.25));
        }

        .frameShadow {
          right: 14%;
          bottom: 14%;
          width: 56%;
          height: 18%;
          border-radius: 50%;
          background: rgba(48, 31, 57, 0.25);
          filter: blur(8px);
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

      .storyboardPreview {
        width: min(560px, 86%);
        min-height: 330px;
        margin: 0 auto;

        .storyFrameOne .frameScene { min-height: 190px; }
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

      .storyboardPreview {
        grid-template-columns: 1fr 0.82fr;
        width: 94%;
        min-height: 292px;
        padding: 10px;

        .storyFrame { padding: 6px; }
        .storyFrameOne .frameScene { min-height: 164px; }
      }

      .projectList .sectionHeader { align-items: flex-start; }
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .storyboardPreview,
    .projectCard,
    .promptCard,
    .sendButton { transition: none !important; }

    .projectCard:hover { transform: none; }
  }
}

</style>
