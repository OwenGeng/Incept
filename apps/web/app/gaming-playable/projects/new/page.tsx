import { redirect } from "next/navigation";

export default function NewPlayableWorkspacePage() {
  // Preserve existing deep links while keeping every new-project path in one flow.
  redirect("/gaming-playable/new");
}
