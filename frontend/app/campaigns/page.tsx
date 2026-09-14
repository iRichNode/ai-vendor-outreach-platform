import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { CampaignsClient } from "./CampaignsClient";

export default async function CampaignsPage() {
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <CampaignsClient />
    </AppShell>
  );
}
