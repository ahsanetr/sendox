import type { ReactNode } from "react";

/** The bar at the top of every page: what you are looking at, and the one thing
 *  you are most likely to do to it.
 *
 *  No rule underneath — the canvas already separates it from the content below,
 *  and a line there is the kind of chrome that makes an interface feel older
 *  than it is. */
export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4 px-8 pt-10 pb-2">
      <div className="min-w-0">
        <h1 className="text-[1.75rem] font-semibold tracking-[-0.02em]">{title}</h1>
        {description && (
          <p className="mt-2 max-w-prose text-[0.9375rem] leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {action}
    </header>
  );
}
