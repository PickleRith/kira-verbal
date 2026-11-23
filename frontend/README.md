# Kira Verbal frontend

Next.js (App Router) + TypeScript + Tailwind. See the root [README](../README.md) for setup.

```bash
npm install
npm run dev     # http://localhost:3000
npm run lint
npm run build
```

Tailwind is pinned to 4.1.18 because the newest 4.x (4.3.5 tested) depends on an ESM-only
package (`magic-string` 1.x) that Node 20.15 cannot `require()`, which breaks `next build`. After upgrading to Node 22 LTS the pin can be lifted.
