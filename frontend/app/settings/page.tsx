import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { SettingsClient } from "./SettingsClient";

export default async function SettingsPage() {
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <SettingsClient />
    </AppShell>
  );
}
