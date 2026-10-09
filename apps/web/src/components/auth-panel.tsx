"use client";

import { useState } from "react";

import { login, logout, register, verifyEmail } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button, Card, ErrorNote, Field, Note, inputClass } from "@/components/ui";

type Mode = "login" | "register";

export function AuthPanel() {
  const { me, loading, refresh } = useSession();
  const [mode, setMode] = useState<Mode>("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingToken, setPendingToken] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (mode === "register") {
        const created = await register({
          email,
          password,
          full_name: fullName || undefined,
          workspace_name: workspaceName || undefined,
        });
        // Development builds return the token so there is no need for a mail
        // server; production returns null and this stays hidden.
        setPendingToken(created.dev_verification_token);
        if (!created.dev_verification_token) {
          setError(null);
        }
      } else {
        await login(email, password);
        setPassword("");
        refresh();
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!pendingToken) return;
    setBusy(true);
    setError(null);
    try {
      await verifyEmail(pendingToken);
      setPendingToken(null);
      setPassword("");
      refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <Card title="Account">
        <p className="text-xs text-zinc-500 dark:text-zinc-400">Checking your session…</p>
      </Card>
    );
  }

  if (me) {
    return (
      <Card
        title="Account"
        subtitle={me.user.email}
        action={
          <Button
            onClick={() => {
              void logout().then(refresh);
            }}
          >
            Sign out
          </Button>
        }
      >
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-3">
          {[
            ["Name", me.user.full_name ?? "—"],
            ["Email confirmed", me.user.email_verified ? "yes" : "no"],
            ["Workspaces", String(me.workspaces.length)],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
              <dd className="mt-0.5 font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      </Card>
    );
  }

  return (
    <Card
      title={mode === "register" ? "Create an account" : "Sign in"}
      subtitle="Phase 1.1 / M1 — sessions are httpOnly cookies, so no token is visible to page scripts"
      action={
        <Button onClick={() => setMode(mode === "register" ? "login" : "register")}>
          {mode === "register" ? "I have an account" : "Create one instead"}
        </Button>
      }
    >
      {error && <ErrorNote>{error}</ErrorNote>}

      {pendingToken && (
        <div className="mb-3 flex flex-col gap-2">
          <Note>
            Account created but not yet confirmed. In production this link arrives by
            email; locally the API hands it back so no mail server is needed.
          </Note>
          <div>
            <Button onClick={() => void confirm()} disabled={busy}>
              {busy ? "Confirming…" : "Confirm email address"}
            </Button>
          </div>
        </div>
      )}

      {!pendingToken && (
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <Field label="Email">
            <input
              id="auth-email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className={inputClass}
              placeholder="you@example.com"
            />
          </Field>

          <Field
            label="Password"
            hint={
              mode === "register"
                ? "At least 10 characters, mixed case, and a digit."
                : undefined
            }
          >
            <input
              id="auth-password"
              type="password"
              required
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className={inputClass}
            />
          </Field>

          {mode === "register" && (
            <>
              <Field label="Your name">
                <input
                  id="auth-name"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  className={inputClass}
                  placeholder="Ahsan Ali"
                />
              </Field>
              <Field label="First workspace" hint="Optional — you can create one later.">
                <input
                  id="auth-workspace"
                  value={workspaceName}
                  onChange={(event) => setWorkspaceName(event.target.value)}
                  className={inputClass}
                  placeholder="Northwind Supply"
                />
              </Field>
            </>
          )}

          <div>
            <Button onClick={() => void submit()} disabled={busy}>
              {busy ? "Working…" : mode === "register" ? "Create account" : "Sign in"}
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
