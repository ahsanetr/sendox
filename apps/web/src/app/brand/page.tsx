"use client";

import { ShopifyPanel } from "@/components/shopify-panel";
import { PageHeader } from "@/components/app/page-header";
import { Section } from "@/components/app/primitives";

export default function BrandPage() {
  return (
    <>
      <PageHeader
        title="Brand"
        description="Where your store connects, and where Sendox learns how you write."
      />
      <Section
        title="Shopify"
        description="Sendox reads your catalogue, customers and order history. It never writes to your store."
      >
        <ShopifyPanel />
      </Section>
    </>
  );
}
