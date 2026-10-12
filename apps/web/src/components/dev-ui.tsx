import type { ItemStatus, ProbeStatus } from "@/lib/api";

/* These started as throwaway chrome for the /dev page and drifted into Settings
 * and Brand, carrying a hardcoded zinc/sky/rose palette with them. That made
 * two design systems in one app: the token-driven one in components/app, and
 * this. Everything here now reads the same custom properties as the rest, so a
 * change of colour scheme reaches the whole product rather than half of it.
 *
 * Role and status colours are the one place raw hues survive, because they are
 * a legend — four roles the eye has to tell apart at a glance — rather than
 * brand colour. They are pinned to the chart ramp, which every scheme defines.
 */

const STATUS_STYLE: Record<ItemStatus | ProbeStatus, string> = {
  done: "bg-positive/10 text-positive ring-positive/20",
  ok: "bg-positive/10 text-positive ring-positive/20",
  partial: "bg-attention/10 text-attention ring-attention/20",
  in_progress: "bg-primary/10 text-primary ring-primary/20",
  planned: "bg-muted text-muted-foreground ring-border",
  error: "bg-destructive/10 text-destructive ring-destructive/20",
};

const STATUS_LABEL: Record<ItemStatus | ProbeStatus, string> = {
  done: "done",
  ok: "ok",
  partial: "partial",
  in_progress: "in progress",
  planned: "planned",
  error: "error",
};

export function Badge({ status }: { status: ItemStatus | ProbeStatus }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLE[status]}`}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

export function Dot({ status }: { status: ProbeStatus }) {
  const color = status === "ok" ? "bg-positive" : "bg-destructive";
  return (
    <span className="relative flex h-2.5 w-2.5 shrink-0">
      {status === "ok" && (
        <span
          className={`absolute inline-flex h-full w-full animate-ping rounded-full ${color} opacity-60`}
        />
      )}
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${color}`} />
    </span>
  );
}

export function Card({
  title,
  subtitle,
  action,
  children,
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
          {subtitle && (
            <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>
          )}
        </div>
        {action}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Button({
  onClick,
  disabled,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="cursor-pointer rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors duration-200 hover:brightness-110 active:brightness-95 disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-foreground">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-md border border-input bg-card px-2.5 py-1.5 text-sm text-foreground outline-none transition-colors duration-200 placeholder:text-muted-foreground/70 focus:border-ring focus:ring-2 focus:ring-ring/20 disabled:opacity-50";

export function Note({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-md bg-primary/10 px-3 py-2 text-xs text-primary ring-1 ring-inset ring-primary/20">
      {children}
    </p>
  );
}

export function RoleBadge({ role }: { role: string }) {
  // A legend, not brand colour: four roles that have to be distinguishable at a
  // glance, so they ride the chart ramp each scheme defines rather than fixed
  // hues that would clash with half of them.
  const tone: Record<string, string> = {
    owner: "bg-chart-5/12 text-chart-5 ring-chart-5/25",
    admin: "bg-chart-1/12 text-chart-1 ring-chart-1/25",
    editor: "bg-chart-2/12 text-chart-2 ring-chart-2/25",
    viewer: "bg-muted text-muted-foreground ring-border",
  };
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tone[role] ?? tone.viewer}`}
    >
      {role}
    </span>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive ring-1 ring-inset ring-destructive/20">
      {children}
    </p>
  );
}
