<template>
  <div class="aboutPanel">
    <img :src="logoUrl" alt="LinglongLab" />
    <div>
      <h3>LinglongLab Video</h3>
      <p>Vue 视频工作台 · FastAPI 统一后端</p>
      <p class="muted">版本 {{ version }}</p>
    </div>
    <el-divider />
    <el-descriptions :column="1" border>
      <el-descriptions-item label="项目与设置">LinglongLab FastAPI</el-descriptions-item>
      <el-descriptions-item label="AI 模型">Google Vertex AI（部署托管）</el-descriptions-item>
      <el-descriptions-item label="身份方式">内部无登录视频入口</el-descriptions-item>
      <el-descriptions-item label="前端">Vue 3 + Element Plus + Vue Flow</el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<script setup lang="ts">
import logoUrl from "@linglonglab/video-assets/logo.png";
const version = import.meta.env.appVersion;
</script>

<style scoped lang="scss">
.aboutPanel {
  display: grid;
  grid-template-columns: 72px 1fr;
  align-items: center;
  gap: 16px;

  img { width: 64px; height: 64px; object-fit: contain; }
  h3 { margin: 0 0 6px; font-size: 20px; }
  p { margin: 0; }
  .muted { margin-top: 6px; color: var(--el-text-color-secondary); font-size: 12px; }
  .el-divider, .el-descriptions { grid-column: 1 / -1; }
}
</style>
