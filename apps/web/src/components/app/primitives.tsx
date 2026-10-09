import type { ReactNode } from "react";

/** A row of plain figures.
 *
 *  Deliberately not cards: these are one reading of one thing, not separate
 *  objects, and boxing each in its own bordered tile flattens the hierarchy of
 *  the page that follows.
 */
export function Figures({
  items,
}: {
  items: { label: string; value: string; hint?: string }[];
}) {
  return (
    <dl className="flex flex-wrap gap-x-10 gap-y-4">
      {items.map((item) => (
        <div key={item.label}>
          <dd className="tabular text-2xl font-medium tracking-tight">{item.value}</dd>
          <dt className="mt-0.5 text-sm text-muted-foreground">{item.label}</dt>
          {item.hint && <p className="text-xs text-muted-foreground/80">{item.hint}</p>}
        </div>
      ))}
    </dl>
  );
}

export function Section({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="px-6 py-6">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
          {description && (
            <p className="mt-0.5 max-w-prose text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

/** An empty screen is an invitation to act, so it always carries the action. */
export function EmptyState({
  headline,
  body,
  action,
}: {
  headline: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
      <p className="text-sm font-medium">{headline}</p>
      <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">{body}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function Pill({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "positive" | "attention" | "critical" | "accent";
  children: ReactNode;
}) {
  const tones = {
    neutral: "bg-muted text-muted-foreground",
    positive: "bg-positive/10 text-positive",
    attention: "bg-attention/10 text-attention",
    critical: "bg-destructive/10 text-destructive",
    accent: "bg-primary/10 text-primary",
  } as const;
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono text-xs text-muted-foreground">{children}</span>;
}
