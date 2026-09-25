import { createApp, h } from "vue";
import { ElButton, ElResult } from "element-plus";
import { createPinia } from "pinia";
import { createPersistedState } from "pinia-plugin-persistedstate";
import App from "./App.vue";
import "@/assets/main.scss";
import "element-plus/es/components/message-box/style/css";
import "element-plus/es/components/button/style/css";
import "element-plus/es/components/result/style/css";

import router from "@/router";
import { loadSettings, settingsStorage } from "@/stores/settings";

const app = createApp(App);
let isMounted = false;

loadSettings().then(async () => {
  app.use(createPinia().use(createPersistedState({ storage: settingsStorage })));
  app.use(router);
  await router.isReady();
  app.mount("#app");
  isMounted = true;
}).catch(async (error) => {
  console.error("页面初始化失败：", error);
  if (isMounted) app.unmount();
  createApp({
    render: () => h(ElResult, {
      icon: "error",
      title: "启动失败",
      subTitle: error instanceof Error ? error.message : "无法加载应用，请重试。",
    }, {
      extra: () => h(ElButton, { type: "primary", onClick: () => window.location.reload() }, () => "重试"),
    }),
  }).mount("#app");
});
