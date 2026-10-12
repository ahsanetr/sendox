"use client";

import { getBuildStatus, type StatusItem } from "@/lib/api";
import { usePolledResource } from "@/lib/use-polled-resource";
import { Badge, Card, ErrorNote } from "@/components/dev-ui";

function ItemRow({ item }: { item: StatusItem }) {
  const dimmed = item.status === "planned";
  return (
    <li
      className={`flex flex-wrap items-baseline gap-x-2 gap-y-1 py-2 ${dimmed ? "opacity-60" : ""}`}
    >
      <span className="w-10 shrink-0 font-mono text-xs text-muted-foreground">
        {item.id}
      </span>
      <span className="min-w-0 flex-1 text-sm">{item.name}</span>
      {item.phase && (
        <span className="font-mono text-xs text-muted-foreground/70">
          {item.phase}
        </span>
      )}
      <Badge status={item.status} />
      {item.note && (
        <p className="w-full pl-10 text-xs text-muted-foreground">
          {item.note}
        </p>
      )}
    </li>
  );
}

export function BuildStatusPanel() {
  const { data, error } = usePolledResource(getBuildStatus);

  if (error) {
    return (
      <Card title="Build status">
        <ErrorNote>{error}</ErrorNote>
      </Card>
    );
  }

  if (!data) {
    return (
      <Card title="Build status">
        <p className="text-xs text-muted-foreground">Loading…</p>
      </Card>
    );
  }

  const done = data.totals.done ?? 0;
  const partial = data.totals.partial ?? 0;
  const total = data.totals.items;

  return (
    <Card
      title="Build status"
      subtitle={`${done} done · ${partial} partial · ${total - done - partial} planned, across ${total} items`}
    >
      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-positive"
          style={{ width: `${(done / total) * 100}%` }}
        />
      </div>

      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        R0 — Foundation
      </h3>
      <ul className="divide-y divide-border">
        {data.foundation.map((item) => (
          <ItemRow key={item.id} item={item} />
        ))}
      </ul>

      {data.releases
        .filter((release) => release.id !== "R0")
        .map((release) => {
          const items = data.modules.filter((m) => m.release === release.id);
          if (items.length === 0) return null;
          return (
            <div key={release.id} className="mt-6">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {release.id} — {release.title}
                <span className="ml-2 font-normal normal-case text-muted-foreground/70">
                  {release.window}
                </span>
              </h3>
              <ul className="divide-y divide-border">
                {items.map((item) => (
                  <ItemRow key={item.id} item={item} />
                ))}
              </ul>
            </div>
          );
        })}

      <p className="mt-5 border-t border-border pt-3 text-xs text-muted-foreground dark:text-muted-foreground/70">
        {data.note}
      </p>
    </Card>
  );
}
