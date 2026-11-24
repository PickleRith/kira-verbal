// Shared UI kit: app shell (dark rail + accent line), cards, buttons, status pills,
// section headers, tool tiles and a small inline icon set (no icon dependency).

import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

// --- icons ----------------------------------------------------------------------------

type IconProps = { className?: string };
const base = "h-5 w-5 shrink-0";

function Svg({ className, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={cx(base, className)}
    >
      {children}
    </svg>
  );
}

export const Icon = {
  Mic: (p: IconProps) => (
    <Svg {...p}>
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </Svg>
  ),
  MicOff: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 3l18 18M9 9v2a3 3 0 0 0 5.1 2.1M15 10V6a3 3 0 0 0-5.7-1.3" />
      <path d="M5 11a7 7 0 0 0 11.5 5.4M19 11a7 7 0 0 1-.6 2.8M12 18v3" />
    </Svg>
  ),
  Home: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z" />
    </Svg>
  ),
  Clipboard: (p: IconProps) => (
    <Svg {...p}>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4h6v3H9zM9 12l2 2 4-4M9 17h6" />
    </Svg>
  ),
  Book: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" />
      <path d="M4 19V5M8 7h7" />
    </Svg>
  ),
  Sparkle: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z" />
      <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" />
    </Svg>
  ),
  Chat: (p: IconProps) => (
    <Svg {...p}>
      <path d="M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H9l-4 4V6a1 1 0 0 1 1-1z" />
    </Svg>
  ),
  User: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </Svg>
  ),
  Check: (p: IconProps) => (
    <Svg {...p}>
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </Svg>
  ),
  Clock: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </Svg>
  ),
  Alert: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 3l10 18H2z" />
      <path d="M12 10v4M12 17.5v.5" />
    </Svg>
  ),
  X: (p: IconProps) => (
    <Svg {...p}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Svg>
  ),
  Download: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 4v11M7 10l5 5 5-5M5 20h14" />
    </Svg>
  ),
  ArrowRight: (p: IconProps) => (
    <Svg {...p}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Svg>
  ),
  ChevronRight: (p: IconProps) => (
    <Svg {...p}>
      <path d="M9 6l6 6-6 6" />
    </Svg>
  ),
  Send: (p: IconProps) => (
    <Svg {...p}>
      <path d="M4 12l16-8-6 16-2.5-6.5z" />
    </Svg>
  ),
  Lightbulb: (p: IconProps) => (
    <Svg {...p}>
      <path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z" />
    </Svg>
  ),
  Flag: (p: IconProps) => (
    <Svg {...p}>
      <path d="M5 21V4M5 4h11l-2 4 2 4H5" />
    </Svg>
  ),
  History: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2" />
    </Svg>
  ),
  Shield: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z" />
    </Svg>
  ),
  Plus: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12 5v14M5 12h14" />
    </Svg>
  ),
};

// --- brand mark (Kira Verbal's own: a mic on a violet tile) ------------------------------

export function BrandMark({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const box = { sm: "h-8 w-8 rounded-lg", md: "h-10 w-10 rounded-xl", lg: "h-14 w-14 rounded-2xl" }[size];
  const icon = { sm: "h-4 w-4", md: "h-5 w-5", lg: "h-7 w-7" }[size];
  return (
    <span
      className={cx(
        box,
        "inline-flex items-center justify-center bg-gradient-to-br from-brand-400 to-brand-600 text-white shadow-[0_4px_14px_-4px_rgb(139_79_240/0.7)]",
      )}
    >
      <Icon.Mic className={icon} />
    </span>
  );
}

// --- app shell -----------------------------------------------------------------------

type NavKey = "home" | "teacher" | "learner" | null;

const NAV: { key: Exclude<NavKey, null>; href: string; label: string; icon: (p: IconProps) => ReactNode }[] = [
  { key: "home", href: "/", label: "Home", icon: Icon.Home },
  { key: "teacher", href: "/teacher", label: "Teacher dashboard", icon: Icon.Clipboard },
  { key: "learner", href: "/#lessons", label: "Try as a learner", icon: Icon.Chat },
];

export function AppShell({
  active,
  children,
}: {
  active: NavKey;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen border-t-[3px] border-brand-400 bg-canvas">
      {/* Desktop rail */}
      <nav
        aria-label="Main"
        className="fixed inset-y-0 left-0 z-20 hidden w-[68px] flex-col items-center gap-2 border-t-[3px] border-brand-400 bg-gradient-to-b from-brand-900 to-brand-950 py-4 md:flex"
      >
        <Link href="/" aria-label="Kira Verbal home" className="mb-4">
          <BrandMark />
        </Link>
        {NAV.map(({ key, href, label, icon: NavIcon }) => (
          <Link
            key={key}
            href={href}
            title={label}
            aria-label={label}
            aria-current={active === key ? "page" : undefined}
            className={cx(
              "group relative flex h-11 w-11 items-center justify-center rounded-xl transition",
              active === key
                ? "bg-white/15 text-white"
                : "text-brand-200/70 hover:bg-white/10 hover:text-white",
            )}
          >
            <NavIcon />
            <span className="pointer-events-none absolute left-full ml-3 whitespace-nowrap rounded-md bg-ink px-2 py-1 text-xs text-white opacity-0 transition group-hover:opacity-100">
              {label}
            </span>
          </Link>
        ))}
      </nav>

      {/* Mobile top bar */}
      <nav
        aria-label="Main"
        className="sticky top-0 z-20 flex items-center gap-2 bg-gradient-to-r from-brand-900 to-brand-950 px-4 py-2.5 md:hidden"
      >
        <Link href="/" aria-label="Kira Verbal home" className="mr-2">
          <BrandMark size="sm" />
        </Link>
        {NAV.map(({ key, href, label, icon: NavIcon }) => (
          <Link
            key={key}
            href={href}
            aria-label={label}
            aria-current={active === key ? "page" : undefined}
            className={cx(
              "flex h-9 w-9 items-center justify-center rounded-lg",
              active === key ? "bg-white/15 text-white" : "text-brand-200/70",
            )}
          >
            <NavIcon />
          </Link>
        ))}
      </nav>

      <div className="md:pl-[68px]">{children}</div>
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow ? <div className="text-sm text-muted">{eyebrow}</div> : null}
        <h1 className="mt-1 text-[26px] font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle ? <div className="mt-1.5 text-[15px] text-muted">{subtitle}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </header>
  );
}

// --- surfaces ------------------------------------------------------------------------

export function Card({
  className,
  children,
  ...rest
}: ComponentProps<"section">) {
  return (
    <section
      {...rest}
      className={cx("rounded-2xl border border-line bg-white shadow-card", className)}
    >
      {children}
    </section>
  );
}

export function SectionHeader({
  title,
  count,
  action,
  id,
}: {
  title: ReactNode;
  count?: number;
  action?: ReactNode;
  id?: string;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 id={id} className="flex items-center gap-2 text-lg font-semibold text-ink">
        {title}
        {count !== undefined ? (
          <span className="rounded-full bg-ink px-2 py-0.5 text-xs font-semibold text-white">{count}</span>
        ) : null}
      </h2>
      {action}
    </div>
  );
}

// --- buttons -------------------------------------------------------------------------

type ButtonVariant = "primary" | "secondary" | "ghost" | "success" | "pill";

const BUTTON: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-[0_6px_16px_-8px_rgb(95_43_192/0.9)] hover:from-brand-600 hover:to-brand-800",
  secondary: "border border-line bg-white text-ink hover:border-brand-200 hover:bg-brand-50",
  ghost: "text-muted hover:bg-row hover:text-ink",
  success: "bg-emerald-600 text-white hover:bg-emerald-700",
  pill: "rounded-full border border-line bg-white px-4 text-ink hover:border-brand-200 hover:bg-brand-50",
};

export function Button({
  variant = "primary",
  className,
  children,
  ...rest
}: ComponentProps<"button"> & { variant?: ButtonVariant }) {
  return (
    <button
      {...rest}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        BUTTON[variant],
        className,
      )}
    >
      {children}
    </button>
  );
}

export function ButtonLink({
  variant = "primary",
  className,
  children,
  ...rest
}: ComponentProps<typeof Link> & { variant?: ButtonVariant }) {
  return (
    <Link
      {...rest}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition",
        BUTTON[variant],
        className,
      )}
    >
      {children}
    </Link>
  );
}

// --- status pills (like Overdue / Due Today / Due in 2 days) ---------------------------

export type Tone = "red" | "amber" | "green" | "purple" | "gray" | "blue";

const TONE: Record<Tone, string> = {
  red: "bg-rose-50 text-rose-700 ring-rose-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  purple: "bg-brand-50 text-brand-700 ring-brand-200",
  gray: "bg-row text-muted ring-line",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
};

export function Pill({
  tone = "gray",
  icon,
  children,
  className,
}: {
  tone?: Tone;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        TONE[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

// --- callouts ------------------------------------------------------------------------

export function Callout({
  tone = "purple",
  title,
  children,
  role,
  icon,
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  role?: "alert" | "status";
  icon?: ReactNode;
}) {
  const style: Record<Tone, string> = {
    red: "border-rose-200 bg-rose-50 text-rose-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    green: "border-emerald-200 bg-emerald-50 text-emerald-900",
    purple: "border-brand-200 bg-brand-50 text-brand-900",
    gray: "border-line bg-row text-ink",
    blue: "border-sky-200 bg-sky-50 text-sky-900",
  };
  return (
    <div role={role} className={cx("flex gap-3 rounded-xl border p-3.5 text-sm", style[tone])}>
      {icon ? <span className="mt-0.5">{icon}</span> : null}
      <div className="min-w-0">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className={title ? "mt-0.5" : ""}>{children}</div> : null}
      </div>
    </div>
  );
}

// --- tool tiles (like "Lesson Studio / Course Studio / Assessment") ---------------------

export function ToolTile({
  icon,
  label,
  hint,
  active = false,
  onClick,
  href,
  tint = "bg-brand-50 text-brand-600",
}: {
  icon: ReactNode;
  label: ReactNode;
  hint?: ReactNode;
  active?: boolean;
  onClick?: () => void;
  href?: string;
  tint?: string;
}) {
  const body = (
    <>
      <span
        className={cx(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
          active ? "bg-white/15 text-white" : tint,
        )}
      >
        {icon}
      </span>
      <span className="min-w-0 text-left">
        <span className={cx("block truncate text-sm font-medium", active ? "text-white" : "text-ink")}>
          {label}
        </span>
        {hint ? (
          <span className={cx("block truncate text-xs", active ? "text-brand-100" : "text-muted")}>{hint}</span>
        ) : null}
      </span>
    </>
  );
  const cls = cx(
    "flex min-h-[58px] w-full items-center gap-3 rounded-xl border px-3.5 py-2.5 transition",
    active
      ? "border-transparent bg-gradient-to-br from-brand-600 to-brand-800 shadow-lift"
      : "border-line bg-white hover:border-brand-200 hover:bg-brand-50/50",
  );
  if (href) {
    return (
      <Link href={href} className={cls}>
        {body}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} aria-pressed={active} className={cls}>
      {body}
    </button>
  );
}

// --- misc ----------------------------------------------------------------------------

export function Disclaimer({ className }: { className?: string }) {
  return (
    <p className={cx("flex items-start gap-2 text-xs leading-relaxed text-faint", className)}>
      <Icon.Shield className="mt-px h-4 w-4" />
      <span>
        Independent portfolio prototype. Not affiliated with or endorsed by Kira Learning. Synthetic
        learners and data only; no real student records.
      </span>
    </p>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent",
        className,
      )}
    />
  );
}

export function LevelDots({ level, total = 4 }: { level: number | null; total?: number }) {
  return (
    <span className="inline-flex gap-1" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={cx(
            "h-1.5 w-4 rounded-full",
            level !== null && i <= level ? "bg-brand-500" : "bg-line",
          )}
        />
      ))}
    </span>
  );
}
