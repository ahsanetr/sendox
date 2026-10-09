"use client";

import { PageHeader } from "@/components/app/page-header";
import { EmptyState, Section } from "@/components/app/primitives";

export default function CampaignsPage() {
  return (
    <>
      <PageHeader
        title="Campaigns"
        description="One-off sends: a launch, a sale, a newsletter."
      />
      <Section title="Not built yet">
        <EmptyState
          headline="Campaigns arrive in a later release"
          body="The campaign engine is scheduled for the release after this one. Until then, connect your store so Sendox has something to write about."
        />
      </Section>
    </>
  );
}
