import type { ItemStatus, ProbeStatus } from "@/lib/api";

const STATUS_STYLE: Record<ItemStatus | ProbeStatus, string> = {
  done: "bg-emerald-500/10 text-emerald-700 ring-emerald-600/20 dark:text-emerald-400",
  ok: "bg-emerald-500/10 text-emerald-700 ring-emerald-600/20 dark:text-emerald-400",
  partial: "bg-amber-500/10 text-amber-700 ring-amber-600/20 dark:text-amber-400",
  in_progress:
    "bg-sky-500/10 text-sky-700 ring-sky-600/20 dark:text-sky-400",
  planned: "bg-zinc-500/10 text-zinc-600 ring-zinc-500/20 dark:text-zinc-400",
  error: "bg-rose-500/10 text-rose-700 ring-rose-600/20 dark:text-rose-400",
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
  const color = status === "ok" ? "bg-emerald-500" : "bg-rose-500";
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
    <section className="rounded-xl border border-zinc-200 bg-white/60 dark:border-zinc-800 dark:bg-zinc-900/40">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
          {subtitle && (
            <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
              {subtitle}
            </p>
          )}
        </div>
        {action}
      </header>
      <div className="p-4">{children}</div>
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
      className="rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
    >
      {children}
    </button>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-md bg-rose-500/10 px-3 py-2 text-xs text-rose-700 ring-1 ring-inset ring-rose-600/20 dark:text-rose-400">
      {children}
    </p>
  );
}
