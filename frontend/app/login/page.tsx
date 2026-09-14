"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ToastProvider, useToast } from "@/components/Toast";
import { Field } from "@/components/ui";
import { api, API_BASE, errorMessage } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const toast = useToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await api.setup.status();
        if (cancelled) return;
        if (status?.setup_required) {
          router.replace("/setup");
          return;
        }
        const me = await api.auth.me();
        if (!cancelled && me?.authenticated) {
          router.replace("/dashboard");
          return;
        }
      } catch {
        /* backend unreachable: keep showing the login form */
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.auth.login(username.trim(), password);
      toast("Signed in", "success");
      router.replace("/dashboard");
      router.refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-4 py-10">
      <div className="mb-6 text-center">
        <span className="mx-auto mb-3 grid h-11 w-11 place-items-center rounded-xl bg-indigo-600 text-lg font-bold text-white">
          AV
        </span>
        <h1 className="text-2xl font-bold">Sign in</h1>
        <p className="muted mt-1 text-sm">AI Vendor Outreach operator console</p>
      </div>

      <form onSubmit={submit} className="card space-y-4">
        {error ? <div className="alert">{error}</div> : null}
        <Field label="Username">
          <input
            className="input"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            required
          />
        </Field>
        <Field label="Password">
          <input
            className="input"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </Field>
        <button className="btn btn-primary w-full" type="submit" disabled={busy || checking}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="muted text-center text-xs">
          Sessions are cookie-based (HttpOnly). No token is stored in this app.
          <br />
          API: <span className="mono">{API_BASE}</span>
        </p>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <ToastProvider>
      <LoginForm />
    </ToastProvider>
  );
}
