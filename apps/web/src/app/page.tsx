"use client";

import { Building2, CheckCheck, DownloadCloud, Sparkles, Store } from "lucide-react";
import Link from "next/link";

import { getBrandProfile, getImportedData, getShopifyStatus } from "@/lib/api";
import { useSession } from "@/lib/session";
import { usePolledResource } from "@/lib/use-polled-resource";
import { PageHeader } from "@/components/app/page-header";
import { Button, EmptyState, Figures, Pill, Section, Table } from "@/components/app/primitives";

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
    <Section>
      <EmptyState
        icon={Building2}
        headline="Create a workspace to begin"
        body="A workspace holds one brand: its store, its contacts, and everything Sendox writes for it."
        action={
          <Link href="/settings">
            <Button>Create a workspace</Button>
          </Link>
        }
      />
    </Section>
  );
}

function Overview({ workspaceId }: { workspaceId: string }) {
  const { data: shopify } = usePolledResource(
    () => getShopifyStatus(workspaceId),
    undefined,
    [workspaceId],
  );
  const { data } = usePolledResource(
    () => getImportedData(workspaceId),
    undefined,
    [workspaceId],
  );
  const { data: brand } = usePolledResource(
    () => getBrandProfile(workspaceId),
    undefined,
    [workspaceId],
  );

  const connected = (shopify?.stores ?? []).filter((store) => store.connected);
  const counts = data?.counts;
  // Anything at all having arrived, not contacts specifically. Shopify gates
  // customers and orders behind an approval many stores do not have, so a
  // perfectly successful import can land products and nothing else — and
  // keying off contacts told those stores to import again, forever.
  const imported = (counts?.products ?? 0) + (counts?.contacts ?? 0) > 0;

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
            icon={Store}
            headline="Connect your Shopify store"
            body="Sendox reads your products, customers and order history to learn how your brand sells before it writes anything."
            action={
              <Link href="/brand">
                <Button>Connect a store</Button>
              </Link>
            }
          />
        ) : counts && !imported ? (
          <EmptyState
            icon={DownloadCloud}
            headline="Import your store data"
            body="Your store is connected. Bring in customers, orders and products so Sendox has something to work from."
            action={
              <Link href="/brand">
                <Button>Go to Brand</Button>
              </Link>
            }
          />
        ) : (
          <EmptyState
            icon={CheckCheck}
            headline="Nothing needs you right now"
            body="Campaign planning arrives in a later release. When Sendox drafts something, it will appear here for approval before anything is sent."
          />
        )}
      </Section>

      {/* What the brand profile says, on the page people actually open. The
          answers steer every generation, so "is it set and what does it say"
          should not require remembering which screen holds it. */}
      {brand && (
        <Section
          title="What Sendox knows about you"
          description="Your onboarding answers. Every campaign is written against them."
          action={
            <Link href="/brand">
              <Button variant="quiet">
                {brand.complete ? "Review answers" : "Finish setup"}
              </Button>
            </Link>
          }
        >
          {brand.complete ? (
            <dl className="panel divide-y divide-border/60">
              {[
                ["Sells", brand.what_you_sell],
                ["Audience", brand.audience],
                ["Voice", brand.tone],
              ].map(([label, value]) => (
                <div key={label} className="px-5 py-3.5">
                  <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
                  <dd className="mt-0.5 line-clamp-2 text-sm leading-relaxed">
                    {value ?? "—"}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <EmptyState
              icon={Sparkles}
              headline="Sendox does not know your brand yet"
              body="Five questions about what you sell and how you write. They steer every campaign, so they are worth a few real sentences each."
              action={
                <Link href="/brand">
                  <Button>Answer them</Button>
                </Link>
              }
            />
          )}
        </Section>
      )}

      {counts && imported && (
        <Section title="Your store" description="Imported from Shopify.">
          <Figures
            items={[
              { label: "Contacts", value: counts.contacts.toLocaleString() },
              { label: "Recorded events", value: counts.events.toLocaleString() },
              { label: "Products", value: counts.products.toLocaleString() },
            ]}
          />

          {data && data.top_contacts.length > 0 && (
            <div className="mt-8">
              <Table
                columns={[
                  { label: "Customer" },
                  { label: "Email" },
                  { label: "Orders", align: "right" },
                  { label: "Spent", align: "right" },
                  { label: "Marketing" },
                ]}
              >
                {data.top_contacts.map((contact) => (
                  <tr key={contact.email} className="row-hover">
                    <td className="px-5 py-3.5 font-medium">{contact.name ?? "—"}</td>
                    <td className="px-5 py-3.5 text-muted-foreground">{contact.email}</td>
                    <td className="tabular px-5 py-3.5 text-right">{contact.orders}</td>
                    <td className="tabular px-5 py-3.5 text-right">
                      {contact.spent.toFixed(2)}
                    </td>
                    <td className="px-5 py-3.5">
                      <Pill tone={contact.consent === "subscribed" ? "positive" : "neutral"}>
                        {contact.consent === "subscribed" ? "Subscribed" : contact.consent}
                      </Pill>
                    </td>
                  </tr>
                ))}
              </Table>
            </div>
          )}
        </Section>
      )}
    </>
  );
}
