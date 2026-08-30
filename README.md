# Event Suggester — The Lasallian (Edge Edition)

> **React + Cloudflare Workers/Pages + D1 (SQLite) + Authentik OIDC** — no Next.js.  
> Collated from AY 25-26 sheet (**140 events** — 139 sheet + Start of Term 1 added as undated) + 45 verified new candidates = **185-event database**. Every event verified one-at-a-time via subagents.

Source sheet: `https://docs.google.com/spreadsheets/d/e/2PACX-1vSiKyKDTVW1-r2p98yIkIceQrV7jnHVKP3vd-eJQLkYakTYXHj2ucsxDgMYDoPBwl3wANpfFh3ykD8x/pub?output=xlsx`

---

## 1. What changed per your feedback

| Ask | Change |
|-----|--------|
| **No Next.js, edge preferred** | **Vite + React Router** SPA on **Cloudflare Pages** (static) + **Cloudflare Workers (Hono) API** + **D1** for DB. All compute on edge, `dateEngine.ts` runs client + worker. |
| **Cloudflare DB** | **D1 (SQLite)** — schema in `drizzle.schema.ts` (preferred) and `schema.prisma` (SQLite mode) — no Postgres, no `Json` columns, `month` nullable. |
| **Authentik on React** | OIDC PKCE via `oidc-client-ts` / `react-oidc-context` against `auth.tls.local` (Authentik). Worker validates JWT via JWKS. |
| **Include Start of Term 1 + 9 Sept events** | Added **Start of Term 1** as `undated` pool item; enriched the 9 Sept events you listed with founding years (see §2). All 10 now in `seed.json`. |
| **Terms have no set date** | All `Start of Term 1/2/3` are now `logic=undated, month=null, isUndated=true` — they live in the **Undated Pool**, not September. You can still add them to any month's issue manually. |
| **Support date-less pool** | DB allows `month=null`; UI has dedicated **Undated Pool** section; API `POST /events` lets editors add custom pool items without date. |
| **Prio by anniversary “nice numbers”** | `prioScore()` in `drizzle.schema.ts` + `dateEngine.ts` — 100/80/60/40/20/5 tiers. September view sorted by `prioScore desc → anniversary desc → title`. Toggle for other sorts. |
| **Shared state, 1+ users** | Single `MonthlyIssue(year,month)` row, `version` optimistic locking, last-write-wins for picks. No per-user isolation. `addedBy` tracks who added. |

---

## 2. September + Undated — the 10 you flagged

All 9 September events already in sheet, now enriched + verified:

| Event | Sheet date | Logic | Founded | 2026 anniversary | Prio |
|-------|------------|-------|---------|------------------|------|
| **Nativity of the Blessed Virgin Mary** | Sep 8 | `fixed` (Sep 8) | ~500 (Jerusalem) | — | — |
| **Anniversary of the Official Gazette** | Sep 10 | `fixed` (Sep 10) | **1902** (Act 453) — sheet 1901 was wrong | **124th** | 5 |
| **World Suicide Prevention Day** | Sep 10 | `fixed` (Sep 10) | **2003** IASP/WHO | **23rd** | 5 |
| **Grandparents Day** | Sep 14* | `movable_nth` 2nd Sun Sep | 1978 (US), 1987 PH adoption | — | — |
| **International Ozone Day** | Sep 16 | `fixed` (Sep 16) | **1994** UNGA 49/114 (Montreal Protocol 1987) | 32nd | 5 |
| **First Paralympic Games** | Sep 18 | `fixed` (Sep 18-25) | **1960** Rome | **66th** | 5 |
| **Martial Law Anniversary** | Sep 21 | `fixed` (Sep 21 dated / Sep23 announced) | **1972** Proc 1081 | **54th** | 5 |
| **World Alzheimer's Day** | Sep 21 | `fixed` (Sep 21) | **1994** ADI/WHO | 32nd | 5 |
| **International Day of Sign Languages** | Sep 23 | `fixed` (Sep 23) | **2018** UNGA 72/161 | **8th** | 5 |

*Grandparents Day sheet says Sep 14 but 2nd Sun Sep 2026 = **Sep 13** — fixed.

**Undated pool (no month/day):**

| Event | Logic | Category | Notes |
|-------|-------|----------|-------|
| **Start of Term 1** | `undated` | DLSU | DLSU Academic Calendar — varies yearly |
| **Start of Term 2** | `undated` | DLSU | was Jan 5 fixed → now pool |
| **Start of Term 3** | `undated` | DLSU | was May 11 fixed → now pool |

You can add more undated items (e.g., “TBA: UAAP Finals”) via `POST /events { isUndated:true }` — they appear in the pool until assigned to a month.

---

## 3. Architecture — Edge

```
[Browser: Vite React SPA]  --oidc PKCE-->  [Authentik]
        |                                      | JWKS
        v                                     /
[Cloudflare Pages]  -->  [Cloudflare Worker (Hono)]  -->  [D1 — tls-events]
        |                    |  dateEngine.ts
        |                    +-- GET /api/suggestions?year=2026&month=9  (computed)
        |                    +-- GET /api/pool?undated=1
        |                    +-- POST /api/issues/:year/:month/picks  (shared state, version check)
        |                    +-- POST /api/events  (add undated custom)
        +---------------------> static assets (edge cached)
```

**Stack specifics:**

- **Frontend:** Vite + React 18 + React Router + Tailwind + shadcn/ui + `react-oidc-context` (Authentik provider). No SSR. `VITE_OIDC_AUTHORITY=https://auth.tls.local/application/o/tls-suggester/`, `VITE_API_URL=https://api.tls.local`.
- **API:** Hono on Workers, `wrangler.toml` with `d1_databases = [{binding="DB", database_name="tls-events"}]`. Routes are edge-native, no Node.
- **DB:** D1 SQLite — see `drizzle.schema.ts` (preferred) or `schema.prisma` (SQLite mode with `driverAdapters`). `month` nullable, `ruleJson`/`tags` as TEXT JSON, `isUndated` flag.
- **Auth:** Authentik OIDC Authorization Code + PKCE. Worker middleware verifies `Authorization: Bearer <id_token>` via Authentik JWKS (`/.well-known/jwks.json`). RBAC via Authentik groups (`tls-editors`, `tls-admin`). Pages protected via `OidcSecure` wrapper.
- **Deploy:** `wrangler pages deploy dist` + `wrangler d1 migrations apply tls-events`. Existing ansible can proxy `api.tls.local` to Worker or use Cloudflare tunnel.

**Why not Next.js:** avoids Node server, keeps everything on Cloudflare edge (cheaper, faster cold start, same `dateEngine.ts` on client and worker).

---

## 4. Data Model (D1)

```ts
// drizzle.schema.ts — key table
events {
  id, slug, title, description,
  category,           // GLOBAL | PHILIPPINES | MANILA | DLSU | TLS
  logic,              // fixed | movable_nth | ... | undated | tba_*
  month: integer|null, // null = undated pool
  day: integer|null,
  ruleJson: text|null, // {nth, weekday} or {anchor:"EASTER", offset:49}
  isUndated: boolean,
  isTba: boolean, tbaSource,
  foundedYear, foundedAuthority,
  tags, typeOfVisual, sourceUrl, notionUrl
}
occurrences { eventId, year, date, isTba, isMilestone, anniversary, prioScore }
monthly_issues { year, month, status, version } // version for optimistic locking
monthly_picks { issueId, eventId, status, priority, artist, notes, addedBy }
```

Prisma SQLite equivalent in `schema.prisma` — same shape, `String` ISO dates, `String?` JSON.

---

## 5. Priority Scoring + Sorting

```ts
// drizzle.schema.ts / lib/dateEngine.ts
function prioScore(anniv: number | null): number {
  if (anniv == null) return 0
  if (anniv % 100 === 0) return 100 // centennial
  if (anniv % 50 === 0)  return 80  // golden
  if (anniv % 25 === 0)  return 60  // silver 25
  if (anniv % 10 === 0)  return 40  // decade
  if (anniv % 5 === 0)   return 20  // 5-year
  return 5
}
```

**September view default sort:** `prioScore desc, anniversary desc, title asc` — so 10/25/50/100 pop to top, but toggleable to `date asc | category | prioScore`. Undated pool is **always separate** below, sorted by `relevanceTier` + `prioScore`.

Milestone badge: `isMilestone = prioScore >= 20` (5-year multiples).

---

## 6. Flow — “It’s September”

1. Editor opens `/2026/09` (or current `new Date()`).  
   Worker runs `GET /api/suggestions?year=2026&month=9` → computes occurrences for all `month=9` events via `dateEngine` (fixed + nth + lunar estimates) + `prioScore` + `isMilestone` — returns sorted list.
2. **Main list:** September-dated suggestions (9 events + any other September logics). Cards show: title, computed date (e.g., “Sep 13 — 2nd Sun”), anniversary badge (e.g., “124th”), TBA flag, category chip.
3. **Undated Pool:** collapsed section below: Start of Term 1/2/3 + any custom pool items (no date) + `+ Add to pool` form (title, category, notes — no date required).
4. **Sort controls:** `[Prio ▼] [Date] [Category]` — prio is default. Editor drags/clicks `Add →` to move an item to the right **Issue** column.
5. **Issue column (shared state):** `MonthlyIssue 2026-09` row + `MonthlyPick` children. On `Add`, `POST /api/issues/2026/09/picks { eventId, addedBy }` with `If-Match: version` — increments `version` on success, broadcasts via polling (or Workers WebSocket / Durable Object). All users see same list (last-write-wins, conflict 409 → refetch).
6. **Create issue:** `POST /api/issues { year:2026, month:9 }` auto-creates from template if not exists (clones previous year's picks as “suggested”). Editor can set `deadline`/`artist`/`notes` per pick, mark `deferred`.
7. Export to Google Sheets/Notion stays as `GET /api/issues/2026/09/export?format=sheets`.

No per-user private state — single shared pick list per `(year,month)`.

---

## 7. Auth — Authentik on React

```ts
// src/auth.ts
import { AuthProvider } from "react-oidc-context";
<AuthProvider
  authority="https://auth.tls.local/application/o/tls-suggester/"
  client_id="tls-suggester"
  redirect_uri={window.location.origin}
  scope="openid profile email"
  onSigninCallback={() => window.history.replaceState({}, "", "/")}
/>
```

Worker: `middleware/auth.ts` fetches `https://auth.tls.../.well-known/jwks.json` (cached), verifies `id_token`, checks `groups includes tls-editors`.

---

## 8. Files

- `drizzle.schema.ts` — D1 schema + `prioScore()`
- `schema.prisma` — Prisma SQLite (alt, driverAdapters)
- `dateEngine.ts` — Easter, nth-weekday, lunar, `prioScore`
- `seed.json` — 185 records (140 existing + 45 new) with `month:null` for undated
- `wrangler.toml` (to create) — `d1_databases`, `vars { OIDC_ISSUER }`
- `src/pages/MonthView.tsx` — September + undated pool + prio sort

## 9. Next Steps

```bash
npm create vite@latest tls-suggester -- --template react-ts
npm i hono drizzle-orm react-router-dom react-oidc-context oidc-client-ts
npm i -D wrangler drizzle-kit @cloudflare/workers-types
wrangler d1 create tls-events
wrangler d1 migrations apply tls-events
npm run dev # Vite on 5173, worker via `wrangler dev --local`
```

Seed: `wrangler d1 execute tls-events --file=./seed.sql` (generate via `drizzle-kit generate` from `seed.json`).

---

*Updated 2026-08-30 — edge rewrite per feedback.*
