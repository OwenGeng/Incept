"use client";

import "@ant-design/v5-patch-for-react-19";
import { Component, useEffect, type ReactNode } from "react";
import { App as AntApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import enUS from "antd/locale/en_US";
import RouterApp from "./App";
import i18n from "./i18n";
import { isAiVideoMockEnabled } from "./runtime";
import { useAppStore } from "./store/useAppStore";
import { SystemTextEnglishAdapter } from "./components/SystemTextEnglishAdapter";
import { AntdMessageBridge } from "./components/AntdMessageBridge";
import "./services/openapi";

function AiVideoRoot() {
  const language = useAppStore((state) => state.language);
  const antdLocale = language === "en-US" ? enUS : zhCN;

  useEffect(() => {
    if (!isAiVideoMockEnabled) return;
    void import("./mocks/browser")
      .then(({ worker }) => worker.start({ onUnhandledRequest: "bypass" }))
      .catch((error: unknown) => console.error("AI Video mock service failed to start", error));
  }, []);

  return (
    <ConfigProvider
      locale={antdLocale}
      theme={{
        token: {
          colorPrimary: "#356fec",
          colorInfo: "#356fec",
          colorText: "#101318",
          colorTextSecondary: "#5f6673",
          colorBorder: "#e6e8ec",
          colorBgLayout: "#f6f8fb",
          colorBgContainer: "#ffffff",
          borderRadius: 12,
          borderRadiusLG: 16,
        },
      }}
    >
      <AntApp>
        <AntdMessageBridge />
        <SystemTextEnglishAdapter />
        <RouterApp />
      </AntApp>
    </ConfigProvider>
  );
}

type BoundaryState = { error: Error | null };

class AiVideoErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  render() {
    if (this.state.error) {
      const isChinese = i18n.language === "zh-CN";
      return (
        <div style={{ padding: 24, fontFamily: "sans-serif" }}>
          <h2>{isChinese ? "页面加载出错" : "Page failed to load"}</h2>
          <pre style={{ color: "#c00", overflow: "auto" }}>{this.state.error.message}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

export function AiVideoApp() {
  return (
    <AiVideoErrorBoundary>
      <AiVideoRoot />
    </AiVideoErrorBoundary>
  );
}
