# Fundamentals

After the overview, learn how Pyxle merges async Python loaders with React function components.

## You will learn

- The `.pyx` file format, module-level `HEAD`, and supported decorators.
- How loader return values become props and status codes.
- Patterns for sharing Python helpers and React hooks between files.

## Helpful snippets

```py
# pages/dashboard.pyx
from pyxle import server
from httpx import AsyncClient

@server
async def load_dashboard(request):
    async with AsyncClient(base_url="https://api.example.com") as client:
        summary = (await client.get("/summary")).json()
    return {"summary": summary, "user": request.state.user}, 200
```

```jsx
export default function Dashboard({ data }) {
    const { summary, user } = data;
    return (
        <section>
            <h1>Hello {user.name}</h1>
            <pre>{JSON.stringify(summary, null, 2)}</pre>
        </section>
    );
}
```

## Pages in this section

1. [Authoring `.pyx` files](pyx-files.md)
2. [Loader ↔ component lifecycle](loader-lifecycle.md)

---
**Navigation:** [← Previous](../overview/project-structure.md) | [Next →](pyx-files.md)
