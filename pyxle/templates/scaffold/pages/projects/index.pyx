from pages.components.site import base_page_payload, build_page_head
from pyxle import __version__

HEAD = build_page_head(
    "Projects",
    description="Understand how loaders feed React components and copy the workflow commands you need to ship quickly.",
)


@server
async def load_projects(request):
    payload = base_page_payload(
        request,
        page_id="projects",
        title="Map the workflow from loader to deploy.",
        intro="This page steps through the default stack so you can edit any block or reuse the commands elsewhere.",
        eyebrow="PROJECT WALKTHROUGH",
    )
    payload["page"].update(
        {
            "version": __version__,
            "heroActions": [
                {"href": "/diagnostics", "label": "Diagnostics", "variant": "primary"},
                {"href": "/", "label": "Overview"},
            ],
        }
    )
    payload["stack"] = [
        {
            "label": "Loader",
            "title": "Async data",
            "description": "The @server function above this component runs before render, returning props for hydrated UI.",
            "meta": "pages/projects/index.pyx · load_projects",
        },
        {
            "label": "React",
            "title": "Client + server",
            "description": "JSX sits beside Python so you can render once for SSR and hydrate the same tree in the browser.",
            "meta": "pages/projects/index.pyx · Page",
        },
        {
            "label": "API",
            "title": "Starlette routes",
            "description": "pages/api/pulse.py responds with live metadata and is reusable from loaders or browsers.",
            "meta": "pages/api/pulse.py",
        },
        {
            "label": "Middleware",
            "title": "Project hooks",
            "description": "middlewares/telemetry.py stamps headers + request IDs configured via pyxle.config.json.",
            "meta": "middlewares/telemetry.py",
        },
    ]
    payload["commands"] = [
        {"label": "Scaffold", "command": "pyxle init my-app"},
        {"label": "Install deps", "command": "pip install -r requirements.txt"},
        {"label": "Install client", "command": "npm install"},
        {"label": "Run dev server", "command": "pyxle dev"},
        {"label": "Call API", "command": "curl http://localhost:8000/api/pulse"},
    ]
    return payload


import React from 'react';
import { Link, SectionLabel } from '../components/layout.jsx';

const FeatureGrid = ({ items }) => (
    <div className="pyxle-grid__cards">
        {items.map((item) => (
            <article className="pyxle-card" key={item.title}>
                <span className="pyxle-card__label">{item.label}</span>
                <h3 className="pyxle-card__title">{item.title}</h3>
                <p>{item.description}</p>
                <span className="pyxle-card__meta">{item.meta}</span>
            </article>
        ))}
    </div>
);

const CommandList = ({ commands }) => (
    <div className="pyxle-commands">
        {commands.map((command) => (
            <button
                key={command.label}
                type="button"
                className="pyxle-command"
                data-pyxle-command={command.command}
            >
                <strong>{command.label}</strong>
                <div>{command.command}</div>
            </button>
        ))}
    </div>
);

const PageHero = ({ page }) => (
    <section className="pyxle-hero">
        <div className="pyxle-hero__inner">
            {page.eyebrow && <p className="pyxle-hero__eyebrow">{page.eyebrow}</p>}
            <h1 className="pyxle-hero__title">{page.title}</h1>
            <p className="pyxle-hero__tagline">{page.intro}</p>
            <p className="pyxle-pulse__live">v{page.version}</p>
            <div className="pyxle-hero__actions">
                {page.heroActions.map((action) => (
                    <Link key={action.href} href={action.href} variant={action.variant}>
                        {action.label}
                    </Link>
                ))}
            </div>
        </div>
    </section>
);

export const slots = {
    hero: ({ data }) => <PageHero page={data.page} />,
};

export const createSlots = () => slots;

export default function Page({ data }) {
    const { stack, commands } = data;
    return (
        <>
            <section className="pyxle-section">
                <SectionLabel
                    eyebrow="BUILDING BLOCKS"
                    title="Everything Pyxle ships on day one"
                    description="Single-file authoring mixes Python + React, while middleware and APIs stay in the same repo."
                />
                <FeatureGrid items={stack} />
            </section>

            <section className="pyxle-section">
                <SectionLabel
                    eyebrow="WORKFLOW"
                    title="From scaffold to shipping"
                    description="Copy any command to your clipboard or wire them into package.json scripts."
                />
                <CommandList commands={commands} />
            </section>
        </>
    );
}
