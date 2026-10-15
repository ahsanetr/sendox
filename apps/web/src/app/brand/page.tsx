"use client";

import { ShopifyPanel } from "@/components/shopify-panel";
import { BrandAnalysis } from "@/components/brand/brand-analysis";
import { OnboardingWizard } from "@/components/brand/onboarding-wizard";
import { PageInspector } from "@/components/brand/page-inspector";
import { PageHeader } from "@/components/app/page-header";
import { Section } from "@/components/app/primitives";

/** Everything Sendox knows about the brand, in the order it learns it.
 *
 *  The merchant's own answers come first and the crawl second, which is the
 *  same precedence the generator uses: when the storefront and the owner
 *  disagree about who the audience is, the owner wins.
 */
export default function BrandPage() {
  return (
    <>
      <PageHeader
        title="Brand"
        description="What Sendox knows about how you sell, and where it learned it."
      />

      <Section
        title="Your answers"
        description="Five questions. Every campaign Sendox writes is steered by them, so they are worth a few real sentences each."
      >
        <OnboardingWizard />
      </Section>

      <Section
        title="Shopify"
        description="Sendox reads your catalogue, customers and order history. It never writes to your store."
      >
        <ShopifyPanel />
      </Section>

      <Section
        title="What Sendox worked out"
        description="Read from your catalogue and storefront copy, not from your answers. Where the two disagree, that is shown rather than smoothed over."
      >
        <BrandAnalysis />
      </Section>

      <Section
        title="What Sendox read"
        description="Every page taken from your storefront, in full. If one of them does not represent you, exclude it and it will be left out the next time the site is indexed."
      >
        <PageInspector />
      </Section>
    </>
  );
}
