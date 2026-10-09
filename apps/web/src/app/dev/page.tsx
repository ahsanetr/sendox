"use client";

import { AiStatus } from "@/components/dev/ai-status";
import { BrandKnowledge } from "@/components/dev/brand-knowledge";
import { BuildStatusPanel } from "@/components/dev/build-status";
import { CapabilityChecks } from "@/components/dev/capability-checks";
import { DatabaseStatus } from "@/components/dev/database-status";
import { ServiceHealth } from "@/components/dev/service-health";
import { PageHeader } from "@/components/app/page-header";

/** The developer dashboard, kept out of the product.
 *
 *  It is reachable without signing in on purpose: it is how you check whether
 *  the platform is up, which matters most when it is not.
 */
export default function SystemPage() {
  return (
    <main className="mx-auto w-full max-w-3xl">
      <PageHeader
        title="System"
        description="What is wired up and working, read from the running backend. Internal — not part of the product."
      />
      <div className="space-y-5 px-6 py-6">
        <ServiceHealth />
        <DatabaseStatus />
        <CapabilityChecks />
        <BrandKnowledge />
        <AiStatus />
        <BuildStatusPanel />
      </div>
    </main>
  );
}
