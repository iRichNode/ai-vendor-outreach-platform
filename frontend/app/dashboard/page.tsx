import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { DashboardClient } from "./DashboardClient";

export default async function DashboardPage() {
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <DashboardClient />
    </AppShell>
  );
}
