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
      <section class="creationPanel" aria-label="创建项目">
        <div class="brand">
          <el-image class="brandLogo" :src="logoUrl" fit="contain" alt="LinglongLab" />
          <h1>LinglongLab</h1>
        </div>
        <div class="promptArea">
          <span class="arrowHint inspirationHint">
            灵感创作模式
            <svg viewBox="0 0 60 60" fill="none" aria-hidden="true">
              <path d="M4 9C21 0 44 5 40 23C36 39 14 34 22 20C30 7 49 21 47 52M38 43L47 52L54 42" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </span>
          <el-card class="promptCard" shadow="never" :bodyStyle="{ padding: '20px' }" :footerStyle="{ padding: '12px 16px' }">
            <el-input v-model="prompt" type="textarea" :rows="4" resize="none" :disabled="creating || opening" :placeholder="promptPlaceholder" aria-label="创作描述" />
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
      </section>
      <section class="projectList" aria-labelledby="projectListTitle">
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
          <el-card v-for="project in sortedProjects" :key="project.directory" class="projectCard" shadow="hover" :bodyStyle="{ padding: '0' }">
            <button class="projectEntry" type="button" :disabled="creating || opening" :aria-label="`打开项目 ${project.name}`" @click="openProject(project)">
              <icon-folder class="projectIcon" :size="28" aria-hidden="true" />
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
import { storeToRefs } from "pinia";
import { computed, onMounted, ref, watch } from "vue";
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
    animation: hintNudge 2.4s ease-in-out infinite;

    svg {
      width: 56px;
      height: 30px;
      flex-shrink: 0;
    }

    @media (prefers-reduced-motion: reduce) {
      animation: none;
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

    .creationPanel {
      max-width: 800px;
      margin: clamp(32px, 6vh, 64px) auto 56px;

      .brand {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 16px;
        margin-bottom: 36px;

        .brandLogo {
          width: 48px;
          height: 48px;

          .dark & {
            filter: invert(1);
          }
        }

        h1 {
          margin: 0;
          font-size: clamp(30px, 4vw, 38px);
          font-weight: 600;
          letter-spacing: -1px;
        }
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
          border-radius: calc(var(--ui-radius) * 2.5);
          border-color: var(--el-border-color-lighter);
          box-shadow: var(--el-box-shadow-lighter);

          &:focus-within {
            border-color: var(--el-color-primary-light-5);
          }

          :deep(.el-textarea__inner) {
            padding: 4px 0;
            box-shadow: none;
            background: transparent;
            font-size: 15px;
            line-height: 1.8;
          }

          :deep(.el-card__footer) {
            background: var(--el-fill-color-extra-light);
          }

          .composerFooter {
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;

            .sendActions {
              margin-left: auto;

              .modelSelect {
                width: 190px;
              }

              .sendButton {
                width: 36px;
                height: 36px;
              }
            }
          }
        }
      }
    }

    .projectList {
      max-width: 1040px;
      margin: 0 auto;

      .projectItems {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
        gap: 16px;
        margin-top: 16px;

        &.listView { grid-template-columns: 1fr; }

        .projectCard {
          position: relative;

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
          align-items: flex-start;
          gap: 12px;
          width: 100%;
          padding: 20px 84px 20px 20px;
          border: 0;
          background: transparent;
          color: inherit;
          font: inherit;
          text-align: left;
          cursor: pointer;

          &:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: -2px; }
          &:disabled { cursor: wait; opacity: 0.6; }

          .projectIcon { flex-shrink: 0; color: var(--el-color-primary); }

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

            .projectName { font-weight: 600; }
            .projectPath { font-size: 13px; color: var(--el-text-color-regular); }
            .projectTime { font-size: 12px; color: var(--el-text-color-secondary); }
          }
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
}

@keyframes hintNudge {
  0%, 100% { transform: translateX(0) rotate(-3deg); }
  50% { transform: translateX(-6px) rotate(-5deg); }
}
</style>
