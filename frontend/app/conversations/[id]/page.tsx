import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { ConversationDetailClient } from "./ConversationDetailClient";

export default async function ConversationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <ConversationDetailClient id={id} />
    </AppShell>
  );
}
