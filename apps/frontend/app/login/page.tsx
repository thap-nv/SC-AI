"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, saveSession, User } from "@/lib/api";
import { ErrorText, Logo, PrimaryButton } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ access_token: string; user: User }>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      saveSession(result.access_token, result.user);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-ink bg-hero p-12 text-white lg:flex">
        <div className="pointer-events-none absolute inset-0 bg-dots bg-[length:20px_20px] [mask-image:linear-gradient(to_bottom_left,black,transparent_65%)]" aria-hidden="true" />
        {/* A blurred cyan core, like the glowing backdrop behind the site's hero. */}
        <span className="pointer-events-none absolute -right-24 top-[48%] h-[420px] w-[420px] rounded-full bg-brand-500/20 blur-[90px]" aria-hidden="true" />
        <Logo className="relative self-start text-[18px]" />
        <div className="relative max-w-md">
          <p className="font-display text-[32px] font-bold leading-tight">
            AI-assisted safety monitoring for the <span className="bg-brand-text bg-clip-text text-transparent">factory floor</span>
          </p>
          <span className="my-6 block h-[3px] w-12 rounded-full bg-brand-text" aria-hidden="true" />
          <p className="text-[15px] leading-6 text-white/85">AI watches every camera on the factory floor and raises the alert. People decide what each alert means.</p>
        </div>
        <div className="relative text-xs text-white/70">Factory safety & compliance · Proof of concept</div>
      </section>
      <div className="grid place-items-center px-4 py-10">
        <form onSubmit={submit} className="panel w-full max-w-md border-t-[3px] border-t-brand-500 p-8 shadow-[0_10px_28px_rgba(10,21,37,.08)]">
          <Logo light className="mb-6 text-[15px] lg:hidden" />
          <div className="eyebrow text-brand-600">Factory & workshop POC</div>
          <h1 className="mt-2 font-display text-2xl font-bold tracking-tight text-graphite-900">AI Safety & Compliance Monitoring</h1>
          <p className="mt-2 text-sm text-graphite-600">Sign in to review cameras, zones, and safety alerts.</p>
          <div className="mt-6 space-y-3">
            <label className="block text-sm font-medium">Username<input className="mt-1" value={username} onChange={(e) => setUsername(e.target.value)} /></label>
            <label className="block text-sm font-medium">Password<input className="mt-1" type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
            {error ? <ErrorText>{error}</ErrorText> : null}
            <PrimaryButton type="submit" disabled={busy} className="w-full py-2.5">{busy ? "Signing in…" : "Sign in"}</PrimaryButton>
          </div>
          <div className="mt-6 rounded-lg border border-line bg-paper p-3 font-mono text-xs leading-5 text-graphite-600">
            <div>admin / admin123 — configure cameras, zones, and rules</div>
            <div>safety / safety123 — review incidents</div>
            <div>viewer / viewer123 — view only</div>
          </div>
        </form>
      </div>
    </div>
  );
}
