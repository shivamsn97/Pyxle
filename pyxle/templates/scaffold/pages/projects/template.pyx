import React from 'react';
import { Slot } from 'pyxle/client';
import { Link } from '../components/layout.jsx';

const TemplateHero = ({ data }) => {
    const page = data?.page ?? {};
    return (
        <section className="pyxle-hero pyxle-hero--projects">
            <div className="pyxle-hero__inner">
                {page.eyebrow && <p className="pyxle-hero__eyebrow">{page.eyebrow}</p>}
                <h1 className="pyxle-hero__title">{page.title}</h1>
                <p className="pyxle-hero__tagline">{page.intro}</p>
                <div className="pyxle-hero__actions">
                    <Link href="/" variant="ghost">
                        Overview
                    </Link>
                    <Link href="/diagnostics">Diagnostics</Link>
                </div>
            </div>
        </section>
    );
};

export const slots = {
    hero: ({ data }) => <TemplateHero data={data} />,
};

export default function ProjectsTemplate({ children, data }) {
    return (
        <div className="pyxle-template pyxle-template--projects">
            <div className="pyxle-template__hero">
                <Slot name="hero" props={{ data }} fallback={<TemplateHero data={data} />} />
            </div>
            <div className="pyxle-template__body">{children}</div>
        </div>
    );
}
