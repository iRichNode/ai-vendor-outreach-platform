import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { AnalyticsClient } from "./AnalyticsClient";

export default async function AnalyticsPage() {
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <AnalyticsClient />
    </AppShell>
  );
}
