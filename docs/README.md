# MoneyMatch — Docs Index

| Area | Doc | What it answers |
| --- | --- | --- |
| **Build plan** | [`implementation-guide/`](./implementation-guide/00-README.md) | **Start here to build.** Phased PoC→MVP plan, architecture, design system, migration map, acceptance checklist |
| Design | [`design/moneymatch-design.pdf`](./design/moneymatch-design.pdf) | The visual source of truth (13 screens) |
| Product | [`product/overview.md`](./product/overview.md) | What the product is: P2P skill contests, rake-only, no house |
| Product | [`product/roadmap.md`](./product/roadmap.md) | The long arc: MVP → gems launch → real money |
| Legal | [`legal/legal-compliance.md`](./legal/legal-compliance.md) | State-law posture, publisher ToS verdicts, payments/KYC/AML, gems design rules |
| Legal | [`legal/integrity-audit.md`](./legal/integrity-audit.md) | Threat model from the PoC audit — the integrity release gates |
| Business | [`business/business-and-competition.md`](./business/business-and-competition.md) | Rake economics, competitive landscape, retention, liquidity plan |
| Business | [`business/gtm-prelaunch.md`](./business/gtm-prelaunch.md) | Metrics, waitlist/community, referral mechanics |
| Proposals | [`proposals/production-launch-plan-v3.md`](./proposals/production-launch-plan-v3.md) | Engineer's launch plan — matchmaking/pool/tournament fairness math adopted into the guide; Firebase/Stripe stack not adopted (see banner) |
| Proposals | [`proposals/challenge-engine-workflow.md`](./proposals/challenge-engine-workflow.md) | Engineer's challenge-engine spec — profiles/audit/risk adopted; house-backed mode rejected (see banner) |
| PoC | [`../poc-reference/POC-IMPLEMENTATION.md`](../poc-reference/POC-IMPLEMENTATION.md) | Ground truth of the PoC code mirrored in `/poc-reference` |

**Invariants that never change, whichever doc you're in:** peer-to-peer /
pooled, rake-only, no house; `sum(payouts) + rake = sum(entries)`; settlements
are host-API-verified, never self-reported; the server owns every number.
