"use client";

import { Users } from "lucide-react";
import Link from "next/link";

import { getImportedData } from "@/lib/api";
import { useSession } from "@/lib/session";
import { usePolledResource } from "@/lib/use-polled-resource";
import { PageHeader } from "@/components/app/page-header";
import { Button, EmptyState, Figures, Pill, Section, Table } from "@/components/app/primitives";

export default function ContactsPage() {
  const { activeWorkspace } = useSession();
  const { data } = usePolledResource(
    () => (activeWorkspace ? getImportedData(activeWorkspace.id) : Promise.resolve(null)),
    undefined,
    [activeWorkspace?.id],
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
            icon={Users}
            headline="No contacts yet"
            body="Contacts arrive when you import your Shopify store."
            action={
              <Link href="/brand">
                <Button>Import your store</Button>
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
            <div className="mt-8">
              <Table
                columns={[
                  { label: "Name" },
                  { label: "Email" },
                  { label: "Orders", align: "right" },
                  { label: "Spent", align: "right" },
                  { label: "Marketing" },
                ]}
              >
                {contacts.map((contact) => (
                  <tr key={contact.email} className="row-hover">
                    <td className="px-5 py-3.5 font-medium">{contact.name ?? "—"}</td>
                    <td className="px-5 py-3.5 text-muted-foreground">{contact.email}</td>
                    <td className="tabular px-5 py-3.5 text-right">{contact.orders}</td>
                    <td className="tabular px-5 py-3.5 text-right">{contact.spent.toFixed(2)}</td>
                    <td className="px-5 py-3.5">
                      <Pill tone={contact.consent === "subscribed" ? "positive" : "neutral"}>
                        {contact.consent}
                      </Pill>
                    </td>
                  </tr>
                ))}
              </Table>
            </div>
            <p className="mt-4 text-xs text-muted-foreground">
              Showing the ten highest-spending contacts. Full search, filtering and the
              per-contact timeline arrive with the rest of module 5.
            </p>
          </>
        )}
      </Section>
    </>
  );
}
