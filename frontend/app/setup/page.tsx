"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Field } from "@/components/ui";
import { api, API_BASE, errorMessage } from "@/lib/api";

const STEPS = ["Welcome", "Admin account", "Finish"] as const;

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);
  const [alreadyDone, setAlreadyDone] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await api.setup.status();
        if (!cancelled && status && status.setup_required === false) setAlreadyDone(true);
      } catch {
        /* allow the wizard to render; submission will surface errors */
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const validate = (): string | null => {
    if (username.trim().length < 3) return "Username must be at least 3 characters.";
    if (password.length < 10) return "Password must be at least 10 characters.";
    if (password !== confirm) return "Passwords do not match.";
    if (email.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
      return "Enter a valid email address or leave it blank.";
    }
    return null;
  };

  const next = () => {
    if (step === 1) {
      const issue = validate();
      if (issue) {
        setError(issue);
        return;
      }
    }
    setError(null);
    setStep((value) => Math.min(value + 1, STEPS.length - 1));
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.setup.complete({
        username: username.trim(),
        password,
        email: email.trim() ? email.trim() : null,
      });
      router.replace("/login");
      router.refresh();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-xl flex-col justify-center px-4 py-10">
      <div className="mb-6">
        <span className="mb-3 grid h-11 w-11 place-items-center rounded-xl bg-indigo-600 text-lg font-bold text-white">
          AV
        </span>
        <h1 className="text-2xl font-bold">First-run setup</h1>
        <p className="muted mt-1 text-sm">
          Create the administrator account for this instance. The account is stored server-side.
        </p>
      </div>

      <ol className="mb-4 flex items-center gap-2 text-xs">
        {STEPS.map((label, index) => (
          <li key={label} className="flex items-center gap-2">
            <span
              className={`grid h-6 w-6 place-items-center rounded-full border text-[11px] font-semibold ${
                index <= step
                  ? "border-indigo-500 bg-indigo-600 text-white"
                  : "border-slate-700 bg-slate-900 text-slate-400"
              }`}
            >
              {index + 1}
            </span>
            <span className={index <= step ? "text-slate-200" : "muted"}>{label}</span>
            {index < STEPS.length - 1 ? <span className="muted">—</span> : null}
          </li>
        ))}
      </ol>

      <div className="card space-y-4">
        {error ? <div className="alert">{error}</div> : null}
        {alreadyDone && step === 0 ? (
          <div className="alert alert-info">
            This instance is already initialised. You can sign in instead.
          </div>
        ) : null}

        {step === 0 ? (
          <div className="space-y-3 text-sm text-slate-300">
            <p>The wizard will:</p>
            <ul className="ml-5 list-disc space-y-1">
              <li>Create the single administrator account</li>
              <li>Start your session with an HttpOnly cookie</li>
              <li>Take you to the dashboard to configure Gmail, Telegram and AI settings</li>
            </ul>
            <p className="muted text-xs">
              Backend: <span className="mono">{API_BASE}</span>
            </p>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="space-y-3">
            <Field label="Username" hint="3–64 characters.">
              <input
                className="input"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
              />
            </Field>
            <Field label="Password" hint="At least 10 characters.">
              <input
                className="input"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
              />
            </Field>
            <Field label="Confirm password">
              <input
                className="input"
                type="password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                autoComplete="new-password"
              />
            </Field>
            <Field label="Email (optional)" hint="Used for notifications; can be changed later.">
              <input
                className="input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </Field>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-2 text-sm">
            <p className="text-slate-300">Review and confirm:</p>
            <p>
              Username: <span className="mono text-slate-100">{username}</span>
            </p>
            <p>
              Email: <span className="mono text-slate-100">{email || "—"}</span>
            </p>
            <p className="muted text-xs">
              The password is submitted once over the API and never stored by this frontend.
            </p>
          </div>
        ) : null}

        <div className="flex justify-between gap-2 pt-1">
          <button
            type="button"
            className="btn"
            onClick={() => setStep((value) => Math.max(0, value - 1))}
            disabled={step === 0 || busy}
          >
            Back
          </button>
          {step < STEPS.length - 1 ? (
            <button type="button" className="btn btn-primary" onClick={next} disabled={checking}>
              Continue
            </button>
          ) : (
            <button type="button" className="btn btn-primary" onClick={submit} disabled={busy}>
              {busy ? "Creating account…" : "Create account & sign in"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
