"use client";

import { AuthPanel } from "@/components/auth-panel";
import { WorkspacePanel } from "@/components/workspace-panel";
import { PageHeader } from "@/components/app/page-header";
import { Section } from "@/components/app/primitives";

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="Settings"
        description="Your account, your workspaces, and who else can get in."
      />
      <Section title="Account">
        <AuthPanel />
      </Section>
      <Section title="Workspaces and team">
        <WorkspacePanel />
      </Section>
    </>
  );
}
