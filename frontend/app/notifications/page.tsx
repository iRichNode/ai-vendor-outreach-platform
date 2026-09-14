import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { NotificationsClient } from "./NotificationsClient";

export default async function NotificationsPage() {
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <NotificationsClient />
    </AppShell>
  );
}
