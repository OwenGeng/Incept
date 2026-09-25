import { defineStore } from "pinia";
import { ref } from "vue";
import axios from "axios";

export type Project = {
  directory: string;
  name: string;
  lastOpenedAt: number;
};

export const useWorkspaceStore = defineStore("workspace", () => {
  const project = ref<Project | null>(null);
  const projectList = ref<Project[]>([]);
  const pendingAgentMessage = ref<{ directory: string; prompt: string; model: string; reasoningEffort: string } | null>(null);

  async function openProject(path: string, previousDirectory = path, signal?: AbortSignal) {
    const { data } = await axios.get<{ code: number; data?: { directory: string }; message?: string }>("/api/workspaces/check", {
      params: { directory: path }, headers: { "x-linglonglabVideo-workspace": "1" }, signal,
    });
    signal?.throwIfAborted();
    if (data.code !== 200 || !data.data?.directory) throw new Error(data.message || "工作目录校验失败");
    const checkedDirectory = data.data.directory;
    pendingAgentMessage.value = null;
    const existing = projectList.value.find(project => project.directory === previousDirectory)
      ?? projectList.value.find(project => project.directory === checkedDirectory);
    project.value = { directory: checkedDirectory, name: existing?.name || checkedDirectory.split(/[\\/]/).filter(Boolean).at(-1) || checkedDirectory, lastOpenedAt: Date.now() };
    projectList.value = [
      project.value,
      ...projectList.value.filter(item => item.directory !== previousDirectory && item.directory !== checkedDirectory),
    ];
  }

  async function refreshProjects(signal?: AbortSignal) {
    const { data } = await axios.get<{ code: number; data: Project[]; message?: string }>("/api/workspaces/projects", { signal });
    if (data.code !== 200 || !Array.isArray(data.data)) throw new Error(data.message || "读取项目列表失败");
    projectList.value = data.data;
    if (project.value) project.value = data.data.find(item => item.directory === project.value?.directory) ?? null;
  }

  async function createProject(name: string, description = "") {
    const { data } = await axios.post<{ code: number; data: Project; message?: string }>("/api/workspaces/create", { name, description });
    if (data.code !== 200 || !data.data?.directory) throw new Error(data.message || "创建项目失败");
    project.value = data.data;
    projectList.value = [data.data, ...projectList.value.filter(item => item.directory !== data.data.directory)];
    return data.data;
  }

  async function renameProject(path: string, name: string) {
    const { data } = await axios.patch<{ code: number; data: Project; message?: string }>("/api/workspaces/project", { directory: path, name });
    if (data.code !== 200) throw new Error(data.message || "重命名项目失败");
    const target = projectList.value.find(item => item.directory === path);
    if (!target || !name.trim()) return;
    Object.assign(target, data.data);
    if (project.value?.directory === path) project.value = target;
  }

  async function removeProject(path: string) {
    const { data } = await axios.delete<{ code: number; message?: string }>("/api/workspaces/project", { params: { directory: path } });
    if (data.code !== 200) throw new Error(data.message || "删除项目失败");
    projectList.value = projectList.value.filter(item => item.directory !== path);
    if (project.value?.directory === path) project.value = null;
  }

  return { project, projectList, pendingAgentMessage, refreshProjects, createProject, openProject, renameProject, removeProject };
}, {
  persist: {
    key: "linglonglabVideo.projectList",
    pick: ["project", "projectList"],
  },
});
