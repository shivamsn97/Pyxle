import React from 'react';
import { Slot } from 'pyxle/client';
import { Link, RootLayout } from './components/layout.jsx';

const DefaultHero = ({ data }) => {
    const page = data?.page ?? {};
    return (
        <section className="pyxle-hero pyxle-hero--minimal">
            <div className="pyxle-hero__inner">
                {page.eyebrow && <p className="pyxle-hero__eyebrow">{page.eyebrow}</p>}
                <h1 className="pyxle-hero__title">{page.title || 'Pyxle starter'}</h1>
                <p className="pyxle-hero__tagline">{page.intro || 'Edit pages/*.pyx to customize loaders, components, and middleware.'}</p>
                <div className="pyxle-hero__actions">
                    <Link href="/projects" variant="primary">
                        Explore projects
                    </Link>
                    <Link href="/diagnostics">Diagnostics</Link>
                </div>
            </div>
        </section>
    );
};

export const slots = {};
export const createSlots = () => slots;

export default function AppLayout({ children, data }) {
    const site = data?.site;
    const page = data?.page;
    return (
        <RootLayout site={site} currentPath={page?.path}>
            <Slot name="hero" props={{ data }} fallback={<DefaultHero data={data} />} />
            <div className="pyxle-shell__sections">{children}</div>
        </RootLayout>
    );
}
