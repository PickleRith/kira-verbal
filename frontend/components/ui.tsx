// UI primitives for the light editorial system (see DESIGN_SYSTEM.md). Presentation only:
// no data fetching or business rules here.
//
// Buttons: black rectangle (primary), outline (secondary), ghost, purple (AI actions).
// Cards: white, thin border, 12px radius. Pills: small, 6px radius (not full pills).
// Icons: Lucide outline icons through the `Icon` map, so call sites stay stable.

import {
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  CircleExclamationPoint,
  ClipboardCheck,
  Clock,
  Copy,
  Download,
  Flag,
  GraduationCap,
  House,
  KeyRound,
  Layers,
  LayoutGrid,
  Lightbulb,
  LoaderCircle,
  Lock,
  LogOut,
  Mail,
  Menu,
  MessageSquare,
  Mic,
  MicOff,
  PhoneOff,
  Plus,
  Quote,
  RotateCcw,
  RotateCcwClock,
  SendHorizontal,
  Shield,
  Sparkles,
  TriangleExclamationPoint,
  User,
  Users,
  Volume2,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

export function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

// --- icons ----------------------------------------------------------------------------

type IconProps = { className?: string };

function wrap(Glyph: LucideIcon) {
  function IconGlyph({ className }: IconProps) {
    return <Glyph aria-hidden="true" strokeWidth={1.75} className={cx("h-5 w-5 shrink-0", className)} />;
  }
  return IconGlyph;
}

export const Icon = {
  Mic: wrap(Mic),
  MicOff: wrap(MicOff),
  Home: wrap(House),
  Clipboard: wrap(ClipboardCheck),
  Book: wrap(BookOpen),
  Sparkle: wrap(Sparkles),
  Chat: wrap(MessageSquare),
  User: wrap(User),
  Users: wrap(Users),
  Check: wrap(Check),
  CheckCircle: wrap(CircleCheck),
  Clock: wrap(Clock),
  Alert: wrap(TriangleExclamationPoint),
  Error: wrap(CircleExclamationPoint),
  X: wrap(X),
  Download: wrap(Download),
  ArrowRight: wrap(ArrowRight),
  ArrowUpRight: wrap(ArrowUpRight),
  ChevronRight: wrap(ChevronRight),
  ChevronLeft: wrap(ChevronLeft),
  Send: wrap(SendHorizontal),
  Lightbulb: wrap(Lightbulb),
  Flag: wrap(Flag),
  History: wrap(RotateCcwClock),
  Shield: wrap(Shield),
  Plus: wrap(Plus),
  LogOut: wrap(LogOut),
  Copy: wrap(Copy),
  Mail: wrap(Mail),
  Lock: wrap(Lock),
  Key: wrap(KeyRound),
  Waveform: wrap(AudioLines),
  Quote: wrap(Quote),
  Layers: wrap(Layers),
  Menu: wrap(Menu),
  Retry: wrap(RotateCcw),
  EndCall: wrap(PhoneOff),
  Speaker: wrap(Volume2),
  Grid: wrap(LayoutGrid),
  Cap: wrap(GraduationCap),
  Loader: wrap(LoaderCircle),
};

// --- brand mark: Kira Verbal's own (a microphone on a black square) ----------------------

export function BrandMark({ size = "md", inverted = false }: { size?: "sm" | "md" | "lg"; inverted?: boolean }) {
  const box = { sm: "h-7 w-7 rounded-md", md: "h-8 w-8 rounded-md", lg: "h-12 w-12 rounded-lg" }[size];
  const icon = { sm: "h-4 w-4", md: "h-[18px] w-[18px]", lg: "h-6 w-6" }[size];
  return (
    <span
      className={cx(
        box,
        "relative inline-flex shrink-0 items-center justify-center",
        inverted ? "bg-white text-purple-deep" : "bg-ink text-white",
      )}
    >
      <Icon.Mic className={icon} />
      <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-mint" aria-hidden="true" />
    </span>
  );
}

// --- typography ------------------------------------------------------------------------------

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cx("text-sm font-medium text-muted", className)}>{children}</p>;
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
    <header className="flex flex-wrap items-end justify-between gap-6">
      <div className="min-w-0">
        {eyebrow ? <div className="mb-2">{typeof eyebrow === "string" ? <Eyebrow>{eyebrow}</Eyebrow> : eyebrow}</div> : null}
        <h1 className="text-[36px] text-ink md:text-[44px]">{title}</h1>
        {subtitle ? <div className="mt-3 max-w-2xl text-base text-muted">{subtitle}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </header>
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
    <div className="mb-4 flex items-end justify-between gap-3">
      <h2 id={id} className="flex items-center gap-2.5 text-[28px] text-ink">
        {title}
        {count !== undefined ? <Count>{count}</Count> : null}
      </h2>
      {action}
    </div>
  );
}

// A small dark counter, like "Grading queue 54".
export function Count({ children, tone = "dark" }: { children: ReactNode; tone?: "dark" | "light" }) {
  return (
    <span
      className={cx(
        "inline-flex min-w-6 items-center justify-center rounded-md px-1.5 py-0.5 font-sans text-xs font-semibold leading-none",
        tone === "dark" ? "bg-ink text-white" : "bg-sunken text-muted",
      )}
    >
      {children}
    </span>
  );
}

// --- surfaces ------------------------------------------------------------------------

export function Card({ className, children, ...rest }: ComponentProps<"section">) {
  return (
    <section {...rest} className={cx("rounded-xl border border-line bg-surface", className)}>
      {children}
    </section>
  );
}

// A highlight card (class code, calls to action): mint or lavender fill, ink text.
export function NoteCard({
  title,
  children,
  footer,
  tone = "mint",
  className,
}: {
  title: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  tone?: "mint" | "lavender";
  className?: string;
}) {
  return (
    <div
      className={cx(
        "rounded-xl border border-ink p-6 text-ink md:p-8",
        tone === "mint" ? "bg-mint" : "bg-lavender",
        className,
      )}
    >
      <h3 className="text-[26px] text-ink">{title}</h3>
      {children ? <div className="mt-2 text-[15px] text-ink/80">{children}</div> : null}
      {footer ? <div className="mt-6 border-t border-ink/20 pt-4 text-sm">{footer}</div> : null}
    </div>
  );
}

// Small label laid over media.
export function MediaLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1 text-xs text-muted", className)}>
      {children}
    </span>
  );
}

// --- buttons -------------------------------------------------------------------------

type ButtonVariant = "primary" | "secondary" | "ghost" | "ai" | "success" | "danger";

const BUTTON: Record<ButtonVariant, string> = {
  primary: "bg-ink text-white hover:bg-[#333333]",
  secondary: "border border-line-strong bg-transparent text-ink hover:bg-raised",
  ghost: "text-muted hover:bg-raised hover:text-ink",
  ai: "bg-purple-ink text-white hover:bg-[#4a22c2]", // purple with AA-contrast white text
  success: "bg-ok text-white hover:bg-[#0f5631]",
  danger: "border border-bad/40 bg-transparent text-bad hover:bg-bad-soft",
};

const BUTTON_BASE =
  "kv-ease inline-flex items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45";

export function Button({
  variant = "primary",
  className,
  children,
  ...rest
}: ComponentProps<"button"> & { variant?: ButtonVariant }) {
  return (
    <button {...rest} className={cx(BUTTON_BASE, BUTTON[variant], className)}>
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
    <Link {...rest} className={cx(BUTTON_BASE, BUTTON[variant], className)}>
      {children}
    </Link>
  );
}

// --- status pills ----------------------------------------------------------------------

export type Tone = "red" | "amber" | "green" | "purple" | "gray" | "blue";

const TONE: Record<Tone, string> = {
  red: "bg-bad-soft text-bad",
  amber: "bg-warn-soft text-warn",
  green: "bg-ok-soft text-ok",
  purple: "bg-lavender-soft text-purple-ink",
  gray: "bg-sunken text-muted",
  blue: "bg-info-soft text-info",
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
        "inline-flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium",
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

const CALLOUT: Record<Tone, string> = {
  red: "border-bad/30 bg-bad-soft",
  amber: "border-warn/30 bg-warn-soft",
  green: "border-ok/30 bg-ok-soft",
  purple: "border-purple/30 bg-lavender-soft",
  gray: "border-line bg-raised",
  blue: "border-info/30 bg-info-soft",
};
const CALLOUT_TITLE: Record<Tone, string> = {
  red: "text-bad",
  amber: "text-warn",
  green: "text-ok",
  purple: "text-purple-ink",
  gray: "text-ink",
  blue: "text-info",
};

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
  return (
    <div role={role} className={cx("flex gap-3 rounded-lg border p-4 text-sm text-ink", CALLOUT[tone])}>
      {icon ? <span className={cx("mt-0.5", CALLOUT_TITLE[tone])}>{icon}</span> : null}
      <div className="min-w-0">
        {title ? <p className={cx("font-semibold", CALLOUT_TITLE[tone])}>{title}</p> : null}
        {children ? <div className={title ? "mt-0.5" : ""}>{children}</div> : null}
      </div>
    </div>
  );
}

// --- form fields -----------------------------------------------------------------------

export function Field({
  label,
  hint,
  icon,
  className,
  id,
  ...input
}: ComponentProps<"input"> & { label: ReactNode; hint?: ReactNode; icon?: ReactNode }) {
  const inputId = id ?? (typeof input.name === "string" ? `f-${input.name}` : undefined);
  return (
    <label htmlFor={inputId} className={cx("block text-sm", className)}>
      <span className="block font-medium text-ink">{label}</span>
      <span className="kv-ease mt-1.5 flex items-center rounded-md border border-line-strong bg-surface transition-colors focus-within:border-purple focus-within:ring-2 focus-within:ring-lavender-soft">
        {icon ? <span className="ml-3 text-faint">{icon}</span> : null}
        <input
          id={inputId}
          {...input}
          className="w-full rounded-md bg-transparent px-3 py-2.5 text-[15px] text-ink outline-none placeholder:text-faint focus-visible:outline-none"
        />
      </span>
      {hint ? <span className="mt-1.5 block text-xs text-faint">{hint}</span> : null}
    </label>
  );
}

// --- misc ----------------------------------------------------------------------------

export function Disclaimer({ className }: { className?: string }) {
  return (
    <p className={cx("flex items-start gap-2 text-xs text-faint", className)}>
      <Icon.Shield className="mt-px h-4 w-4" />
      <span>
        Independent portfolio prototype. Not affiliated with or endorsed by Kira Learning. Demo accounts and
        synthetic data only: use made-up names and emails, never real student records.
      </span>
    </p>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Icon.Loader className={cx("h-4 w-4 animate-spin motion-reduce:animate-none", className)} />;
}

// One segment per point (levels 0-3 -> 3 segments), the same as the student's results.
export function LevelDots({ level, total = 3 }: { level: number | null; total?: number }) {
  return (
    <span className="inline-flex gap-1" aria-hidden="true">
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={cx("h-1.5 w-5 rounded-sm", level !== null && i < level ? "bg-purple" : "bg-sunken")} />
      ))}
    </span>
  );
}

export function Stat({ label, children, accent = false }: { label: string; children: ReactNode; accent?: boolean }) {
  return (
    <div className={cx("rounded-xl border p-4", accent ? "border-purple/40 bg-lavender-soft" : "border-line bg-surface")}>
      <p className="text-xs font-medium text-muted">{label}</p>
      <div className="mt-1 font-serif text-[30px] leading-tight text-ink">{children}</div>
    </div>
  );
}

// Empty state used by lists.
export function EmptyState({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-4 py-10 text-center">
      {icon ? <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-sunken text-muted">{icon}</span> : null}
      <p className="mt-3 font-serif text-[20px] text-ink">{title}</p>
      {children ? <p className="mt-1 max-w-sm text-sm text-muted">{children}</p> : null}
    </div>
  );
}
