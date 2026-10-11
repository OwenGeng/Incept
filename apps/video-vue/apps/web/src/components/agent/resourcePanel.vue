<template>
  <el-button text circle :aria-label="t('Agent 设置', 'Agent settings')" :title="t('Agent 设置', 'Agent settings')" @click="visible = true"><icon-settings :size="17" /></el-button>
  <el-drawer v-model="visible" :title="t('Agent 设置', 'Agent settings')" :size="'min(560px, 100vw)'" append-to-body @keydown.stop>
    <div class="agentResources">
      <el-select v-model="resource" :aria-label="t('设置类型', 'Resource')" :disabled="loading || saving">
        <el-option v-for="item in resources" :key="item.value" :value="item.value" :label="item.label" />
      </el-select>
      <el-radio-group v-if="resource === 'memory'" v-model="scope" :disabled="loading || saving" :aria-label="t('记忆范围', 'Memory scope')">
        <el-radio-button value="project">{{ t('当前项目', 'This project') }}</el-radio-button>
        <el-radio-button value="user">{{ t('我的偏好', 'My preferences') }}</el-radio-button>
      </el-radio-group>
      <p class="resourceHelp">{{ helpText }}</p>
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
      <el-alert v-if="conflict" :title="t('内容已被其他操作修改。你的草稿仍保留，请复制草稿后重新载入最新版本再保存。', 'This resource changed elsewhere. Your draft is preserved. Copy it, then reload the latest version before saving.')" type="warning" :closable="false" show-icon />
      <div v-if="resource !== 'skills'" class="resourceToggle"><span>{{ t('对新任务启用', 'Enable for new tasks') }}</span><el-switch v-model="enabled" :disabled="loading || saving" :aria-label="t('启用资源', 'Enable resource')" /></div>
      <template v-if="resource === 'skills' && !advanced">
        <article v-for="(skill, index) in skillEntries" :key="skill.id" class="resourceEntry">
          <div class="resourceToggle"><el-input :model-value="skill.name" :aria-label="t('技能名称', 'Skill name')" :disabled="loading || saving" @update:model-value="editSkill(index, 'name', $event)" /><el-switch :model-value="skill.enabled" :aria-label="t('启用技能', 'Enable skill')" :disabled="loading || saving" @update:model-value="editSkill(index, 'enabled', $event)" /></div>
          <el-input :model-value="skill.description" :placeholder="t('用途说明', 'Description')" :aria-label="t('用途说明', 'Description')" :disabled="loading || saving" @update:model-value="editSkill(index, 'description', $event)" />
          <el-input :model-value="skill.instructions" type="textarea" :rows="4" :placeholder="t('执行指引', 'Instructions')" :aria-label="t('技能执行指引', 'Skill instructions')" :disabled="loading || saving" @update:model-value="editSkill(index, 'instructions', $event)" />
          <el-button v-if="!skill.builtin" text type="danger" :disabled="loading || saving" @click="removeSkill(index)">{{ t('移除技能', 'Remove skill') }}</el-button>
        </article>
        <el-button :disabled="loading || saving" @click="addSkill">{{ t('添加技能', 'Add skill') }}</el-button>
      </template>
      <template v-else-if="resource === 'team' && !advanced">
        <p class="revision">{{ t('本地团队成员', 'Local team members') }}</p>
        <article v-for="(agent, index) in teamEntries.agents" :key="agent.id" class="resourceEntry">
          <el-input :model-value="agent.name" :aria-label="t('成员名称', 'Member name')" :disabled="loading || saving" @update:model-value="editTeam('agents', index, 'name', $event)" />
          <el-input :model-value="agent.instructions" type="textarea" :rows="4" :placeholder="t('职责和执行指引', 'Role and instructions')" :aria-label="t('成员职责', 'Member instructions')" :disabled="loading || saving" @update:model-value="editTeam('agents', index, 'instructions', $event)" />
          <el-button text type="danger" :disabled="loading || saving" @click="removeTeam('agents', index)">{{ t('移除成员', 'Remove member') }}</el-button>
        </article>
        <el-button :disabled="loading || saving" @click="addTeam('agents')">{{ t('添加成员', 'Add member') }}</el-button>
        <p class="revision">{{ t('外部 A2A 协作', 'External A2A collaboration') }}</p>
        <article v-for="(agent, index) in teamEntries.remote_agents" :key="agent.id" class="resourceEntry">
          <el-input :model-value="agent.name" :aria-label="t('外部成员名称', 'External member name')" :disabled="loading || saving" @update:model-value="editTeam('remote_agents', index, 'name', $event)" />
          <el-input :model-value="agent.url" placeholder="https://…" :aria-label="t('A2A 服务地址', 'A2A service URL')" :disabled="loading || saving" @update:model-value="editTeam('remote_agents', index, 'url', $event)" />
          <el-button text type="danger" :disabled="loading || saving" @click="removeTeam('remote_agents', index)">{{ t('移除成员', 'Remove member') }}</el-button>
        </article>
        <el-button :disabled="loading || saving" @click="addTeam('remote_agents')">{{ t('连接外部成员', 'Connect external member') }}</el-button>
      </template>
      <el-input v-else v-model="content" type="textarea" :rows="16" :maxlength="100000" :disabled="loading || saving" :aria-label="selectedLabel" :placeholder="resource === 'team' || resource === 'skills' ? jsonExample : t('写下希望 Agent 遵循的内容…', 'Write what the Agent should remember or follow…')" />
      <el-switch v-if="resource === 'team' || resource === 'skills'" v-model="advanced" :active-text="t('高级编辑', 'Advanced editor')" :disabled="loading || saving" />
      <p v-if="revision" class="revision">{{ t('版本', 'Revision') }}: {{ revision.slice(0, 12) }}</p>
      <div class="resourceActions">
        <el-button :loading="loading" :disabled="saving" @click="load">{{ t('重新载入', 'Reload') }}</el-button>
        <el-button v-if="resource === 'memory'" type="danger" plain :disabled="loading || saving || conflict" @click="forget">{{ t('清除记忆', 'Forget memory') }}</el-button>
        <el-button type="primary" :loading="saving" :disabled="loading || conflict || !loaded" @click="save">{{ t('保存', 'Save') }}</el-button>
      </div>
    </div>
  </el-drawer>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import axios from 'axios';
import { ElMessage, ElMessageBox } from 'element-plus';
import { IconSettings } from '@tabler/icons-vue';
import { useWorkspaceStore } from '@/stores/workspace';
import { t } from '@/i18n';
const workspace = useWorkspaceStore();
const visible = ref(false);
const resource = ref<'memory' | 'rules' | 'skills' | 'team'>('memory');
const scope = ref<'project' | 'user'>('project');
const content = ref('');
const advanced = ref(false);
type SkillEntry = { id: string; name: string; description: string; instructions: string; enabled: boolean; builtin: boolean; order: number };
type TeamEntry = { id: string; name: string; instructions?: string; url?: string };
function parsedContent() { try { return JSON.parse(content.value || (resource.value === 'skills' ? '[]' : '{}')); } catch { return undefined; } }
const skillEntries = computed<SkillEntry[]>(() => { const value = parsedContent(); return Array.isArray(value) ? value : []; });
const teamEntries = computed<{ agents: TeamEntry[]; remote_agents: TeamEntry[] }>(() => { const value = parsedContent(); return { agents: value?.agents ?? [], remote_agents: value?.remote_agents ?? [] }; });
function editSkill(index: number, key: keyof SkillEntry, value: unknown) { content.value = JSON.stringify(skillEntries.value.map((skill, i) => i === index ? { ...skill, [key]: value } : skill), null, 2); }
function removeSkill(index: number) { content.value = JSON.stringify(skillEntries.value.filter((_, i) => i !== index), null, 2); }
function addSkill() { content.value = JSON.stringify([...skillEntries.value, { id: `skill-${crypto.randomUUID()}`, name: t('新技能', 'New skill'), description: '', instructions: '', enabled: true, builtin: false, order: skillEntries.value.length }], null, 2); }
function editTeam(group: 'agents' | 'remote_agents', index: number, key: keyof TeamEntry, value: string) { content.value = JSON.stringify({ ...parsedContent(), ...teamEntries.value, [group]: teamEntries.value[group].map((agent, i) => i === index ? { ...agent, [key]: value } : agent) }, null, 2); }
function removeTeam(group: 'agents' | 'remote_agents', index: number) { content.value = JSON.stringify({ ...parsedContent(), ...teamEntries.value, [group]: teamEntries.value[group].filter((_, i) => i !== index) }, null, 2); }
function addTeam(group: 'agents' | 'remote_agents') { content.value = JSON.stringify({ ...parsedContent(), ...teamEntries.value, [group]: [...teamEntries.value[group], { id: `agent-${crypto.randomUUID()}`, name: t('新成员', 'New member'), ...(group === 'agents' ? { instructions: '' } : { url: '' }) }] }, null, 2); }
const enabled = ref(true);
const revision = ref('');
const loading = ref(false);
const saving = ref(false);
const loaded = ref(false);
const conflict = ref(false);
const error = ref('');
let requestId = 0;
const resources = computed(() => [
  { value: 'memory', label: t('长期记忆', 'Long-term memory') },
  { value: 'rules', label: t('项目规则', 'Project rules') },
  { value: 'skills', label: t('技能', 'Skills') },
  { value: 'team', label: t('团队', 'Team') },
]);
const selectedLabel = computed(() => resources.value.find(item => item.value === resource.value)!.label);
const jsonExample = computed(() => resource.value === 'team' ? '{"agents": [{"id": "writer", "name": "编剧", "instructions": "Write original scripts."}], "remote_agents": []}' : '[{"id": "project-skill", "name": "Project skill", "description": "", "instructions": "", "enabled": true, "builtin": false, "order": 1}]');
const helpText = computed(() => ({
  memory: t('记忆按用户和项目隔离。你可以修改、清除或关闭；当前对话指令优先。', 'Memory is isolated by user and project. Edit, forget, or disable it. Current instructions take priority.'),
  rules: t('项目规则以 Markdown 保存，并在后续 Pi 会话中应用。', 'Project rules are saved as Markdown and applied to subsequent Pi sessions.'),
  skills: t('技能属于你的个人目录，在所有项目间共享。使用每条技能的开关启用或关闭，修改会在后续任务中生效。', 'Your skill catalog is shared across all projects. Enable or disable each skill individually. Changes apply to subsequent tasks.'),
  team: t('为团队成员分配职责，也可以连接支持 A2A 的外部服务。每个成员使用独立会话。', 'Assign roles to team members or connect external A2A services. Each member uses an independent session.'),
}[resource.value]));
function payload() { return { directory: workspace.project?.directory, resource: resource.value, scope: resource.value === 'memory' ? scope.value : 'project' }; }
function message(error: unknown) {
  if (axios.isAxiosError(error)) return error.response?.data?.message || error.response?.data?.detail?.message || error.message;
  return error instanceof Error ? error.message : String(error);
}
async function load() {
  if (!visible.value || !workspace.project?.directory) return;
  const current = ++requestId;
  loading.value = true; error.value = ''; conflict.value = false; loaded.value = false;
  try {
    const { data } = await axios.get('/api/agent/resources', { params: payload(), headers: { 'x-linglonglabVideo-workspace': '1' } });
    if (data.code !== 200) throw new Error(data.message || '读取失败');
    if (current !== requestId) return;
    content.value = data.data.content ?? ''; enabled.value = data.data.enabled !== false; revision.value = data.data.revision; loaded.value = true;
  } catch (failure) { if (current === requestId) error.value = message(failure); }
  finally { if (current === requestId) loading.value = false; }
}
async function save() {
  if (!loaded.value || conflict.value || saving.value) return;
  if (['skills', 'team'].includes(resource.value) && content.value.trim()) {
    try { JSON.parse(content.value); } catch { error.value = t('请输入有效的 JSON', 'Enter valid JSON'); return; }
  }
  saving.value = true; error.value = '';
  try {
    const { data } = await axios.patch('/api/agent/resources', { ...payload(), expectedRevision: revision.value, content: content.value, enabled: enabled.value }, { headers: { 'x-linglonglabVideo-workspace': '1' } });
    if (data.code !== 200) throw new Error(data.message || '保存失败');
    revision.value = data.data.revision;
    ElMessage.success(t('已保存，将用于后续任务', 'Saved for subsequent tasks'));
  } catch (failure) {
    conflict.value = axios.isAxiosError(failure) && failure.response?.status === 409;
    if (!conflict.value) error.value = message(failure);
  } finally { saving.value = false; }
}
async function forget() {
  const confirmed = await ElMessageBox.confirm(t('清除当前范围内的记忆？这不会删除项目、素材或对话。', 'Forget memory in this scope? Projects, assets, and conversations are preserved.'), t('清除记忆', 'Forget memory'), { confirmButtonText: t('清除', 'Forget'), cancelButtonText: t('取消', 'Cancel'), type: 'warning' }).catch(() => false);
  if (!confirmed) return;
  content.value = ''; await save();
}
watch([visible, resource, scope, () => workspace.project?.directory], () => { void load(); });
</script>
<style scoped>
.agentResources { display: flex; flex-direction: column; gap: 16px; }
.resourceEntry { display: flex; flex-direction: column; gap: 10px; padding: 12px; border: 1px solid var(--el-border-color-light); border-radius: var(--el-border-radius-base); }
.resourceHelp, .revision { margin: 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }
.resourceToggle, .resourceActions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.resourceActions { justify-content: flex-end; flex-wrap: wrap; }
.resourceActions :deep(.el-button) { margin-left: 0; }
</style>
