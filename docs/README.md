# MoneyMatch — Docs Index

| Area | Doc | What it answers |
| --- | --- | --- |
| **Build state** | [`implementation-guide/implementation-summary.md`](./implementation-guide/implementation-summary.md) | What the MVP is as built: architecture, stack, features, invariants |
| Build state | [`implementation-guide/BACKLOG.md`](./implementation-guide/BACKLOG.md) | Pending / not-yet-built work |
| Decisions | [`decisions.md`](./decisions.md) | Settled "do not relitigate" architecture & product decisions + why |
| Design | [`design-guidelines.md`](./design-guidelines.md) | The design system the UI follows: tokens, type, components, patterns, copy |
| Engineering | [`adding-a-game.md`](./adding-a-game.md) | How to add a new title via the GameAdapter seam |
| Engineering | [`data-model.md`](./data-model.md) | Map of the database: tables, the ledger, the invariants |
| Ops | [`runbook.md`](./runbook.md) | Deploy, rollback, worker restart, common incidents |
| Brand | [`brand-and-name.md`](./brand-and-name.md) | Name (Money Match vs Dueloro), voice, messaging, compliance copy |
| Product | [`product/overview.md`](./product/overview.md) | What the product is: P2P skill contests, rake-only, no house |
| Product | [`product/roadmap.md`](./product/roadmap.md) | The long arc: MVP → gems launch → real money |
| Legal | [`legal/legal-compliance.md`](./legal/legal-compliance.md) | State-law posture, publisher ToS, payments/KYC/AML, gems rules |
| Legal | [`legal/integrity-audit.md`](./legal/integrity-audit.md) | Threat model + integrity release gates |
| Business | [`business/business-and-competition.md`](./business/business-and-competition.md) | Rake economics, competitive landscape, retention, liquidity |
| Business | [`business/gtm-prelaunch.md`](./business/gtm-prelaunch.md) | Metrics, waitlist/community, referral mechanics |
| Business | [`business/website-recommendations.md`](./business/website-recommendations.md) | Marketing-site (dueloro.com) recommendations |
| Game | [`game/`](./game/) | Host API references (chess) + local end-to-end testing notes |

**Invariants that never change, whichever doc you're in:** peer-to-peer /
pooled, rake-only, no house; `sum(payouts) + rake = sum(entries)`; settlements
are host-API-verified, never self-reported; the server owns every number.
