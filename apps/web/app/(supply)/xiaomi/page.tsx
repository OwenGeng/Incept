import { Topbar } from "@/components/layout/topbar";
import { Card } from "@/components/ui/card";

export default function XiaomiPage() {
  return (
    <>
      <Topbar title="Xiaomi" subtitle="Xiaomi supply intelligence module." />
      <Card className="p-8">
        <h2 className="text-2xl font-semibold text-foreground">Xiaomi module coming soon</h2>
        <p className="mt-4 max-w-3xl text-sm leading-8 text-muted-foreground">
          This surface is reserved for the Xiaomi supply module. The navigation and shell
          are already ready to host Xiaomi-specific KPI, campaign, and AI reporting experience.
        </p>
      </Card>
    </>
  );
}
