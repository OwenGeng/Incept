import { GamingPlayableWorkspace } from "@/components/gaming-playable/GamingPlayableWorkspace";

export default async function PlayableProjectPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <GamingPlayableWorkspace embedded initialProjectId={projectId} />;
}
