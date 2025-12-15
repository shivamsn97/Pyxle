from datetime import datetime, timezone

from pages.api.pulse import build_pulse_payload
from pages.components.site import base_page_payload, build_page_head

HEAD = build_page_head(
    "Diagnostics",
    description="Validate middleware state and observe the live /api/pulse response without leaving the starter project.",
)


@server
async def load_diagnostics(request):
    payload = base_page_payload(
        request,
        page_id="diagnostics",
        title="Inspect middleware headers and the sample API.",
        intro="Use this route when you want to confirm request state, middleware metadata, or the JSON payload emitted by pages/api/pulse.py.",
        eyebrow="DIAGNOSTICS",
    )
    middleware_context = getattr(request.state, "pyxle_demo", {})
    issued_at = middleware_context.get("issuedAt", datetime.now(tz=timezone.utc).isoformat())
    payload["middleware"] = {
        "requestId": middleware_context.get("requestId", "enable-pyxle-middleware"),
        "issuedAt": issued_at,
        "path": middleware_context.get("path", request.url.path),
        "header": "x-pyxle-demo",
    }
    payload["api"] = {
        "endpoint": "/api/pulse",
        "prefill": build_pulse_payload(),
        "notes": [
            "The loader shares utilities with the API via build_pulse_payload().",
            "Use route middleware or API middleware via pyxle.config.json when you need per-route hooks.",
        ],
    }
    payload["page"]["notes"] = [
        "Telemetry middleware stores per-request state on request.state.pyxle_demo.",
        "Starlette routes live in pages/api/* and automatically import next to your pages.",
    ]
    return payload


import React, { useEffect, useState } from 'react';
import { SectionLabel } from './components/layout.jsx';

const MiddlewarePanel = ({ middleware }) => (
    <div className="pyxle-middleware">
        <dl>
            <dt>Request</dt>
            <dd>{middleware.requestId}</dd>
            <dt>Issued</dt>
            <dd>{middleware.issuedAt}</dd>
            <dt>Path</dt>
            <dd>{middleware.path}</dd>
            <dt>Header</dt>
            <dd>{middleware.header}</dd>
        </dl>
    </div>
);

const ApiPulse = ({ endpoint, prefill, notes }) => {
    const [payload, setPayload] = useState(prefill);
    const [status, setStatus] = useState('prefilled');

    useEffect(() => {
        let cancelled = false;

        const refresh = async () => {
            try {
                const response = await fetch(endpoint, {
                    headers: { 'x-pyxle-demo': 'pulse' },
                });
                const data = await response.json();
                if (!cancelled) {
                    setPayload(data);
                    setStatus('live');
                }
            } catch (error) {
                if (!cancelled) {
                    setStatus('offline');
                }
            }
        };

        refresh();
        const interval = setInterval(refresh, 8000);
        return () => {
            cancelled = true;
            clearInterval(interval);
        };
    }, [endpoint]);

    const latestRequest = payload.request || {};

    return (
        <div className="pyxle-pulse">
            <div className="pyxle-pulse__panel">
                <p className="pyxle-section__heading">API pulse</p>
                <div className="pyxle-pulse__values">
                    <div>
                        <p className="pyxle-card__label">Pyxle</p>
                        <p className="pyxle-pulse__value">{payload.pyxleVersion}</p>
                    </div>
                    <div>
                        <p className="pyxle-card__label">Python</p>
                        <p className="pyxle-pulse__value">{payload.python}</p>
                    </div>
                    <div>
                        <p className="pyxle-card__label">Uptime</p>
                        <p className="pyxle-pulse__value">{payload.uptime}</p>
                    </div>
                </div>
                <p className="pyxle-pulse__meta">Host: {payload.hostname} · PID: {payload.pid}</p>
                <p className="pyxle-pulse__meta">Updated: {payload.timestamp}</p>
                <p className="pyxle-pulse__live">Status: {status}</p>
                <ul>
                    {notes.map((note) => (
                        <li key={note}>{note}</li>
                    ))}
                </ul>
            </div>
            <div className="pyxle-pulse__panel">
                <p className="pyxle-section__heading">Available features</p>
                <ul>
                    {(payload.features || []).map((feature) => (
                        <li key={feature}>{feature}</li>
                    ))}
                </ul>
                <p className="pyxle-pulse__meta">
                    Latest request from {latestRequest.client || 'unknown'} over {latestRequest.method || 'GET'}.
                </p>
            </div>
        </div>
    );
};

const PageHero = ({ page }) => (
    <section className="pyxle-hero">
        <div className="pyxle-hero__inner">
            {page.eyebrow && <p className="pyxle-hero__eyebrow">{page.eyebrow}</p>}
            <h1 className="pyxle-hero__title">{page.title}</h1>
            <p className="pyxle-hero__tagline">{page.intro}</p>
            <ul>
                {(page.notes || []).map((note) => (
                    <li key={note}>{note}</li>
                ))}
            </ul>
        </div>
    </section>
);

export const slots = {
    hero: ({ data }) => <PageHero page={data.page} />,
};

export const createSlots = () => slots;

export default function Page({ data }) {
    const { middleware, api } = data;
    return (
        <>
            <section className="pyxle-section">
                <SectionLabel
                    eyebrow="MIDDLEWARE"
                    title="Configured in pyxle.config.json"
                    description="middlewares/telemetry.py assigns request IDs and headers so you can trace interactions."
                />
                <MiddlewarePanel middleware={middleware} />
            </section>

            <section className="pyxle-section">
                <SectionLabel
                    eyebrow="API"
                    title="pages/api/pulse.py"
                    description="Starlette-compatible endpoints can be fetched from loaders or the browser."
                />
                <ApiPulse endpoint={api.endpoint} prefill={api.prefill} notes={api.notes} />
            </section>
        </>
    );
}
