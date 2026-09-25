import { VideoWorkspace } from "@/components/video-studio/VideoWorkspace";

export default async function VideoWorkspacePage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <VideoWorkspace projectId={projectId} />;
}
