export type PluginInstallType = "node" | "tool" | "skill" | "provider" | "agent";

export type PluginInstallRequest = {
  type: PluginInstallType;
  url: string;
  fileName: string;
};

export type updateSnapshot = {
  version: string;
  channel: string;
  hash: string;
  latestVersion: string;
  latestHash: string;
  error: string;
  updateAvailable: boolean;
  updateReady: boolean;
  updating: boolean;
  canUpdate: boolean;
};
