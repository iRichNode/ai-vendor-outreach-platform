import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { QueueClient } from "./QueueClient";

export default async function QueuePage() {
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <QueueClient />
    </AppShell>
  );
}
