"use client";

// Page chrome.
//   MarketingShell - cream page, top bar (landing, login, register).
//   AppShell       - signed-in workspace: compact deep-purple sidebar with outlined icons on
//                    desktop/tablet, a top bar with a menu drawer on phones.
//   FocusShell     - the check-in itself: brand, what this is, nothing to wander off to.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { homeFor, useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

import { BrandMark, ButtonLink, Icon, cx } from "./ui";

type NavItem = { href: string; label: string; icon: (p: { className?: string }) => ReactNode };

const APP_NAV: Record<Role, NavItem[]> = {
  student: [
    { href: "/", label: "Home", icon: Icon.Home },
    { href: "/student", label: "My check-ins", icon: Icon.Mic },
  ],
  teacher: [
    { href: "/", label: "Home", icon: Icon.Home },
    { href: "/teacher", label: "Review queue", icon: Icon.Clipboard },
  ],
};

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export function Wordmark({ inverted = false }: { inverted?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5" aria-label="Kira Verbal home">
      <BrandMark inverted={inverted} />
      <span className={cx("font-serif text-[20px] leading-none", inverted ? "text-white" : "text-ink")}>Kira Verbal</span>
    </Link>
  );
}

// --- marketing -------------------------------------------------------------------------------

export function MarketingShell({ children }: { children: ReactNode }) {
  const { user, ready, logout } = useAuth();
  const router = useRouter();
  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-line bg-paper">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 md:px-8">
          <Wordmark />
          <nav aria-label="Main" className="hidden items-center gap-6 text-sm text-muted md:flex">
            <Link href="/#how" className="hover:text-ink">
              How it works
            </Link>
            <Link href="/#voice" className="hover:text-ink">
              Voice check-ins
            </Link>
            <Link href="/#teachers" className="hover:text-ink">
              For teachers
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {!ready ? null : user ? (
              <>
                <button
                  type="button"
                  onClick={async () => {
                    await logout();
                    router.push("/");
                  }}
                  className="hidden px-3 py-2 text-sm text-muted hover:text-ink sm:block"
                >
                  Sign out
                </button>
                <ButtonLink href={homeFor(user.role)} className="px-3.5 py-2">
                  Open {user.role === "teacher" ? "review queue" : "my check-ins"}
                </ButtonLink>
              </>
            ) : (
              <>
                <ButtonLink href="/login" variant="secondary" className="px-3.5 py-2">
                  Log in
                </ButtonLink>
                <ButtonLink href="/register" className="px-3.5 py-2">
                  Get started
                </ButtonLink>
              </>
            )}
          </div>
        </div>
      </header>
      {children}
    </div>
  );
}

// --- app (signed in) ---------------------------------------------------------------------

function SidebarLink({ item, active, onNavigate }: { item: NavItem; active: boolean; onNavigate?: () => void }) {
  const Glyph = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cx(
        "kv-ease group relative flex h-11 w-11 items-center justify-center rounded-lg transition-colors",
        active ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10 hover:text-white",
      )}
    >
      <Glyph className="h-5 w-5" />
      <span className="sr-only">{item.label}</span>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute left-full z-50 ml-3 whitespace-nowrap rounded-md bg-ink px-2 py-1 text-xs text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
      >
        {item.label}
      </span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const nav = user ? APP_NAV[user.role] : [];

  useEffect(() => setMenuOpen(false), [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  async function signOut() {
    await logout();
    router.push("/");
  }

  return (
    <div className="min-h-screen bg-app">
      {/* Sidebar: tablet and up */}
      <aside
        aria-label="Main"
        className="fixed inset-y-0 left-0 z-30 hidden w-[72px] flex-col items-center gap-2 bg-purple-deep py-4 md:flex"
      >
        <Link href="/" aria-label="Kira Verbal home" className="mb-4">
          <BrandMark inverted />
        </Link>
        <nav className="flex flex-col items-center gap-1.5">
          {nav.map((item) => (
            <SidebarLink key={item.href} item={item} active={isActive(pathname, item.href)} />
          ))}
        </nav>
        <div className="mt-auto flex flex-col items-center gap-2">
          {user ? (
            <span
              className="flex h-9 w-9 items-center justify-center rounded-md bg-lavender font-serif text-[15px] text-ink"
              title={`${user.display_name} (${user.role})`}
            >
              {user.display_name.charAt(0).toUpperCase()}
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => void signOut()}
            className="flex h-11 w-11 items-center justify-center rounded-lg text-white/70 hover:bg-white/10 hover:text-white"
            aria-label="Sign out"
            title="Sign out"
          >
            <Icon.LogOut className="h-5 w-5" />
          </button>
        </div>
      </aside>

      {/* Phone: top bar + drawer */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 bg-purple-deep px-4 md:hidden">
        <Wordmark inverted />
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          className="ml-auto flex h-10 w-10 items-center justify-center rounded-lg text-white hover:bg-white/10"
          aria-label="Open menu"
          aria-expanded={menuOpen}
          aria-controls="app-menu"
        >
          <Icon.Menu />
        </button>
      </header>
      {menuOpen ? (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Menu" id="app-menu">
          <button type="button" className="absolute inset-0 bg-ink/40" aria-label="Close menu" onClick={() => setMenuOpen(false)} />
          <nav className="absolute inset-y-0 right-0 flex w-72 max-w-[85vw] flex-col gap-1 bg-purple-deep p-4">
            <button
              type="button"
              onClick={() => setMenuOpen(false)}
              className="mb-4 ml-auto flex h-10 w-10 items-center justify-center rounded-lg text-white hover:bg-white/10"
              aria-label="Close menu"
            >
              <Icon.X />
            </button>
            {nav.map((item) => {
              const Glyph = item.icon;
              const active = isActive(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cx(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px]",
                    active ? "bg-white/15 text-white" : "text-white/80 hover:bg-white/10",
                  )}
                >
                  <Glyph className="h-5 w-5" /> {item.label}
                </Link>
              );
            })}
            <button
              type="button"
              onClick={() => void signOut()}
              className="mt-auto flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] text-white/80 hover:bg-white/10"
            >
              <Icon.LogOut className="h-5 w-5" /> Sign out
            </button>
          </nav>
        </div>
      ) : null}

      <div className="md:pl-[72px]">{children}</div>
    </div>
  );
}

// --- the check-in ---------------------------------------------------------------------------

export function FocusShell({ label, right, children }: { label: string; right?: ReactNode; children: ReactNode }) {
  return (
    <div className="min-h-screen bg-app">
      <header className="sticky top-0 z-30 border-b border-line bg-surface">
        <div className="mx-auto flex h-14 max-w-3xl items-center gap-3 px-4 md:px-8">
          <BrandMark size="sm" />
          <div className="min-w-0 leading-tight">
            <p className="text-sm font-medium text-ink">Kira Verbal</p>
            <p className="truncate text-xs text-muted">{label}</p>
          </div>
          <div className="ml-auto">{right}</div>
        </div>
      </header>
      {children}
    </div>
  );
}
