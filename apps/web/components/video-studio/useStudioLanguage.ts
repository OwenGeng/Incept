"use client";

import { useEffect, useState } from "react";
import type { StudioLanguage } from "./types";

const STORAGE_KEY = "linglonglab.video.language";

export function useStudioLanguage() {
  const [language, setLanguageState] = useState<StudioLanguage>("zh-CN");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "zh-CN" || stored === "en-US") setLanguageState(stored);
  }, []);

  const setLanguage = (next: StudioLanguage) => {
    setLanguageState(next);
    window.localStorage.setItem(STORAGE_KEY, next);
  };

  return { language, setLanguage, isChinese: language === "zh-CN" };
}
