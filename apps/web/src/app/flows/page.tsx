"use client";

import { PageHeader } from "@/components/app/page-header";
import { EmptyState, Section } from "@/components/app/primitives";

export default function FlowsPage() {
  return (
    <>
      <PageHeader
        title="Flows"
        description="Sequences that run themselves when a customer does something."
      />
      <Section title="Not built yet">
        <EmptyState
          headline="Flows arrive in a later release"
          body="Abandoned cart, welcome and post-purchase sequences are scheduled for the next release."
        />
      </Section>
    </>
  );
}
