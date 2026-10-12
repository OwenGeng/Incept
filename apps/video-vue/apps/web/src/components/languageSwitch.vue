<template>
  <el-radio-group
    v-model="language"
    class="languageSwitch"
    data-no-translate
    size="small"
    :aria-label="t('界面语言', 'Interface language')">
    <el-radio-button value="zh-CN">{{ t("中文", "Chinese") }}</el-radio-button>
    <el-radio-button value="en">EN</el-radio-button>
  </el-radio-group>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { interfaceLanguage, setInterfaceLanguage, t, type InterfaceLanguage } from "@/i18n";

const language = computed({
  get: () => interfaceLanguage.value,
  set: value => setInterfaceLanguage(value as InterfaceLanguage),
});
</script>

<style scoped lang="scss">
.languageSwitch {
  flex-shrink: 0;

  :deep(.el-radio-button__inner) {
    min-width: 42px;
    padding: 7px 10px;
    font-size: 12px;
  }
}
</style>
