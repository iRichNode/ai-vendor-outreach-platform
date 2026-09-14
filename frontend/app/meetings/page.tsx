import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { MeetingsClient } from "./MeetingsClient";

export default async function MeetingsPage() {
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <MeetingsClient />
    </AppShell>
  );
}
