"use client";

import { useState } from "react";

import { login, register, verifyEmail } from "@/lib/api";
import { useSession } from "@/lib/session";

type Mode = "signin" | "signup";

export function SignInScreen() {
  const { refresh } = useSession();
  const [mode, setMode] = useState<Mode>("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") {
        const created = await register({
          email,
          password,
          full_name: fullName || undefined,
          workspace_name: workspaceName || undefined,
        });
        setPendingToken(created.dev_verification_token);
      } else {
        await login(email, password);
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
    try {
      await verifyEmail(pendingToken);
      setPendingToken(null);
      refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-2">
      {/* The dark half states what the product does, in its own words, so the
          first screen is an argument rather than a form with a logo above it. */}
      <div className="hidden flex-col justify-between bg-sidebar p-10 lg:flex">
        <p className="text-base font-semibold text-white">Sendox</p>
        <div className="max-w-md">
          <p className="text-2xl leading-snug font-medium text-white">
            Your email marketing, written and scheduled for you.
          </p>
          <p className="mt-4 text-sm leading-relaxed text-sidebar-foreground">
            Connect your Shopify store and Sendox learns how your brand writes, plans
            the campaigns worth sending, drafts them, and waits for your approval.
          </p>
        </div>
        <p className="text-xs text-sidebar-foreground/70">
          Final year project · COMSATS University Islamabad
        </p>
      </div>

      <div className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-sm">
          <h1 className="text-xl font-semibold tracking-tight">
            {mode === "signup" ? "Create your account" : "Sign in"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {mode === "signup"
              ? "You will need a Shopify store to connect afterwards."
              : "Welcome back."}
          </p>

          {error && (
            <p className="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </p>
          )}

          {pendingToken ? (
            <div className="mt-6">
              <p className="text-sm text-muted-foreground">
                Account created. Confirm your email address to finish — in production
                this arrives as a link; locally the API hands it straight back.
              </p>
              <button
                type="button"
                onClick={() => void confirm()}
                disabled={busy}
                className="mt-4 w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition hover:brightness-110 disabled:opacity-50"
              >
                {busy ? "Confirming…" : "Confirm email address"}
              </button>
            </div>
          ) : (
            <form
              className="mt-6 flex flex-col gap-4"
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
            >
              <Labelled label="Email">
                <input
                  id="signin-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className={FIELD}
                  placeholder="you@yourbrand.com"
                />
              </Labelled>

              <Labelled
                label="Password"
                hint={mode === "signup" ? "At least 10 characters, mixed case, a digit." : undefined}
              >
                <input
                  id="signin-password"
                  type="password"
                  required
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className={FIELD}
                />
              </Labelled>

              {mode === "signup" && (
                <>
                  <Labelled label="Your name">
                    <input
                      id="signin-name"
                      value={fullName}
                      onChange={(event) => setFullName(event.target.value)}
                      className={FIELD}
                      placeholder="Ahsan Ali"
                    />
                  </Labelled>
                  <Labelled label="Brand name" hint="This becomes your first workspace.">
                    <input
                      id="signin-workspace"
                      value={workspaceName}
                      onChange={(event) => setWorkspaceName(event.target.value)}
                      className={FIELD}
                      placeholder="Northwind Supply"
                    />
                  </Labelled>
                </>
              )}

              <button
                type="submit"
                disabled={busy}
                className="mt-1 w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition hover:brightness-110 disabled:opacity-50"
              >
                {busy ? "Working…" : mode === "signup" ? "Create account" : "Sign in"}
              </button>
            </form>
          )}

          <p className="mt-6 text-sm text-muted-foreground">
            {mode === "signup" ? "Already have an account?" : "New to Sendox?"}{" "}
            <button
              type="button"
              onClick={() => {
                setMode(mode === "signup" ? "signin" : "signup");
                setPendingToken(null);
                setError(null);
              }}
              className="font-medium text-primary hover:underline"
            >
              {mode === "signup" ? "Sign in" : "Create an account"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

const FIELD =
  "w-full rounded-md border border-input bg-card px-3 py-2 text-sm outline-none transition focus:border-ring focus:ring-2 focus:ring-ring/20";

function Labelled({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}
