"use client";

import Link from "next/link";

import { getImportedData, getShopifyStatus } from "@/lib/api";
import { useSession } from "@/lib/session";
import { usePolledResource } from "@/lib/use-polled-resource";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, Figures, Pill, Section } from "@/components/app/primitives";

export default function HomePage() {
  const { activeWorkspace } = useSession();

  return (
    <>
      <PageHeader
        title={activeWorkspace?.name ?? "Home"}
        description="What Sendox is waiting on, and what it has done for you."
      />
      {activeWorkspace ? <Overview workspaceId={activeWorkspace.id} /> : <NoWorkspace />}
    </>
  );
}

function NoWorkspace() {
  return (
    <Section title="No workspace yet">
      <EmptyState
        headline="Create a workspace to begin"
        body="A workspace holds one brand: its store, its contacts, and everything Sendox writes for it."
        action={
          <Link
            href="/settings"
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
          >
            Create a workspace
          </Link>
        }
      />
    </Section>
  );
}

function Overview({ workspaceId }: { workspaceId: string }) {
  const { data: shopify } = usePolledResource(() => getShopifyStatus(workspaceId));
  const { data } = usePolledResource(() => getImportedData(workspaceId));

  const connected = (shopify?.stores ?? []).filter((store) => store.connected);
  const counts = data?.counts;

  return (
    <>
      {/* The product's thesis is that it proposes work and waits for judgement,
          so the page opens with what is waiting rather than with metrics. */}
      <Section
        title="Waiting on you"
        description="Nothing is sent without your approval."
      >
        {connected.length === 0 ? (
          <EmptyState
            headline="Connect your Shopify store"
            body="Sendox reads your products, customers and order history to learn how your brand sells before it writes anything."
            action={
              <Link
                href="/brand"
                className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition hover:brightness-110"
              >
                Connect a store
              </Link>
            }
          />
        ) : counts && counts.contacts === 0 ? (
          <EmptyState
            headline="Import your store data"
            body="Your store is connected. Bring in customers, orders and products so Sendox has something to work from."
            action={
              <Link
                href="/brand"
                className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition hover:brightness-110"
              >
                Go to Brand
              </Link>
            }
          />
        ) : (
          <EmptyState
            headline="Nothing needs you right now"
            body="Campaign planning arrives in a later release. When Sendox drafts something, it will appear here for approval before anything is sent."
          />
        )}
      </Section>

      {counts && counts.contacts > 0 && (
        <Section title="Your store" description="Imported from Shopify.">
          <Figures
            items={[
              { label: "Contacts", value: counts.contacts.toLocaleString() },
              { label: "Recorded events", value: counts.events.toLocaleString() },
              { label: "Products", value: counts.products.toLocaleString() },
            ]}
          />

          {data && data.top_contacts.length > 0 && (
            <div className="mt-6 overflow-x-auto rounded-lg border border-border bg-card">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="px-4 py-2.5 font-medium">Customer</th>
                    <th className="px-4 py-2.5 font-medium">Email</th>
                    <th className="px-4 py-2.5 text-right font-medium">Orders</th>
                    <th className="px-4 py-2.5 text-right font-medium">Spent</th>
                    <th className="px-4 py-2.5 font-medium">Email</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_contacts.map((contact) => (
                    <tr key={contact.email} className="border-b border-border last:border-0">
                      <td className="px-4 py-2.5">{contact.name ?? "—"}</td>
                      <td className="px-4 py-2.5 text-muted-foreground">{contact.email}</td>
                      <td className="tabular px-4 py-2.5 text-right">{contact.orders}</td>
                      <td className="tabular px-4 py-2.5 text-right">
                        {contact.spent.toFixed(2)}
                      </td>
                      <td className="px-4 py-2.5">
                        <Pill tone={contact.consent === "subscribed" ? "positive" : "neutral"}>
                          {contact.consent === "subscribed" ? "Subscribed" : contact.consent}
                        </Pill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      )}
    </>
  );
}
