import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** A row of figures.
 *
 *  Deliberately not cards: these are one reading of one thing, not separate
 *  objects, and boxing each in a bordered tile flattens the page that follows.
 *  They are set large because a number someone came here to read should not be
 *  the same size as the label explaining it.
 */
export function Figures({
  items,
}: {
  items: { label: string; value: string; hint?: string }[];
}) {
  return (
    <dl className="flex flex-wrap gap-x-14 gap-y-6">
      {items.map((item) => (
        <div key={item.label}>
          <dd className="tabular text-4xl font-medium tracking-[-0.02em]">{item.value}</dd>
          <dt className="mt-1.5 text-sm text-muted-foreground">{item.label}</dt>
          {item.hint && (
            <p className="mt-0.5 text-xs text-muted-foreground/70">{item.hint}</p>
          )}
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
  title?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="px-8 py-8">
      {(title || description || action) && (
        <div className="mb-5 flex flex-wrap items-baseline justify-between gap-3">
          <div>
            {title && (
              <h2 className="text-[0.9375rem] font-semibold tracking-tight">{title}</h2>
            )}
            {description && (
              <p className="mt-1 max-w-prose text-sm leading-relaxed text-muted-foreground">
                {description}
              </p>
            )}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

/** An empty screen is an invitation to act, so it always carries the action.
 *
 *  The icon is not decoration. A panel holding only two lines of grey text reads
 *  as a page that failed to load; a glyph says the emptiness is the state, and
 *  gives the eye something to land on before it reads.
 */
export function EmptyState({
  icon: Icon,
  headline,
  body,
  action,
}: {
  icon: LucideIcon;
  headline: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel flex flex-col items-center px-8 py-12 text-center">
      <div className="flex size-11 items-center justify-center rounded-full bg-primary/8 ring-1 ring-inset ring-primary/12">
        <Icon className="size-5 text-primary" aria-hidden strokeWidth={1.75} />
      </div>
      <p className="mt-4 text-sm font-semibold tracking-tight">{headline}</p>
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-muted-foreground">
        {body}
      </p>
      {action && <div className="mt-5">{action}</div>}
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
    positive: "bg-positive/12 text-positive",
    attention: "bg-attention/12 text-attention",
    critical: "bg-destructive/12 text-destructive",
    accent: "bg-primary/12 text-primary",
  } as const;
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-1 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/** The one button style, in two weights. Rounded to match controls, not panels. */
export function Button({
  variant = "primary",
  type = "button",
  onClick,
  disabled,
  children,
}: {
  variant?: "primary" | "quiet";
  type?: "button" | "submit";
  onClick?: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  const styles = {
    primary:
      "bg-primary text-primary-foreground hover:brightness-110 active:brightness-95",
    quiet:
      "bg-transparent text-foreground hover:bg-muted active:bg-secondary ring-1 ring-inset ring-border",
  } as const;
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex shrink-0 items-center justify-center cursor-pointer rounded-md px-3.5 py-2 text-sm font-medium transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-40 ${styles[variant]}`}
    >
      {children}
    </button>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <span className="font-mono text-xs text-muted-foreground">{children}</span>;
}

/** A table that reads as one surface, with hover instead of a rule per row. */
export function Table({
  columns,
  children,
}: {
  columns: { label: string; align?: "left" | "right" }[];
  children: ReactNode;
}) {
  return (
    <div className="panel overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border/70">
            {columns.map((column) => (
              <th
                key={column.label}
                className={`px-5 py-3.5 text-xs font-medium text-muted-foreground ${
                  column.align === "right" ? "text-right" : "text-left"
                }`}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/40">{children}</tbody>
      </table>
    </div>
  );
}
