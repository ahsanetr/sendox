"use client";

import { Check, Palette } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  SCHEMES,
  readScheme,
  readSchemeOnServer,
  subscribeScheme,
  writeScheme,
  type SchemeId,
} from "@/lib/schemes";

/** Lets you try the colour schemes on without a rebuild.
 *
 *  The schemes are plain CSS custom-property blocks keyed off `data-scheme` on
 *  <html>, so switching is one attribute write and every component follows —
 *  nothing reads a colour directly. The choice is remembered per browser and
 *  re-applied by a small script in the document head, before first paint, so
 *  the page never flashes the default scheme on its way to yours.
 */
export function SchemePicker() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = useSyncExternalStore(
    subscribeScheme,
    readScheme,
    readSchemeOnServer,
  );

  // Clicking away and Escape both close it: a menu you can only dismiss by
  // hitting the same button again is a menu that feels stuck.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function choose(id: SchemeId) {
    writeScheme(id);
    setOpen(false);
  }

  const current = SCHEMES.find((scheme) => scheme.id === active) ?? SCHEMES[0];

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`Colour scheme: ${current.label}`}
        title={`Colour scheme: ${current.label}`}
        className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md text-sidebar-foreground transition-colors duration-200 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
      >
        <Palette className="size-4" aria-hidden />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Colour scheme"
          className="absolute bottom-full left-0 z-20 mb-2 w-[19.5rem] overflow-hidden rounded-md bg-sidebar-accent py-1 shadow-xl ring-1 ring-black/25"
        >
          <p className="px-3 pt-1.5 pb-2 text-[0.6875rem] font-medium tracking-wide text-sidebar-foreground uppercase">
            Colour scheme
          </p>
          {SCHEMES.map((scheme) => (
            <button
              key={scheme.id}
              type="button"
              role="menuitemradio"
              aria-checked={scheme.id === active}
              onClick={() => choose(scheme.id)}
              className="flex w-full cursor-pointer items-center gap-3 px-3 py-2 text-left transition-colors duration-200 hover:bg-sidebar"
            >
              <span className="flex shrink-0 gap-1" aria-hidden>
                {scheme.swatch.map((colour) => (
                  <span
                    key={colour}
                    className="size-3.5 rounded-full ring-1 ring-inset ring-white/15"
                    style={{ backgroundColor: colour }}
                  />
                ))}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[0.8125rem] text-sidebar-accent-foreground">
                  {scheme.label}
                </span>
                <span className="block text-[0.6875rem] leading-snug text-sidebar-foreground">
                  {scheme.note}
                </span>
              </span>
              {scheme.id === active && (
                <Check
                  className="size-3.5 shrink-0 text-sidebar-accent-foreground"
                  aria-hidden
                />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
