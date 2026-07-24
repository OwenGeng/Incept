"use client";

import type { Dispatch, SetStateAction } from "react";
import type { AssetSummary, CreativeThreadSummary, InceptUser, JobSummary } from "@incept/shared";
import { CreateImageView } from "./CreateImageView";
import { CreateVideoView } from "./CreateVideoView";
import type { ContentScope } from "@/lib/incept-api";

interface CreateWorkbenchViewProps {
  surface: "image" | "video";
  liveAssets: AssetSummary[];
  setLiveAssets: Dispatch<SetStateAction<AssetSummary[]>>;
  liveJobs: JobSummary[];
  setLiveJobs: Dispatch<SetStateAction<JobSummary[]>>;
  liveThreads: CreativeThreadSummary[];
  setLiveThreads: Dispatch<SetStateAction<CreativeThreadSummary[]>>;
  currentUser: InceptUser;
  contentScope: ContentScope;
  activeWorkspaceId: string;
  activeThreadId: string | null;
  onThreadSelect: (id: string | null) => void;
  onJobCreated: (job: JobSummary) => void;
}

export function CreateWorkbenchView({
  surface,
  liveAssets,
  setLiveAssets,
  liveJobs,
  setLiveJobs,
  liveThreads,
  setLiveThreads,
  currentUser,
  contentScope,
  activeWorkspaceId,
  activeThreadId,
  onThreadSelect,
  onJobCreated,
}: CreateWorkbenchViewProps) {
  return (
    <div className="flex min-h-screen flex-1 flex-col">
      <div className="min-h-0 flex-1">
        {surface === "image" ? (
          <CreateImageView
            liveAssets={liveAssets}
            setLiveAssets={setLiveAssets}
            liveJobs={liveJobs}
            setLiveJobs={setLiveJobs}
            liveThreads={liveThreads}
            setLiveThreads={setLiveThreads}
            currentUser={currentUser}
            contentScope={contentScope}
            activeWorkspaceId={activeWorkspaceId}
            activeThreadId={activeThreadId}
            onThreadSelect={onThreadSelect}
            onJobCreated={onJobCreated}
          />
        ) : (
          <CreateVideoView
            liveAssets={liveAssets}
            setLiveAssets={setLiveAssets}
            liveJobs={liveJobs}
            liveThreads={liveThreads}
            setLiveThreads={setLiveThreads}
            currentUser={currentUser}
            contentScope={contentScope}
            activeWorkspaceId={activeWorkspaceId}
            activeThreadId={activeThreadId}
            onThreadSelect={onThreadSelect}
            onJobCreated={onJobCreated}
          />
        )}
      </div>
    </div>
  );
}
