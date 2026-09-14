import { AppShell } from "@/components/AppShell";
import { requireAuth } from "@/lib/auth";

import { VendorsClient } from "./VendorsClient";

export default async function VendorsPage() {
  const me = await requireAuth();
  return (
    <AppShell user={me.user}>
      <VendorsClient />
    </AppShell>
  );
}
