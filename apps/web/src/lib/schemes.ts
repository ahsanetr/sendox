/** The colour schemes offered by the picker in the rail.
 *
 *  Each id matches a `:root[data-scheme="…"]` block in globals.css; the swatch
 *  is the three colours that actually tell the schemes apart at a glance —
 *  rail, canvas, primary — so the menu shows the scheme rather than naming it.
 */
export type SchemeId = "swiss" | "graphite" | "indigo" | "teal" | "midnight";

export const SCHEME_STORAGE_KEY = "sendox.scheme";

export const SCHEMES: {
  id: SchemeId;
  label: string;
  note: string;
  swatch: [string, string, string];
}[] = [
  {
    id: "swiss",
    label: "Swiss Blue",
    note: "The default — generated for this project",
    swatch: ["#0f172a", "#f8fafc", "#2563eb"],
  },
  {
    id: "graphite",
    label: "Graphite",
    note: "Near-black and gold, almost no colour",
    swatch: ["#18181b", "#fafafa", "#171717"],
  },
  {
    id: "indigo",
    label: "Indigo",
    note: "Violet-tinted canvas, indigo actions",
    swatch: ["#1e1b4b", "#f5f3ff", "#4f46e5"],
  },
  {
    id: "teal",
    label: "Teal",
    note: "Cool canvas, teal actions, orange alerts",
    swatch: ["#0f2e2b", "#f0fdfa", "#0f766e"],
  },
  {
    id: "midnight",
    label: "Midnight",
    note: "Dark throughout, green for healthy",
    swatch: ["#0a0e1c", "#020617", "#22c55e"],
  },
];

export function isSchemeId(value: unknown): value is SchemeId {
  return SCHEMES.some((scheme) => scheme.id === value);
}

/* ---------------------------------------------------------------------------
   The scheme lives on <html data-scheme>, not in React state.

   That attribute is the thing the CSS reads, it is set before hydration by the
   inline script in the layout, and a user could set it from the console; React
   is therefore a reader of it, not its owner. Exposed as a subscribable store
   so components can read it with useSyncExternalStore instead of mirroring it
   into state and syncing the two.
--------------------------------------------------------------------------- */

let listeners: (() => void)[] = [];

export function subscribeScheme(onChange: () => void): () => void {
  listeners = [...listeners, onChange];
  return () => {
    listeners = listeners.filter((listener) => listener !== onChange);
  };
}

export function readScheme(): SchemeId {
  const current = document.documentElement.dataset.scheme;
  return isSchemeId(current) ? current : "swiss";
}

/** On the server there is no document, and no stored preference to honour. */
export function readSchemeOnServer(): SchemeId {
  return "swiss";
}

export function writeScheme(id: SchemeId): void {
  document.documentElement.dataset.scheme = id;
  try {
    window.localStorage.setItem(SCHEME_STORAGE_KEY, id);
  } catch {
    // Private browsing refuses storage; the scheme still applies for this
    // session, which is all the control promises.
  }
  for (const listener of listeners) listener();
}
