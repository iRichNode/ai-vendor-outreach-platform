import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { FindVendorsClient } from "./FindVendorsClient";

export default async function FindVendorsPage() {
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <FindVendorsClient />
    </AppShell>
  );
}
