from pages.components.site import base_page_payload, build_page_head

HEAD = build_page_head(
        "Overview",
        description="Pick a starter route to explore how Pyxle blends Python loaders, React components, middleware, and APIs.",
)


@server
async def load_home(request):
        payload = base_page_payload(
                request,
                page_id="overview",
                title="Start with three ready-to-edit pages.",
                intro="Each route highlights a different layer of the stack so you can explore loaders, middleware, and APIs immediately.",
                eyebrow="WELCOME",
        )
        payload["hero"] = {
                "actions": [
                        {"href": "https://pypi.org/project/pyxle", "label": "View on PyPI", "variant": "primary"},
                        {"href": "https://github.com/shivamshekhar/pyxle", "label": "GitHub"},
                ],
        }
        payload["routes"] = [
                {
                        "href": "/projects",
                        "title": "Projects",
                        "summary": "Walk through the loader → React workflow and copy ready-made commands.",
                        "cta": "Open projects",
                        "variant": "primary",
                },
                {
                        "href": "/diagnostics",
                        "title": "Diagnostics",
                        "summary": "Inspect middleware state and watch the /api/pulse endpoint update in real time.",
                        "cta": "Open diagnostics",
                        "variant": "primary",
                },
                {
                        "href": "/api/pulse",
                        "title": "API pulse",
                        "summary": "Call the Starlette route directly to see the JSON payload your loaders can reuse.",
                        "cta": "Call API",
                },
        ]
        return payload


import React from 'react';
import { Link } from './components/layout.jsx';

const RouteList = ({ routes }) => (
        <ul className="pyxle-home__nav">
                {routes.map((route) => (
                        <li key={route.href}>
                                <strong>{route.title}</strong>
                                <p>{route.summary}</p>
                                <Link href={route.href} variant={route.variant ?? 'ghost'}>
                                        {route.cta || 'Open page'}
                                </Link>
                        </li>
                ))}
        </ul>
);

const HomeHero = ({ data }) => {
        const { page, hero } = data;
        return (
                <section className="pyxle-hero pyxle-hero--minimal">
                        <div className="pyxle-hero__inner">
                                {page.eyebrow && <p className="pyxle-hero__eyebrow">{page.eyebrow}</p>}
                                <h1 className="pyxle-hero__title">{page.title}</h1>
                                <p className="pyxle-hero__tagline">{page.intro}</p>
                                <div className="pyxle-hero__actions">
                                        {hero.actions.map((action) => (
                                                <Link key={action.href} href={action.href} variant={action.variant ?? 'ghost'}>
                                                        {action.label}
                                                </Link>
                                        ))}
                                </div>
                        </div>
                </section>
        );
};

export const slots = {
        hero: ({ data }) => <HomeHero data={data} />,
};

export const createSlots = () => slots;

export default function Page({ data }) {
        const { routes } = data;
        return (
                <section className="pyxle-section">
                        <p className="pyxle-section__heading">Start exploring</p>
                        <RouteList routes={routes} />
                </section>
        );
}
