"use client";

import Link from "next/link";

import { getImportedData } from "@/lib/api";
import { useSession } from "@/lib/session";
import { usePolledResource } from "@/lib/use-polled-resource";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, Figures, Pill, Section } from "@/components/app/primitives";

export default function ContactsPage() {
  const { activeWorkspace } = useSession();
  const { data } = usePolledResource(() =>
    activeWorkspace ? getImportedData(activeWorkspace.id) : Promise.resolve(null),
  );

  const contacts = data?.top_contacts ?? [];

  return (
    <>
      <PageHeader
        title="Contacts"
        description="Everyone who has bought from you or signed up, with what they have done."
      />

      <Section title="Overview">
        {contacts.length === 0 ? (
          <EmptyState
            headline="No contacts yet"
            body="Contacts arrive when you import your Shopify store."
            action={
              <Link
                href="/brand"
                className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition hover:brightness-110"
              >
                Import your store
              </Link>
            }
          />
        ) : (
          <>
            <Figures
              items={[
                { label: "Contacts", value: (data?.counts.contacts ?? 0).toLocaleString() },
                {
                  label: "Subscribed",
                  value: contacts.filter((c) => c.consent === "subscribed").length.toString(),
                  hint: "Only these can be emailed",
                },
                { label: "Events recorded", value: (data?.counts.events ?? 0).toLocaleString() },
              ]}
            />
            <div className="mt-6 overflow-x-auto rounded-lg border border-border bg-card">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="px-4 py-2.5 font-medium">Name</th>
                    <th className="px-4 py-2.5 font-medium">Email</th>
                    <th className="px-4 py-2.5 text-right font-medium">Orders</th>
                    <th className="px-4 py-2.5 text-right font-medium">Spent</th>
                    <th className="px-4 py-2.5 font-medium">Consent</th>
                  </tr>
                </thead>
                <tbody>
                  {contacts.map((contact) => (
                    <tr key={contact.email} className="border-b border-border last:border-0">
                      <td className="px-4 py-2.5">{contact.name ?? "—"}</td>
                      <td className="px-4 py-2.5 text-muted-foreground">{contact.email}</td>
                      <td className="tabular px-4 py-2.5 text-right">{contact.orders}</td>
                      <td className="tabular px-4 py-2.5 text-right">
                        {contact.spent.toFixed(2)}
                      </td>
                      <td className="px-4 py-2.5">
                        <Pill tone={contact.consent === "subscribed" ? "positive" : "neutral"}>
                          {contact.consent}
                        </Pill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Showing the ten highest-spending contacts. Full search, filtering and the
              per-contact timeline arrive with the rest of module 5.
            </p>
          </>
        )}
      </Section>
    </>
  );
}
