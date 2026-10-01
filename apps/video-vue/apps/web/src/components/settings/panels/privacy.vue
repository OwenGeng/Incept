<template>
  <div class="privacy">
    <el-alert title="外部匿名统计已关闭" type="success" :closable="false" showIcon>
      <template #default>
        视频工作台不会向第三方统计服务发送提示词、对话、项目、文件路径或使用事件。
      </template>
    </el-alert>
    <el-descriptions :column="1" border>
      <el-descriptions-item label="凭据">仅保存在 LinglongLab 服务端环境，浏览器不接收 Google Cloud 凭据</el-descriptions-item>
      <el-descriptions-item label="项目数据">通过 FastAPI 写入当前 LinglongLab 部署</el-descriptions-item>
      <el-descriptions-item label="模型请求">由后端使用部署 Service Account 调用 Vertex AI</el-descriptions-item>
      <el-descriptions-item label="外部遥测">禁用</el-descriptions-item>
    </el-descriptions>
  </div>
</template>

<style scoped>
.privacy { display: grid; gap: 18px; padding: 0 4px 8px; }
</style>
