<template>
  <div class="deploymentModels">
    <el-alert
      title="模型由 LinglongLab 的 Google Cloud 部署统一管理"
      description="浏览器不保存 API Key，也不能修改模型 ID、区域或服务端点。变更请通过部署配置完成。"
      type="info"
      :closable="false"
      showIcon />
    <el-skeleton v-if="loading" :rows="4" animated />
    <el-empty v-else-if="!models.length" description="当前部署未启用此类模型" />
    <div v-else class="modelList">
      <el-card v-for="model in models" :key="`${model.providerId}:${model.modelId}:${model.type ?? 'text'}`" shadow="never">
        <div class="modelHeader">
          <div>
            <strong>{{ model.label }}</strong>
            <p>{{ model.modelId }}</p>
          </div>
          <el-tag type="success">已由后端启用</el-tag>
        </div>
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="提供方">{{ model.providerLabel }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ model.type ? mediaLabels[model.type] ?? model.type : '文本' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>
    </div>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
  </div>
</template>

<script setup lang="ts">
import axios from "axios";
import { onMounted, ref } from "vue";

type Model = {
  providerId: string;
  providerLabel: string;
  modelId: string;
  label: string;
  type?: "image" | "video" | "audio";
};

const props = defineProps<{ kind: "text" | "media" }>();
const models = ref<Model[]>([]);
const loading = ref(true);
const error = ref("");
const mediaLabels: Record<string, string> = { image: "图片", video: "视频", audio: "音频" };

onMounted(async () => {
  try {
    const url = props.kind === "text" ? "/api/ai/models" : "/api/ai/media/models";
    const { data } = await axios.get<{ code: number; data: Model[]; message?: string }>(url);
    if (data.code !== 200 || !Array.isArray(data.data)) throw new Error(data.message || "读取部署模型失败");
    models.value = data.data;
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : "读取部署模型失败";
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped lang="scss">
.deploymentModels {
  display: grid;
  gap: 16px;

  .modelList { display: grid; gap: 12px; }
  .modelHeader {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 14px;

    p {
      margin: 4px 0 0;
      color: var(--el-text-color-secondary);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
    }
  }
}
</style>
