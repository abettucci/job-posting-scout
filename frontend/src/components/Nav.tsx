"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";

const links = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/jobs", label: "Jobs" },
  { href: "/applied", label: "Applied" },
  { href: "/dismissed", label: "Dismissed" },
  { href: "/interviews", label: "Interviews" },
  { href: "/resume", label: "Resume" },
  { href: "/settings", label: "Settings" },
];

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const handleLogout = () => {
    logout();
    router.replace("/");
  };

  return (
    <nav className="sticky top-0 z-10 border-b backdrop-blur" style={{ background: "color-mix(in srgb, var(--background) 90%, transparent)", borderColor: "var(--line)" }}>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 min-h-16 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link href="/dashboard" className="flex items-center gap-2.5 font-black tracking-[-0.05em] text-lg whitespace-nowrap" style={{ color: "var(--foreground)" }}>
            <span className="w-7 h-7 rounded-full grid place-items-center text-white text-xs tracking-normal" style={{ background: "var(--accent)" }}>JS</span>
            Job Scout
          </Link>
          <div className="hidden lg:flex gap-1 overflow-x-auto">
            {links.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={`px-3 py-1.5 rounded-md text-sm transition-colors ${
                  pathname.startsWith(l.href)
                    ? "bg-black text-white dark:bg-white dark:text-slate-900"
                    : "text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white"
                }`}
              >
                {l.label}
              </Link>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3 whitespace-nowrap">
          <span className="text-xs hidden xl:block" style={{ color: "var(--ink-muted)" }}>{user?.email}</span>
          <button
            onClick={toggleTheme}
            aria-label="Toggle dark/light mode"
            className="min-w-9 min-h-9 rounded-full border text-sm transition-colors cursor-pointer hover:bg-black/[.04] dark:hover:bg-white/[.06]"
            style={{ borderColor: "var(--line)" }}
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
          <button onClick={handleLogout} className="hidden sm:block text-sm font-semibold hover:opacity-70 transition-opacity cursor-pointer" style={{ color: "var(--ink-muted)" }}>
            Sign out
          </button>
        </div>
      </div>
      <div className="lg:hidden flex gap-1 overflow-x-auto px-4 pb-2 [scrollbar-width:none]">
        {links.map((l) => (
          <Link key={l.href} href={l.href} className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${pathname.startsWith(l.href) ? "bg-black text-white dark:bg-white dark:text-slate-900" : "text-slate-600 dark:text-slate-300"}`}>{l.label}</Link>
        ))}
      </div>
    </nav>
  );
}
