"use client";

// Tabs: rectangular tabs on a white card, with a black underline on the active one.
// Keyboard: arrow keys move between tabs (roving tabindex).

import { useId, type ReactNode } from "react";

import { Count, cx } from "./ui";

export interface FolderTab {
  id: string;
  label: ReactNode;
  count?: number;
}

export function FolderTabs({
  tabs,
  active,
  onChange,
  children,
  className,
}: {
  tabs: FolderTab[];
  active: string;
  onChange: (id: string) => void;
  children: ReactNode;
  className?: string;
}) {
  const base = useId();
  return (
    <div className={cx("rounded-xl border border-line bg-surface", className)}>
      <div
        role="tablist"
        className="flex gap-1 overflow-x-auto border-b border-line px-3"
        onKeyDown={(event) => {
          const index = tabs.findIndex((t) => t.id === active);
          if (event.key === "ArrowRight") onChange(tabs[(index + 1) % tabs.length].id);
          if (event.key === "ArrowLeft") onChange(tabs[(index - 1 + tabs.length) % tabs.length].id);
        }}
      >
        {tabs.map((tab) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              id={`${base}-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`${base}-panel`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.id)}
              className={cx(
                "kv-ease -mb-px flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-3 text-sm transition-colors",
                selected ? "border-ink font-medium text-ink" : "border-transparent text-muted hover:text-ink",
              )}
            >
              {tab.label}
              {tab.count !== undefined ? <Count tone={selected ? "dark" : "light"}>{tab.count}</Count> : null}
            </button>
          );
        })}
      </div>
      <div id={`${base}-panel`} role="tabpanel" aria-labelledby={`${base}-tab-${active}`} className="p-4 md:p-6">
        {children}
      </div>
    </div>
  );
}
