import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { ConversationsClient } from "./ConversationsClient";

export default async function ConversationsPage() {
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <ConversationsClient />
    </AppShell>
  );
}
