import { redirect } from "next/navigation";

import { serverGet, type MeResponse, type SetupStatus } from "@/lib/auth";

export default async function RootPage() {
  const setup = await serverGet<SetupStatus>("/api/setup/status");
  if (setup?.setup_required) redirect("/setup");

  const me = await serverGet<MeResponse>("/api/auth/me");
  if (me?.authenticated) redirect("/dashboard");

  redirect("/login");
}
