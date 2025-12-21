# Pyxle Documentation

Pyxle embraces the "everything in one file" ergonomics of Next.js while keeping authoring purely in Python and React. This folder organizes the platform into small, focused guides so you can hop straight to the feature you care about without wading through a monolith. Each page mirrors an equivalent Next.js concept and links back to the source so you can verify behaviour against the implementation.

## How to navigate

- **Overview**
  - [What is Pyxle?](overview/what-is-pyxle.md)
  - [Project structure](overview/project-structure.md)
- **Fundamentals**
  - [Authoring `.pyx` files](fundamentals/pyx-files.md)
  - [Loader ↔ component lifecycle](fundamentals/loader-lifecycle.md)
- **Routing & navigation**
  - [File-based routing](routing/file-based-routing.md)
  - [Dynamic segments & catch-alls](routing/dynamic-segments.md)
  - [Layouts and slots](routing/layouts-and-slots.md)
  - [Client navigation + `<Link>`](routing/client-navigation.md)
- **Data & middleware**
  - [Server loaders](data/server-loaders.md)
  - [API routes](data/api-routes.md)
  - [Custom middleware & route hooks](data/middleware-hooks.md)
- **Styling**
  - [Tailwind workflow](styling/tailwind.md)
  - [Global styles & scripts](styling/global-styles-and-scripts.md)
- **Runtime behaviours**
  - [Head management](runtime/head-management.md)
  - [Pyxle client runtime](runtime/pyxle-client.md)
- **Dev server**
  - [How the dev server works](devserver/dev-server.md)
  - [Overlay, watcher, and diagnostics](devserver/overlay-and-watchers.md)
- **Build & deploy**
  - [Production build pipeline](build/production-build.md)
  - [`pyxle serve` and SSR runtime](build/serve-command.md)
- **Reference**
  - [CLI commands](reference/cli.md)
  - [Configuration file](reference/config.md)
- **Deployment**
  - [Deploying Pyxle apps](deployment/deployment.md)
- **Tooling**
  - [LangKit, LSP, and editor support](tooling/langkit.md)
  - [Testing strategy](tooling/testing.md)
- **Internals**
  - [Compiler architecture](internals/compiler.md)
  - [SSR renderer](internals/ssr.md)

Every page calls out the matching Next.js mental model under "Compare with Next.js" and links to implementation anchors so you can dive deeper when something looks off.
