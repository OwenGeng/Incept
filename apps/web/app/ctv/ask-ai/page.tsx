import { Topbar } from "@/components/layout/topbar";
import { Card } from "@/components/ui/card";
import { MessageSquare } from "lucide-react";

export default function CtvAskAiPage() {
  return (
    <>
      <Topbar title="Ask AI" subtitle="Your CTV data analyst — ask any question about your CTV business." />
      <Card className="p-10 text-center">
        <div className="mx-auto mb-5 flex size-16 items-center justify-center rounded-2xl bg-gradient-to-br from-[#f97316] to-[#ea580c] shadow-lg">
          <MessageSquare className="size-8 text-white" />
        </div>
        <h2 className="text-xl font-semibold text-foreground">CTV Ask AI — Coming Soon</h2>
        <p className="mx-auto mt-3 max-w-md text-sm leading-7 text-muted-foreground">
          Once CTV data is available, you&apos;ll be able to ask your AI analyst any question
          about CTV-to-web, CTV-to-app attribution, and campaign performance.
        </p>
      </Card>
    </>
  );
}
