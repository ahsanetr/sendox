"use client";

import { Check, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  getBrandProfile,
  saveBrandProfile,
  type BrandProfile,
  type BrandProfilePatch,
  type BrandTone,
} from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button } from "@/components/app/primitives";

/** Five questions, asked one at a time.
 *
 *  One per screen rather than a single long form, because these are the answers
 *  the copywriting agent is steered by: a merchant who skims a wall of textareas
 *  writes five thin answers, and thin answers produce generic copy that looks
 *  like the model's fault. Asking one thing at a time is what buys the detail.
 *
 *  Each step saves on the way out, so a closed tab costs at most one answer and
 *  the merchant can stop halfway without losing the rest.
 */

type Step = {
  key: keyof BrandProfilePatch;
  question: string;
  help: string;
  placeholder: string;
  optional?: boolean;
  kind: "text" | "tone";
};

const TONES: { value: BrandTone; label: string; example: string }[] = [
  { value: "warm", label: "Warm", example: "Glad you are here. Here is what we would pick." },
  { value: "playful", label: "Playful", example: "New thing. We are quite pleased with it." },
  { value: "direct", label: "Direct", example: "Back in stock. Three sizes left." },
  { value: "luxury", label: "Luxury", example: "Made in small numbers, by people we know." },
  { value: "technical", label: "Technical", example: "20k hydrostatic head, taped seams." },
];

const STEPS: Step[] = [
  {
    key: "what_you_sell",
    kind: "text",
    question: "What do you sell?",
    help: "In your own words, the way you would say it to someone at a market stall. Not your SEO description.",
    placeholder: "Hard-wearing outdoor clothing for people who are outside whether or not the forecast is good.",
  },
  {
    key: "audience",
    kind: "text",
    question: "Who buys it?",
    help: "Be specific. 'Everyone' produces copy written for nobody.",
    placeholder: "Hikers and hill walkers in their 30s and 40s who have owned cheap gear and stopped buying it.",
  },
  {
    key: "tone",
    kind: "tone",
    question: "How should Sendox sound?",
    help: "This one is a fixed list because it steers the writing directly. The next question is where the nuance goes.",
    placeholder: "",
  },
  {
    key: "never_say",
    kind: "text",
    optional: true,
    question: "Is there anything Sendox must never say?",
    help: "Claims you cannot stand behind, words you dislike, promises you do not make. Leave it empty if there are none.",
    placeholder: "Never say waterproof about the fleece. Never use the word 'curated'. No countdown urgency.",
  },
  {
    key: "voice_notes",
    kind: "text",
    optional: true,
    question: "Anything else about how you write?",
    help: "The nuance a dropdown cannot hold. Phrases you use, how you sign off, whether you use exclamation marks.",
    placeholder: "We write short sentences. We never use exclamation marks. We sign off 'See you out there'.",
  },
];

type SaveState = "idle" | "saving" | "saved" | "error";

export function OnboardingWizard({ onComplete }: { onComplete?: () => void }) {
  const { activeWorkspace } = useSession();
  const workspaceId = activeWorkspace?.id ?? null;

  const [profile, setProfile] = useState<BrandProfile | null>(null);
  const [step, setStep] = useState(0);
  // The draft carries the step it belongs to, so moving between questions
  // reveals the stored answer without an effect copying one piece of state into
  // another. Mirroring them would mean two sources of truth and a render where
  // the field still shows the previous question's text.
  const [draft, setDraft] = useState<{ step: number; text: string } | null>(null);
  const [save, setSave] = useState<SaveState>("idle");
  const [error, setError] = useState<string | null>(null);
  // Whether the person is currently working through the questions. Without it,
  // answering the three required questions flips the panel straight to the
  // summary and the two optional ones are never asked — completeness is about
  // what the generator needs, not about the wizard being finished.
  const [walking, setWalking] = useState(false);
  const field = useRef<HTMLTextAreaElement>(null);

  const current = STEPS[step];
  const stored = (profile?.[current.key as keyof BrandProfile] as string | null) ?? "";
  const value = draft?.step === step ? draft.text : stored;

  function edit(text: string) {
    setDraft({ step, text });
    setSave("idle");
  }

  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    void getBrandProfile(workspaceId)
      .then((loaded) => {
        if (cancelled) return;
        setProfile(loaded);
        // Resume where they stopped rather than at step one: re-reading answers
        // you already gave is the fastest way to make someone abandon a wizard.
        const firstUnanswered = STEPS.findIndex(
          (s) => !s.optional && !loaded[s.key as keyof BrandProfile],
        );
        setStep(firstUnanswered === -1 ? 0 : firstUnanswered);
        setWalking(!loaded.complete);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const persist = useCallback(
    async (patch: BrandProfilePatch) => {
      if (!workspaceId) return false;
      setSave("saving");
      setError(null);
      try {
        const result = await saveBrandProfile(workspaceId, patch);
        setProfile((previous) =>
          previous ? { ...previous, ...patch, complete: result.complete } : previous,
        );
        setSave("saved");
        return true;
      } catch (reason: unknown) {
        setSave("error");
        setError(reason instanceof Error ? reason.message : String(reason));
        return false;
      }
    },
    [workspaceId],
  );

  async function goNext() {
    const ok = await persist({ [current.key]: value } as BrandProfilePatch);
    if (!ok) return;
    if (step === STEPS.length - 1) {
      // The last question is the only exit from the walk-through.
      setWalking(false);
      onComplete?.();
      return;
    }
    setDraft(null);
    setStep(step + 1);
  }

  async function goBack() {
    if (step === 0) return;
    await persist({ [current.key]: value } as BrandProfilePatch);
    setDraft(null);
    setStep(step - 1);
  }

  if (!workspaceId) {
    return <p className="text-sm text-muted-foreground">Select a workspace first.</p>;
  }

  if (!profile) {
    // Shaped like the thing it is loading, so the panel does not jump.
    return (
      <div className="panel animate-pulse space-y-4 p-6">
        <div className="h-2 w-40 rounded bg-muted" />
        <div className="h-6 w-2/3 rounded bg-muted" />
        <div className="h-28 w-full rounded bg-muted" />
      </div>
    );
  }

  const answered = STEPS.filter(
    (s) => (profile[s.key as keyof BrandProfile] as string | null) ?? false,
  ).length;

  if (profile.complete && !walking) {
    return (
      <Summary
        profile={profile}
        onEdit={() => {
          setStep(0);
          setDraft(null);
          setWalking(true);
        }}
      />
    );
  }

  const canAdvance = current.optional || value.trim().length > 0;
  const fieldId = `brand-${String(current.key)}`;

  return (
    <div className="panel p-6">
      <Progress step={step} answered={answered} />

      <h3 className="mt-5 text-lg font-semibold tracking-tight">{current.question}</h3>
      {/* Helper text above the control, not inside it: a placeholder that
          explains the question disappears the moment someone starts typing. */}
      <p className="mt-1.5 max-w-prose text-sm leading-relaxed text-muted-foreground">
        {current.help}
      </p>

      <div className="mt-5">
        {current.kind === "tone" ? (
          <ToneChoice
            value={(value as BrandTone) || null}
            onChange={edit}
          />
        ) : (
          <>
            <label htmlFor={fieldId} className="block text-sm font-medium">
              Your answer
              {current.optional && (
                <span className="ml-2 font-normal text-muted-foreground">optional</span>
              )}
            </label>
            <textarea
              id={fieldId}
              ref={field}
              value={value}
              rows={4}
              onChange={(event) => edit(event.target.value)}
              placeholder={current.placeholder}
              className="mt-2 w-full resize-y rounded-md border border-input bg-card px-3 py-2.5 text-sm leading-relaxed text-foreground outline-none transition-colors duration-200 placeholder:text-muted-foreground/60 focus:border-ring focus:ring-2 focus:ring-ring/25"
            />
          </>
        )}
      </div>

      {/* Errors sit with the control they belong to, not at the top of a page
          the person has already scrolled past. */}
      {error && (
        <p className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive ring-1 ring-inset ring-destructive/20">
          {error}
        </p>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => void goBack()}
          disabled={step === 0}
          className="inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2.5 py-2 text-sm text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronLeft className="size-4" aria-hidden />
          Back
        </button>

        <div className="flex items-center gap-3">
          {save === "saving" && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
              Saving
            </span>
          )}
          {save === "saved" && (
            <span className="flex items-center gap-1.5 text-xs text-positive">
              <Check className="size-3.5" aria-hidden />
              Saved
            </span>
          )}
          <Button onClick={() => void goNext()} disabled={!canAdvance || save === "saving"}>
            {step === STEPS.length - 1 ? "Finish" : "Next"}
          </Button>
        </div>
      </div>
    </div>
  );
}

/** Where you are, without a progress bar that implies more precision than exists. */
function Progress({ step, answered }: { step: number; answered: number }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex gap-1.5" aria-hidden>
        {STEPS.map((item, index) => (
          <span
            key={item.key}
            className={`h-1 w-8 rounded-full transition-colors duration-200 ${
              index === step
                ? "bg-primary"
                : index < step
                  ? "bg-primary/40"
                  : "bg-muted"
            }`}
          />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Question {step + 1} of {STEPS.length}
        {answered > 0 && ` · ${answered} answered`}
      </p>
    </div>
  );
}

/** Tone, shown by example rather than by adjective.
 *
 *  "Direct" and "warm" mean different things to different people, and the
 *  merchant cannot tell which one produces the writing they want. A sample
 *  sentence in each voice is the only honest way to ask the question.
 */
function ToneChoice({
  value,
  onChange,
}: {
  value: BrandTone | null;
  onChange: (tone: BrandTone) => void;
}) {
  return (
    <fieldset>
      <legend className="text-sm font-medium">Pick the one that sounds most like you</legend>
      <div className="mt-3 grid gap-2">
        {TONES.map((tone) => {
          const selected = value === tone.value;
          return (
            <button
              key={tone.value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(tone.value)}
              className={`flex cursor-pointer items-start gap-3 rounded-md border px-4 py-3 text-left transition-colors duration-200 active:scale-[0.995] ${
                selected
                  ? "border-primary bg-primary/10"
                  : "border-border bg-card hover:border-muted-foreground/40"
              }`}
            >
              <span
                className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border ${
                  selected ? "border-primary bg-primary" : "border-muted-foreground/40"
                }`}
                aria-hidden
              >
                {selected && <Check className="size-2.5 text-primary-foreground" />}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium">{tone.label}</span>
                <span className="mt-0.5 block text-sm text-muted-foreground">
                  &ldquo;{tone.example}&rdquo;
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}

function Summary({ profile, onEdit }: { profile: BrandProfile; onEdit: () => void }) {
  const rows = STEPS.map((item) => ({
    question: item.question,
    answer: (profile[item.key as keyof BrandProfile] as string | null) ?? null,
    optional: item.optional ?? false,
  }));

  return (
    <div className="panel">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-6 py-4">
        <div className="flex items-center gap-2.5">
          <span className="flex size-7 items-center justify-center rounded-full bg-positive/12">
            <Check className="size-4 text-positive" aria-hidden />
          </span>
          <div>
            <h3 className="text-sm font-semibold tracking-tight">Brand profile complete</h3>
            <p className="text-xs text-muted-foreground">
              Every campaign Sendox writes is steered by these answers.
            </p>
          </div>
        </div>
        <Button variant="quiet" onClick={onEdit}>
          Edit answers
        </Button>
      </header>
      <dl className="divide-y divide-border/60">
        {rows.map((row) => (
          <div key={row.question} className="px-6 py-4">
            <dt className="text-xs font-medium text-muted-foreground">{row.question}</dt>
            <dd className="mt-1 text-sm leading-relaxed">
              {row.answer ?? (
                <span className="text-muted-foreground/70">
                  {row.optional ? "Nothing specified" : "Not answered"}
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function WizardNextIcon() {
  return <ChevronRight className="size-4" aria-hidden />;
}
