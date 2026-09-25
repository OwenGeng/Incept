import { defineStore } from "pinia";

export const useDeveloperStore = defineStore("developer", {
  state: () => ({ developerConfirmed: false }),
  persist: { key: "linglonglabVideo.developer", storage: localStorage },
});
