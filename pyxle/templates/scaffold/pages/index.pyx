from __future__ import annotations

from datetime import datetime, timezone

from pyxle import __version__

HEAD = """
<title>Pyxle • Next-style starter</title>
<meta name="description" content="Kick off a Pyxle project with a minimal, Next.js inspired landing page." />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<link rel="icon" href="/favicon.ico" />
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600&display=swap" rel="stylesheet" />
<link rel="stylesheet" href="/styles/tailwind.css" />
<script>
(function() {
        try {
                var key = 'pyxle-theme-preference';
                var stored = localStorage.getItem(key);
                var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
                if (stored === 'dark' || (!stored && prefersDark)) {
                        document.documentElement.classList.add('dark');
                        document.documentElement.dataset.theme = 'dark';
                } else {
                        document.documentElement.classList.remove('dark');
                        document.documentElement.dataset.theme = 'light';
                }
        } catch (error) {}
})();
</script>
"""


@server
async def load_home(request):
        now = datetime.now(tz=timezone.utc)
        iso_timestamp = now.isoformat()
        display_time = now.strftime("%H:%M:%S UTC")
        return {
                "hero": {
                        "eyebrow": "PYTHON ✕ REACT",
                        "title": "Build like Next.js without leaving Python.",
                        "tagline": "Pyxle keeps loaders and components together so you can ship full-stack features without wiring a separate API layer.",
                        "cta": {
                                "label": "Read the docs",
                                "href": "https://pyxle.dev/docs",
                        },
                },
                "highlights": [
                        {
                                "label": "Routes",
                                "title": "File-based navigation",
                                "summary": "Drop `.pyx` files under pages/ to create instant routes, dynamic segments, and layouts—no config required.",
                        },
                        {
                                "label": "Tooling",
                                "title": "Vite + Tailwind",
                                "summary": "Enjoy instant reloads, JSX transforms, and Tailwind classes without wiring the bundler yourself.",
                        },
                        {
                                "label": "Data",
                                "title": "Async loaders",
                                "summary": "Fetch data with `@server` functions that run on Starlette, then hydrate the same props on the client.",
                        },
                        {
                                "label": "API",
                                "title": "Shared helpers",
                                "summary": "pages/api/*.py files share Python utilities with your loaders so modeling stays in one language.",
                        },
                ],
                "commands": [
                        {"label": "Scaffold", "command": "pyxle init my-app"},
                        {"label": "Start dev server", "command": "pyxle dev"},
                        {"label": "Call diagnostics", "command": "curl http://localhost:8000/api/pulse"},
                ],
                "resources": [
                        {
                                "title": "Architecture",
                                "description": "Understand how the CLI, compiler, and dev server fit together.",
                                "href": "https://github.com/shivamsn97/pyxle/blob/main/architecture.md",
                        },
                        {
                                "title": "Tailwind guide",
                                "description": "Customize the Tailwind theme or wire your own PostCSS build when you're ready.",
                                "href": "https://github.com/shivamsn97/pyxle/blob/main/docs/styling/tailwind.md",
                        },
                        {
                                "title": "Deployment",
                                "description": "Use pyxle build + pyxle serve to ship the same page with hashed assets.",
                                "href": "https://github.com/shivamsn97/pyxle/blob/main/docs/deployment/deployment.md",
                        },
                ],
                "telemetry": {
                        "version": __version__,
                        "timestamp": iso_timestamp,
                        "display_time": display_time,
                },
        }


import React, { useEffect, useState } from 'react';
import { Link } from 'pyxle/client';

const THEME_KEY = 'pyxle-theme-preference';

const resolvePreferredTheme = () => {
        if (typeof window === 'undefined') {
                return 'light';
        }
        const stored = window.localStorage.getItem(THEME_KEY);
        if (stored === 'dark' || stored === 'light') {
                return stored;
        }
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

const ThemeToggle = ({ onToggle, theme }) => (
        <button
                type="button"
                onClick={onToggle}
                className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-slate-200/70 bg-white text-slate-900 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 dark:border-slate-700 dark:bg-slate-900 dark:text-white"
                aria-label="Toggle color theme"
        >
                {theme === 'dark' ? (
                        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor" aria-hidden="true">
                                <path d="M21 12.79A9 9 0 0 1 11.21 3 7 7 0 1 0 21 12.79z" />
                        </svg>
                ) : (
                        <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                                <circle cx="12" cy="12" r="4" />
                                <path d="M12 2v2m0 16v2m10-10h-2M4 12H2m15.4-6.4-1.4 1.4M6 18l-1.4 1.4M18 18l-1.4-1.4M7.4 7.4 6 6" />
                        </svg>
                )}
        </button>
);

const StatCard = ({ label, value, hint }) => (
        <div className="rounded-2xl border border-slate-100/80 bg-white/80 p-5 text-slate-900 shadow-md backdrop-blur dark:border-slate-800/80 dark:bg-slate-900/70 dark:text-slate-50">
                <p className="text-xs uppercase tracking-[0.35em] text-slate-400 dark:text-slate-500">{label}</p>
                <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{value}</p>
                {hint && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{hint}</p>}
        </div>
);

const GRID_BACKGROUND_STYLE = {
        backgroundImage:
                "radial-gradient(circle at 50% 0%, rgba(94, 234, 212, 0.35), transparent 45%), " +
                "radial-gradient(circle at 15% 40%, rgba(129, 140, 248, 0.35), transparent 40%), " +
                "url('/branding/pyxle-grid.svg')",
        backgroundSize: '100% 100%, 100% 100%, 320px 320px',
};

const Background = () => (
        <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
                <div className="absolute inset-0 opacity-70 mix-blend-screen dark:opacity-50" style={GRID_BACKGROUND_STYLE} />
                <div className="absolute inset-0 bg-gradient-to-b from-white via-white/80 to-white opacity-80 dark:from-slate-950/90 dark:via-slate-950/60 dark:to-slate-950" />
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-100/30 via-transparent to-indigo-100/30 dark:from-cyan-500/10 dark:via-transparent dark:to-indigo-700/10" />
        </div>
);

export const slots = {};
export const createSlots = () => slots;

export default function Page({ data }) {
        const { hero, highlights, commands, resources, telemetry } = data;
        const [theme, setTheme] = useState('light');

        useEffect(() => {
                if (typeof window === 'undefined') {
                        return undefined;
                }
                const media = window.matchMedia('(prefers-color-scheme: dark)');

                const syncTheme = () => {
                        setTheme(resolvePreferredTheme());
                };

                const handleChange = (event) => {
                        const stored = window.localStorage.getItem(THEME_KEY);
                        if (!stored) {
                                setTheme(event.matches ? 'dark' : 'light');
                        }
                };

                syncTheme();

                if (typeof media.addEventListener === 'function') {
                        media.addEventListener('change', handleChange);
                        return () => media.removeEventListener('change', handleChange);
                }
                media.addListener(handleChange);
                return () => media.removeListener(handleChange);
        }, []);

        useEffect(() => {
                if (typeof document === 'undefined') {
                        return;
                }
                const root = document.documentElement;
                root.classList.toggle('dark', theme === 'dark');
                root.dataset.theme = theme;
                if (typeof window !== 'undefined') {
                        window.localStorage.setItem(THEME_KEY, theme);
                }
        }, [theme]);

        const toggleTheme = () => setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
        const wordmarkSrc = theme === 'dark' ? '/branding/pyxle-wordmark-light.svg' : '/branding/pyxle-wordmark-dark.svg';

        const heroActions = (
                <div className="flex flex-wrap gap-3">
                        <a
                                href={hero.cta.href}
                                className="inline-flex items-center justify-center rounded-full border border-cyan-300/60 bg-gradient-to-r from-cyan-400 to-blue-500 px-5 py-2 text-sm font-medium text-white shadow-lg shadow-cyan-500/30"
                                target="_blank"
                                rel="noreferrer"
                        >
                                {hero.cta.label}
                        </a>
                        <a
                                href="https://pypi.org/project/pyxle/"
                                className="inline-flex items-center justify-center rounded-full border border-slate-200/70 px-5 py-2 text-sm font-medium text-slate-900 transition hover:border-slate-900 dark:border-slate-700 dark:text-white"
                                target="_blank"
                                rel="noreferrer"
                        >
                                View on PyPI
                        </a>
                </div>
        );

        return (
                <div className="relative min-h-screen overflow-hidden bg-gradient-to-b from-slate-50 via-white to-white text-slate-900 antialiased transition-colors dark:from-slate-950 dark:via-slate-950 dark:to-slate-950 dark:text-slate-50">
                        <Background />
                        <div className="relative mx-auto max-w-6xl px-6 py-10 sm:px-10 lg:px-12">
                                        <header className="flex flex-col gap-6 rounded-3xl border border-white/70 bg-white/80 p-6 shadow-lg shadow-blue-500/5 backdrop-blur dark:border-slate-800/80 dark:bg-slate-900/70">
                                                <div className="flex flex-wrap items-center justify-between gap-4">
                                                        <div className="flex items-center gap-3">
                                                                <img src="/branding/pyxle-mark.svg" alt="Pyxle mark" className="h-12 w-12" />
                                                                <img src={wordmarkSrc} alt="Pyxle wordmark" className="h-6" />
                                                        </div>
                                                        <ThemeToggle theme={theme} onToggle={toggleTheme} />
                                                </div>
                                                <div>
                                                        <p className="text-xs uppercase tracking-[0.35em] text-slate-400 dark:text-slate-500">{hero.eyebrow}</p>
                                                        <h1 className="mt-3 text-3xl font-semibold leading-tight text-slate-900 dark:text-white sm:text-4xl">
                                                                {hero.title}
                                                        </h1>
                                                        <p className="mt-3 text-base text-slate-600 dark:text-slate-300">{hero.tagline}</p>
                                                </div>
                                                {heroActions}
                                        </header>

                                        <section className="mt-10 grid gap-6 lg:grid-cols-[3fr,2fr]">
                                                <div className="space-y-4">
                                                        <div className="grid gap-4 md:grid-cols-2">
                                                                {highlights.map((item) => (
                                                                        <article
                                                                                key={item.title}
                                                                                className="rounded-2xl border border-slate-200/70 bg-white/80 p-5 shadow-md shadow-slate-900/5 backdrop-blur transition hover:-translate-y-0.5 dark:border-slate-800/70 dark:bg-slate-900/70"
                                                                        >
                                                                                <p className="text-xs uppercase tracking-[0.35em] text-slate-400 dark:text-slate-500">{item.label}</p>
                                                                                <h2 className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">{item.title}</h2>
                                                                                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{item.summary}</p>
                                                                        </article>
                                                                ))}
                                                        </div>
                                                </div>
                                                <div className="rounded-[28px] border border-slate-200/80 bg-white/90 p-6 shadow-2xl shadow-blue-500/10 backdrop-blur dark:border-slate-800/80 dark:bg-slate-900/80">
                                                        <div className="flex flex-col gap-4">
                                                                <h3 className="text-sm uppercase tracking-[0.3em] text-slate-400 dark:text-slate-500">Project snapshot</h3>
                                                                <StatCard label="Pyxle" value={`v${telemetry.version}`} hint="server + client" />
                                                                <StatCard label="Last refresh" value={telemetry.display_time} hint="UTC" />
                                                                <Link
                                                                        href="/api/pulse"
                                                                        className="inline-flex items-center justify-center rounded-2xl border border-slate-200/80 px-4 py-3 text-sm font-medium text-slate-900 transition hover:border-slate-900 dark:border-slate-700 dark:text-white"
                                                                >
                                                                        View API pulse →
                                                                </Link>
                                                        </div>
                                                </div>
                                        </section>

                                        <section className="mt-12 rounded-3xl border border-slate-200/70 bg-white/80 p-6 shadow-lg shadow-slate-900/5 backdrop-blur dark:border-slate-800/70 dark:bg-slate-900/70">
                                                <div className="flex flex-wrap items-center justify-between gap-4">
                                                        <div>
                                                                <p className="text-xs uppercase tracking-[0.35em] text-slate-400 dark:text-slate-500">Quick commands</p>
                                                                <h2 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Drop these into your terminal</h2>
                                                        </div>
                                                        <span className="rounded-full border border-slate-200/80 px-3 py-1 text-xs font-semibold text-slate-600 dark:border-slate-700 dark:text-slate-300">
                                                                Tailwind ready
                                                        </span>
                                                </div>
                                                <div className="mt-6 grid gap-4 md:grid-cols-3">
                                                        {commands.map((entry) => (
                                                                <div
                                                                        key={entry.command}
                                                                        className="rounded-2xl border border-slate-200/70 bg-slate-900/5 p-4 font-mono text-sm text-slate-900 dark:border-slate-800/70 dark:bg-white/5 dark:text-slate-100"
                                                                >
                                                                        <p className="text-xs uppercase tracking-[0.35em] text-slate-400 dark:text-slate-500">{entry.label}</p>
                                                                        <code className="mt-2 block text-base">{entry.command}</code>
                                                                </div>
                                                        ))}
                                                </div>
                                        </section>

                                        <section className="mt-12">
                                                <div className="rounded-3xl border border-slate-200/70 bg-white/80 p-6 shadow-lg shadow-slate-900/5 backdrop-blur dark:border-slate-800/70 dark:bg-slate-900/70">
                                                        <div className="flex flex-wrap items-center justify-between gap-4">
                                                                <div>
                                                                        <p className="text-xs uppercase tracking-[0.35em] text-slate-400 dark:text-slate-500">Keep exploring</p>
                                                                        <h2 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Resources you’ll want next</h2>
                                                                </div>
                                                                <a
                                                                        href="https://github.com/shivamsn97/pyxle"
                                                                        className="inline-flex items-center justify-center rounded-full border border-slate-200/80 px-4 py-2 text-sm font-medium text-slate-900 transition hover:border-slate-900 dark:border-slate-700 dark:text-white"
                                                                        target="_blank"
                                                                        rel="noreferrer"
                                                                >
                                                                        GitHub →
                                                                </a>
                                                        </div>
                                                        <div className="mt-6 grid gap-4 md:grid-cols-3">
                                                                {resources.map((resource) => (
                                                                        <article
                                                                                key={resource.href}
                                                                                className="rounded-2xl border border-slate-200/70 bg-gradient-to-br from-white to-slate-50/60 p-5 shadow-inner shadow-white/40 dark:border-slate-800/70 dark:from-slate-900 dark:to-slate-900/60"
                                                                        >
                                                                                <h3 className="text-lg font-semibold text-slate-900 dark:text-white">{resource.title}</h3>
                                                                                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{resource.description}</p>
                                                                                <a
                                                                                        href={resource.href}
                                                                                        className="mt-3 inline-flex items-center gap-2 text-sm font-medium text-cyan-600 hover:text-cyan-500 dark:text-cyan-300"
                                                                                >
                                                                                        Read more →
                                                                                </a>
                                                                        </article>
                                                                ))}
                                                        </div>
                                                </div>
                                        </section>
                        </div>
                </div>
        );
}
