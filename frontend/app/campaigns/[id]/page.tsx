import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { CampaignDetailClient } from "./CampaignDetailClient";

export default async function CampaignDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <CampaignDetailClient id={id} />
    </AppShell>
  );
}
