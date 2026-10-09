"use client";

import { useCallback, useEffect, useState } from "react";

import {
  acceptInvitation,
  createWorkspace,
  getAudit,
  getInvitations,
  getMembers,
  inviteMember,
  removeMember,
  setMemberRole,
  updateWorkspace,
  type AuditEntry,
  type Invitation,
  type Member,
  type MemberRole,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import {
  Button,
  Card,
  ErrorNote,
  Field,
  Note,
  RoleBadge,
  inputClass,
} from "@/components/dev-ui";

const ASSIGNABLE: MemberRole[] = ["viewer", "editor", "admin", "owner"];

const RANK: Record<MemberRole, number> = { viewer: 0, editor: 1, admin: 2, owner: 3 };

function canManageMembers(role: MemberRole | null): boolean {
  return role !== null && RANK[role] >= RANK.admin;
}

export function WorkspacePanel() {
  const { me, activeWorkspace, activeWorkspaceId, setActiveWorkspaceId, role, refresh } =
    useSession();

  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [audit, setAudit] = useState<AuditEntry[] | null>(null);
  const [newName, setNewName] = useState("");
  const [renameTo, setRenameTo] = useState("");
  const [timezoneTo, setTimezoneTo] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<MemberRole>("viewer");
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [joinToken, setJoinToken] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(async (workspaceId: string, currentRole: MemberRole | null) => {
    setError(null);
    try {
      setMembers(await getMembers(workspaceId));
      // Invitations and the audit log are admin-only; asking as a viewer would
      // just produce a 403 the user did not cause.
      if (canManageMembers(currentRole)) {
        setInvitations(await getInvitations(workspaceId));
        setAudit(await getAudit(workspaceId));
      } else {
        setInvitations([]);
        setAudit(null);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, []);

  useEffect(() => {
    const id = activeWorkspaceId;
    const currentRole = role;
    // Deferred to the next tick so the effect itself never calls setState during
    // its synchronous phase, which is what react-hooks/set-state-in-effect guards.
    const timer = setTimeout(() => {
      if (!id) {
        setMembers([]);
        setInvitations([]);
        setAudit(null);
        return;
      }
      void loadDetail(id, currentRole);
    }, 0);
    return () => clearTimeout(timer);
  }, [activeWorkspaceId, role, loadDetail]);

  async function run(label: string, action: () => Promise<unknown>) {
    setBusy(label);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(null);
    }
  }

  if (!me) {
    return (
      <Card title="Workspaces">
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Sign in to create and manage workspaces.
        </p>
      </Card>
    );
  }

  const manage = canManageMembers(role);

  return (
    <>
      <Card
        title="Workspaces"
        subtitle="Each workspace is a brand. Its data is isolated inside Postgres, not by application code."
      >
        {error && <ErrorNote>{error}</ErrorNote>}

        {me.workspaces.length === 0 ? (
          <Note>No workspaces yet. Create one below to get started.</Note>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {me.workspaces.map((workspace) => {
              const selected = workspace.id === activeWorkspaceId;
              return (
                <li key={workspace.id}>
                  <button
                    type="button"
                    onClick={() => setActiveWorkspaceId(workspace.id)}
                    aria-pressed={selected}
                    className={`flex w-full flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-left transition ${
                      selected
                        ? "border-zinc-900 dark:border-zinc-100"
                        : "border-zinc-200 hover:border-zinc-400 dark:border-zinc-800 dark:hover:border-zinc-600"
                    }`}
                  >
                    <span className="text-sm font-medium">{workspace.name}</span>
                    <span className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
                      {workspace.slug}
                    </span>
                    <span className="ml-auto flex items-center gap-2">
                      <span className="font-mono text-xs text-zinc-400 dark:text-zinc-500">
                        {workspace.timezone}
                      </span>
                      <RoleBadge role={workspace.role} />
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        <form
          className="mt-4 flex flex-wrap items-end gap-2 border-t border-zinc-200 pt-4 dark:border-zinc-800"
          onSubmit={(event) => {
            event.preventDefault();
            void run("create", async () => {
              const created = await createWorkspace(newName);
              setNewName("");
              refresh();
              setActiveWorkspaceId(created.id);
            });
          }}
        >
          <div className="min-w-48 flex-1">
            <Field label="New workspace">
              <input
                id="workspace-new"
                required
                minLength={2}
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                className={inputClass}
                placeholder="Second Brand"
              />
            </Field>
          </div>
          <Button
            onClick={() =>
              void run("create", async () => {
                const created = await createWorkspace(newName);
                setNewName("");
                refresh();
                setActiveWorkspaceId(created.id);
              })
            }
            disabled={busy !== null || newName.trim().length < 2}
          >
            {busy === "create" ? "Creating…" : "Create"}
          </Button>
        </form>

        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void run("join", async () => {
              const joined = await acceptInvitation(joinToken.trim());
              setJoinToken("");
              refresh();
              setActiveWorkspaceId(joined.workspace.id);
            });
          }}
        >
          <div className="min-w-48 flex-1">
            <Field
              label="Join with an invitation token"
              hint="Paste the token an admin generated. It only works for your own address."
            >
              <input
                id="workspace-join"
                value={joinToken}
                onChange={(event) => setJoinToken(event.target.value)}
                className={inputClass}
                placeholder="token from the invitation email"
              />
            </Field>
          </div>
          <Button
            onClick={() =>
              void run("join", async () => {
                const joined = await acceptInvitation(joinToken.trim());
                setJoinToken("");
                refresh();
                setActiveWorkspaceId(joined.workspace.id);
              })
            }
            disabled={busy !== null || joinToken.trim().length < 10}
          >
            {busy === "join" ? "Joining…" : "Join"}
          </Button>
        </form>
      </Card>

      {activeWorkspace && (
        <Card
          title="Workspace settings"
          subtitle={
            manage
              ? "Name and timezone. Changes are written to the activity log."
              : "Only owners and admins can change these."
          }
        >
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              void run("rename", async () => {
                await updateWorkspace(activeWorkspace.id, {
                  name: renameTo.trim() || undefined,
                  timezone: timezoneTo.trim() || undefined,
                });
                setRenameTo("");
                setTimezoneTo("");
                refresh();
                await loadDetail(activeWorkspace.id, role);
              });
            }}
          >
            <div className="min-w-44 flex-1">
              <Field label="Name" hint={`Currently "${activeWorkspace.name}"`}>
                <input
                  id="workspace-rename"
                  value={renameTo}
                  onChange={(event) => setRenameTo(event.target.value)}
                  className={inputClass}
                  disabled={!manage}
                  placeholder={activeWorkspace.name}
                />
              </Field>
            </div>
            <div className="min-w-36">
              <Field label="Timezone" hint={`Currently ${activeWorkspace.timezone}`}>
                <input
                  id="workspace-timezone"
                  value={timezoneTo}
                  onChange={(event) => setTimezoneTo(event.target.value)}
                  className={inputClass}
                  disabled={!manage}
                  placeholder="Asia/Karachi"
                />
              </Field>
            </div>
            <Button
              onClick={() =>
                void run("rename", async () => {
                  await updateWorkspace(activeWorkspace.id, {
                    name: renameTo.trim() || undefined,
                    timezone: timezoneTo.trim() || undefined,
                  });
                  setRenameTo("");
                  setTimezoneTo("");
                  refresh();
                  await loadDetail(activeWorkspace.id, role);
                })
              }
              disabled={
                busy !== null || !manage || (!renameTo.trim() && !timezoneTo.trim())
              }
            >
              {busy === "rename" ? "Saving…" : "Save"}
            </Button>
          </form>
        </Card>
      )}

      {activeWorkspace && (
        <Card
          title={`Members — ${activeWorkspace.name}`}
          subtitle={
            manage
              ? "You can invite people and change roles here."
              : `You are ${role} in this workspace, so management actions are hidden.`
          }
          action={<RoleBadge role={activeWorkspace.role} />}
        >
          <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
            {members.map((member) => (
              <li key={member.user_id} className="flex flex-wrap items-center gap-2 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm">
                    {member.full_name ?? member.email ?? member.user_id}
                  </span>
                  {member.full_name && member.email && (
                    <span className="block truncate text-xs text-zinc-500 dark:text-zinc-400">
                      {member.email}
                    </span>
                  )}
                </span>

                {manage ? (
                  <select
                    id={`role-${member.user_id}`}
                    value={member.role}
                    onChange={(event) =>
                      void run(`role-${member.user_id}`, async () => {
                        await setMemberRole(
                          activeWorkspace.id,
                          member.user_id,
                          event.target.value as MemberRole,
                        );
                        await loadDetail(activeWorkspace.id, role);
                        refresh();
                      })
                    }
                    className="rounded-md border border-zinc-300 bg-transparent px-2 py-1 text-xs dark:border-zinc-700"
                  >
                    {ASSIGNABLE.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : (
                  <RoleBadge role={member.role} />
                )}

                {manage && (
                  <Button
                    onClick={() =>
                      void run(`remove-${member.user_id}`, async () => {
                        await removeMember(activeWorkspace.id, member.user_id);
                        await loadDetail(activeWorkspace.id, role);
                        refresh();
                      })
                    }
                    disabled={busy !== null}
                  >
                    Remove
                  </Button>
                )}
              </li>
            ))}
          </ul>

          {manage && (
            <>
              <form
                className="mt-4 flex flex-wrap items-end gap-2 border-t border-zinc-200 pt-4 dark:border-zinc-800"
                onSubmit={(event) => {
                  event.preventDefault();
                  void run("invite", async () => {
                    const created = await inviteMember(
                      activeWorkspace.id,
                      inviteEmail,
                      inviteRole,
                    );
                    setInviteToken(created.dev_invitation_token);
                    setInviteEmail("");
                    await loadDetail(activeWorkspace.id, role);
                  });
                }}
              >
                <div className="min-w-48 flex-1">
                  <Field label="Invite by email">
                    <input
                      id="invite-email"
                      type="email"
                      required
                      value={inviteEmail}
                      onChange={(event) => setInviteEmail(event.target.value)}
                      className={inputClass}
                      placeholder="teammate@example.com"
                    />
                  </Field>
                </div>
                <Field label="Role">
                  <select
                    id="invite-role"
                    value={inviteRole}
                    onChange={(event) => setInviteRole(event.target.value as MemberRole)}
                    className="rounded-md border border-zinc-300 bg-transparent px-2 py-1.5 text-sm dark:border-zinc-700"
                  >
                    {ASSIGNABLE.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </Field>
                <Button
                  onClick={() =>
                    void run("invite", async () => {
                      const created = await inviteMember(
                        activeWorkspace.id,
                        inviteEmail,
                        inviteRole,
                      );
                      setInviteToken(created.dev_invitation_token);
                      setInviteEmail("");
                      await loadDetail(activeWorkspace.id, role);
                    })
                  }
                  disabled={busy !== null || !inviteEmail.includes("@")}
                >
                  {busy === "invite" ? "Inviting…" : "Invite"}
                </Button>
              </form>

              {inviteToken && (
                <div className="mt-3">
                  <Note>
                    Invitation token (development only — normally this arrives by email):
                    <code className="mt-1 block break-all font-mono text-xs">
                      {inviteToken}
                    </code>
                  </Note>
                </div>
              )}

              {invitations.length > 0 && (
                <div className="mt-4">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                    Pending invitations
                  </h3>
                  <ul className="mt-1.5 divide-y divide-zinc-200 dark:divide-zinc-800">
                    {invitations.map((invitation) => (
                      <li
                        key={invitation.id}
                        className="flex flex-wrap items-center gap-2 py-1.5 text-sm"
                      >
                        <span className="min-w-0 flex-1 truncate">{invitation.email}</span>
                        <RoleBadge role={invitation.role} />
                        <span className="font-mono text-xs text-zinc-400 dark:text-zinc-500">
                          expires {new Date(invitation.expires_at).toLocaleDateString()}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </Card>
      )}

      {activeWorkspace && manage && audit && (
        <Card
          title="Activity log"
          subtitle="Every workspace change, scoped to this workspace alone"
        >
          {audit.length === 0 ? (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">Nothing recorded yet.</p>
          ) : (
            <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {audit.map((entry, index) => (
                <li key={index} className="flex flex-wrap items-baseline gap-2 py-1.5">
                  <span className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
                    {new Date(entry.at).toLocaleString()}
                  </span>
                  <span className="font-mono text-xs font-medium">{entry.action}</span>
                  {entry.target && (
                    <span className="min-w-0 truncate text-xs text-zinc-600 dark:text-zinc-300">
                      {entry.target}
                    </span>
                  )}
                  {Object.keys(entry.meta).length > 0 && (
                    <span className="font-mono text-xs text-zinc-400 dark:text-zinc-500">
                      {JSON.stringify(entry.meta)}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </>
  );
}
