"use client";

import { getBuildStatus, type StatusItem } from "@/lib/api";
import { usePolledResource } from "@/lib/use-polled-resource";
import { Badge, Card, ErrorNote } from "@/components/ui";

function ItemRow({ item }: { item: StatusItem }) {
  const dimmed = item.status === "planned";
  return (
    <li
      className={`flex flex-wrap items-baseline gap-x-2 gap-y-1 py-2 ${dimmed ? "opacity-60" : ""}`}
    >
      <span className="w-10 shrink-0 font-mono text-xs text-zinc-500 dark:text-zinc-400">
        {item.id}
      </span>
      <span className="min-w-0 flex-1 text-sm">{item.name}</span>
      {item.phase && (
        <span className="font-mono text-xs text-zinc-400 dark:text-zinc-500">
          {item.phase}
        </span>
      )}
      <Badge status={item.status} />
      {item.note && (
        <p className="w-full pl-10 text-xs text-zinc-500 dark:text-zinc-400">
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
        <p className="text-xs text-zinc-500 dark:text-zinc-400">Loading…</p>
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
      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div
          className="h-full bg-emerald-500"
          style={{ width: `${(done / total) * 100}%` }}
        />
      </div>

      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        R0 — Foundation
      </h3>
      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
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
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                {release.id} — {release.title}
                <span className="ml-2 font-normal normal-case text-zinc-400 dark:text-zinc-500">
                  {release.window}
                </span>
              </h3>
              <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {items.map((item) => (
                  <ItemRow key={item.id} item={item} />
                ))}
              </ul>
            </div>
          );
        })}

      <p className="mt-5 border-t border-zinc-200 pt-3 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
        {data.note}
      </p>
    </Card>
  );
}
