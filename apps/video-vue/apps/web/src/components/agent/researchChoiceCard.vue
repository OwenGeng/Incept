<template>
  <section class="researchChoice" data-no-translate :aria-label="t('竞品调研选择', 'Reference research choice')" :aria-busy="submitting">
    <h4>{{ t('是否先进行 YouTube 等平台的竞品调研？', 'Research competitors and video references first?') }}</h4>
    <p>{{ t('提交选择后才会搜索；找到链接或字幕不等于已审看视频画面。', 'Search starts only after confirmation. Links or subtitles are not a visual video review.') }}</p>
    <template v-if="question.status !== 'consumed'">
      <el-radio-group v-model="choice" :disabled="disabled || submitting || question.status === 'answered'" :aria-label="t('调研范围', 'Research scope')">
        <el-radio value="light">{{ t('轻量调研 · 5 条参考', 'Light research · 5 references') }}</el-radio>
        <el-radio value="deep">{{ t('深度调研 · 20–30 条参考', 'Deep research · 20–30 references') }}</el-radio>
        <el-radio value="off">{{ t('暂不调研 · 仅根据客户官网出方案', 'No reference research · website-based proposal') }}</el-radio>
      </el-radio-group>
      <el-input v-model="notes" type="textarea" :rows="2" maxlength="2000" :disabled="disabled || submitting || question.status === 'answered'" :aria-label="t('补充调研要求（可选）', 'Additional research preferences (optional)')" :placeholder="t('可补充竞品名称、市场或参考链接（可选）', 'Competitor names, market or reference links (optional)')" />
      <div class="actions">
        <el-button type="primary" :loading="submitting" :disabled="disabled || !choice" @click="submit(false)">{{ t('确认并继续', 'Confirm and continue') }}</el-button>
        <el-button :disabled="disabled || submitting || question.status === 'answered'" @click="submit(true)">{{ t('跳过竞品调研', 'Skip reference research') }}</el-button>
      </div>
    </template>
    <p v-else role="status">{{ t('已提交：', 'Submitted: ') }}{{ label }}</p>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import axios from 'axios';
import { t } from '@/i18n';
import type { AgentConversation } from './types';

const props = defineProps<{ question: NonNullable<AgentConversation['researchQuestion']>; directory?: string; sessionFile?: string; disabled: boolean }>();
const emit = defineEmits<{ resume: [id: string, prompt: string] }>();
const choice = ref(props.question.choice ?? '');
const notes = ref(props.question.notes ?? '');
const submitting = ref(false);
const error = ref('');
const label = computed(() => props.question.choice === 'light' ? t('轻量调研', 'Light research') : props.question.choice === 'deep' ? t('深度调研', 'Deep research') : t('暂不调研', 'No reference research'));

async function submit(skipped: boolean) {
  if (submitting.value || props.disabled || !props.directory || !props.sessionFile || (!skipped && !choice.value)) return;
  submitting.value = true;
  error.value = '';
  try {
    const { data } = await axios.post('/api/agent/answer', { directory: props.directory, sessionFile: props.sessionFile,
      callId: props.question.id, choice: skipped ? 'off' : choice.value, skipped, notes: notes.value }, { headers: { 'x-linglonglabVideo-workspace': '1' } });
    if (data.code !== 200) throw new Error(data.message || t('提交失败，请重试。', 'Could not submit. Try again.'));
    emit('resume', data.data.questionId, data.data.prompt);
  } catch (reason) {
    error.value = (axios.isAxiosError(reason) && (reason.response?.data?.message || reason.response?.data?.detail?.message)) || t('提交失败，请重新打开会话后重试。', 'Could not submit. Reopen the conversation and retry.');
  } finally { submitting.value = false; }
}
</script>

<style scoped>
.researchChoice { border: 1px solid var(--el-border-color); border-radius: var(--el-border-radius-base); padding: 16px; margin: 12px 0; }
h4 { margin: 0 0 8px; }
p { line-height: 1.6; color: var(--el-text-color-secondary); }
.el-radio-group { display: flex; flex-direction: column; align-items: flex-start; }
:deep(.el-radio) { height: auto; min-height: 36px; margin-right: 0; }
:deep(.el-radio__label) { white-space: normal; line-height: 1.5; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.actions .el-button { margin-left: 0; }
.error { color: var(--el-color-danger); }
</style>
