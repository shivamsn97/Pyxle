from pages.components.site import base_page_payload, build_page_head

HEAD = build_page_head(
    "Not found",
    description="Catch missing routes gracefully and guide folks back to the homepage.",
)


@server
async def load_not_found(request):
    payload = base_page_payload(
        request,
        page_id="not-found",
        title="We couldn't find that page.",
        intro="The link might be outdated or the page was removed. Use the button below to jump back home.",
        eyebrow="404",
    )
    return payload, 404


import React from 'react';
import { Link } from './components/layout.jsx';

const NotFoundHero = ({ page }) => (
    <section className="pyxle-hero pyxle-hero--minimal">
        <div className="pyxle-hero__inner">
            {page.eyebrow && <p className="pyxle-hero__eyebrow">{page.eyebrow}</p>}
            <h1 className="pyxle-hero__title">{page.title}</h1>
            <p className="pyxle-hero__tagline">{page.intro}</p>
            <div className="pyxle-hero__actions">
                <Link href="/" variant="primary">
                    Back to home
                </Link>
            </div>
        </div>
    </section>
);

export const slots = {
    hero: ({ data }) => <NotFoundHero page={data.page} />,
};

export default function NotFoundPage({ data }) {
    const { page } = data;
    return (
        <section className="pyxle-section">
            <p className="pyxle-section__heading">Need a fresh link?</p>
            <p className="pyxle-section__description">
                The request path <code>{page.path}</code> did not match an existing route. Update{' '}
                <code>pages/[...slug].pyx</code> to tailor this fallback or add new segments under{' '}
                <code>pages/</code>.
            </p>
        </section>
    );
}
