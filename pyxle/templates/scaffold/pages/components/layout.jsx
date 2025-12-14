import React from 'react';
import { Link as RouterLink } from 'pyxle/client';

const externalTarget = (href) => (typeof href === 'string' && href.startsWith('http') ? '_blank' : undefined);

export function Link({ href, children, variant = 'ghost', isActive = false }) {
	const classes = ['pyxle-link'];
	if (variant === 'primary') {
		classes.push('pyxle-link--primary');
	}
	if (isActive) {
		classes.push('pyxle-link--active');
	}

	return (
		<RouterLink className={classes.join(' ')} href={href} rel="noreferrer" target={externalTarget(href)}>
			{children}
		</RouterLink>
	);
}

const DEFAULT_NAV = [
	{ href: 'https://github.com/shivamshekhar/pyxle', label: 'GitHub' },
	{ href: 'https://github.com/shivamshekhar/pyxle/tree/main/docs', label: 'Docs' },
	{ href: 'https://github.com/shivamshekhar/pyxle/tree/main/tasks', label: 'Roadmap' },
];

export function RootLayout({ children, site, currentPath }) {
	const navItems = site?.navigation?.length ? site.navigation : DEFAULT_NAV;
	const resources = site?.resources ?? [];
	const tagline = site?.tagline ?? 'Python loaders + React SSR';

	return (
		<div className="pyxle-shell">
			<header className="pyxle-shell__nav">
				<div className="pyxle-shell__brand">
					<div className="pyxle-shell__logo">
						<span className="pyxle-shell__logo-burst" aria-hidden="true" />
						<strong>Pyxle</strong>
						<span className="pyxle-shell__logo-tag">starter</span>
					</div>
					<p className="pyxle-shell__tagline">{tagline}</p>
				</div>
				<nav className="pyxle-shell__links" aria-label="Primary">
					{navItems.map((item) => {
						const isInternal = typeof item.href === 'string' && item.href.startsWith('/');
						return (
							<Link key={item.href} href={item.href} isActive={isInternal && currentPath === item.href}>
								{item.label}
							</Link>
						);
					})}
				</nav>
			</header>
			<main className="pyxle-shell__main">{children}</main>
			<footer className="pyxle-shell__footer">
				<span>
					Edit <code>pages/*.pyx</code> to customize this multi-page starter.
				</span>
				<div className="pyxle-shell__footer-links">
					{resources.map((resource) => (
						<Link key={resource.href} href={resource.href}>
							{resource.label}
						</Link>
					))}
				</div>
			</footer>
		</div>
	);
}

export function SectionLabel({ eyebrow, title, description }) {
	return (
		<div>
			<p className="pyxle-section__heading">{eyebrow}</p>
			<h2 className="pyxle-section__title">{title}</h2>
			<p className="pyxle-section__description">{description}</p>
		</div>
	);
}
