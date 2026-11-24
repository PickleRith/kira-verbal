"use client";

// Sign in and registration. Registration picks a role: a teacher gets a class with a join
// code; a student can enter that code now or later. Both land on their own home page.

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

import { MarketingShell } from "./shell";
import { Button, Callout, Disclaimer, Eyebrow, Field, Icon, Spinner, cx } from "./ui";

const ERRORS: Partial<Record<string, string>> = {
  invalid_credentials: "That email and password don't match an account.",
  email_taken: "An account with this email already exists. Try logging in instead.",
  class_not_found: "No class has that code. Check it with your teacher, or leave it blank for now.",
  rate_limited: "Too many attempts. Wait a minute and try again.",
  network_error: "Can't reach the server. Is the API running on port 8000?",
};

function safeNext(next: string | null, role: Role) {
  // Only follow same-site paths that belong to this role.
  if (next && next.startsWith(`/${role}`)) return next;
  return homeFor(role);
}

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { login, register, user, ready } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [role, setRole] = useState<Role>(params.get("role") === "teacher" ? "teacher" : "student");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState(params.get("code") ?? "");
  const [className, setClassName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ready && user) router.replace(safeNext(params.get("next"), user.role));
  }, [ready, user, router, params]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me =
        mode === "login"
          ? await login(email, password)
          : await register({
              email,
              password,
              display_name: name,
              role,
              join_code: role === "student" && code.trim() ? code.trim() : undefined,
              class_name: role === "teacher" && className.trim() ? className.trim() : undefined,
            });
      router.replace(safeNext(params.get("next"), me.role));
    } catch (e) {
      if (e instanceof ApiError) {
        setError(
          ERRORS[e.code] ??
            (e.code === "invalid_input"
              ? "Check the form: a valid email, a name, and a password of at least 8 characters."
              : e.message),
        );
      } else setError("Something went wrong. Please try again.");
      setBusy(false);
    }
  }

  const isRegister = mode === "register";

  return (
    <MarketingShell>
      <main className="mx-auto grid max-w-6xl gap-10 px-4 pb-20 pt-10 md:px-8 lg:grid-cols-[5fr_6fr] lg:pt-16">
        <section>
          <Eyebrow>{isRegister ? "Create a demo account" : "Welcome back"}</Eyebrow>
          <h1 className="mt-3 text-[40px] text-ink md:text-[52px]">
            {isRegister ? (
              <>
                Every voice, <em>heard</em> and reviewed.
              </>
            ) : (
              <>
                Pick up where you <em>left</em> off.
              </>
            )}
          </h1>
          <p className="mt-5 max-w-md text-base text-muted">
            Students take short spoken or typed check-ins. Teachers see every answer, the evidence behind each
            suggested level, and make the final call.
          </p>
          <ul className="mt-8 space-y-3 text-[15px] text-ink/85">
            {[
              "Teachers get a class code to share",
              "Students join with the code and start a lesson",
              "Finished check-ins land in the teacher's review queue",
            ].map((line, i) => (
              <li key={line} className="flex items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-md border border-line text-xs font-semibold text-ink">
                  {i + 1}
                </span>
                {line}
              </li>
            ))}
          </ul>
          <Disclaimer className="mt-10 max-w-md" />
        </section>

        <section className="rounded-xl border border-line bg-surface p-6 md:p-8">
          <h2 className="text-[28px] text-ink">{isRegister ? "Sign up" : "Log in"}</h2>
          <p className="mt-2 text-sm text-muted">
            {isRegister ? (
              <>
                Already have an account?{" "}
                <Link href="/login" className="text-purple-ink underline-offset-4 hover:underline">
                  Log in
                </Link>
              </>
            ) : (
              <>
                New here?{" "}
                <Link href="/register" className="text-purple-ink underline-offset-4 hover:underline">
                  Create an account
                </Link>
              </>
            )}
          </p>

          <form onSubmit={submit} className="mt-7 space-y-5" noValidate={false}>
            {isRegister ? (
              <fieldset>
                <legend className="text-sm font-medium text-ink">I am a…</legend>
                <div className="mt-2 grid grid-cols-2 gap-3" role="radiogroup" aria-label="Account type">
                  {(
                    [
                      { value: "student", label: "Student", hint: "Take check-ins", icon: <Icon.Mic className="h-4 w-4" /> },
                      { value: "teacher", label: "Teacher", hint: "Review answers", icon: <Icon.Clipboard className="h-4 w-4" /> },
                    ] as const
                  ).map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      role="radio"
                      aria-checked={role === option.value}
                      onClick={() => setRole(option.value)}
                      className={cx(
                        "kv-ease flex items-center gap-3 rounded-lg border p-3.5 text-left transition-colors",
                        role === option.value
                          ? "border-ink bg-surface ring-1 ring-ink"
                          : "border-line bg-surface hover:border-line-strong",
                      )}
                    >
                      <span
                        className={cx(
                          "flex h-9 w-9 items-center justify-center rounded-md",
                          role === option.value ? "bg-ink text-white" : "bg-sunken text-muted",
                        )}
                      >
                        {option.icon}
                      </span>
                      <span>
                        <span className="block text-sm font-medium text-ink">{option.label}</span>
                        <span className="block text-xs text-muted">{option.hint}</span>
                      </span>
                    </button>
                  ))}
                </div>
              </fieldset>
            ) : null}

            {isRegister ? (
              <Field
                label="Display name"
                name="display_name"
                autoComplete="nickname"
                required
                maxLength={80}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={role === "teacher" ? "Ms. Rivera" : "Sam"}
                icon={<Icon.User className="h-4 w-4" />}
                hint="A made-up name is fine. This is a demo."
              />
            ) : null}
            <Field
              label="Email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.test"
              icon={<Icon.Mail className="h-4 w-4" />}
            />
            <Field
              label="Password"
              name="password"
              type="password"
              autoComplete={isRegister ? "new-password" : "current-password"}
              required
              minLength={isRegister ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={isRegister ? "At least 8 characters" : "Your password"}
              icon={<Icon.Lock className="h-4 w-4" />}
            />
            {isRegister && role === "student" ? (
              <Field
                label={
                  <>
                    Class code <span className="font-normal text-faint">(optional)</span>
                  </>
                }
                name="join_code"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                placeholder="e.g. K7Q4MZ"
                maxLength={16}
                autoComplete="off"
                icon={<Icon.Key className="h-4 w-4" />}
                hint="Your teacher shares this. You can also add it later."
              />
            ) : null}
            {isRegister && role === "teacher" ? (
              <Field
                label={
                  <>
                    Class name <span className="font-normal text-faint">(optional)</span>
                  </>
                }
                name="class_name"
                value={className}
                onChange={(e) => setClassName(e.target.value)}
                placeholder="Period 3 Science"
                maxLength={80}
                icon={<Icon.Users className="h-4 w-4" />}
                hint="You'll get a code to share with your students."
              />
            ) : null}

            {error ? (
              <Callout tone="red" role="alert" icon={<Icon.Alert className="h-4 w-4" />}>
                {error}
              </Callout>
            ) : null}

            <Button type="submit" disabled={busy} className="w-full py-3">
              {busy ? <Spinner /> : <Icon.ArrowRight className="h-4 w-4" />}
              {busy ? "One moment…" : isRegister ? `Create ${role} account` : "Log in"}
            </Button>
          </form>
        </section>
      </main>
    </MarketingShell>
  );
}
