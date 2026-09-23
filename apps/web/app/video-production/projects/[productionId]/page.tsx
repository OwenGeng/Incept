import { VideoProductionWorkspace } from "@/components/video-production/VideoProductionWorkspace";

export default async function VideoProductionProjectPage({ params }: { params: Promise<{ productionId: string }> }) {
  const { productionId } = await params;
  return <VideoProductionWorkspace productionId={productionId} />;
}
