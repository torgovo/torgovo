# Torgovo2 — Marketing Evaluation

**Evaluated:** 2026-07-28
**Skills applied:** analytics-tracking, brand-guidelines, campaign-analytics, churn-prevention, cold-email, competitor-alternatives, content-production, content-strategy, copywriting, email-sequence, landing, launch-strategy, marketing-context, marketing-ops, marketing-strategy-pmm, onboarding-cro, page-cro, paid-ads, paywall-upgrade-cro, popup-cro, pricing-strategy, programmatic-seo, referral-program, schema-markup, seo-audit, signup-flow-cro, site-architecture, social-content, social-media-manager, webinar-marketing

---

## Executive Summary

Torgovo2 has **zero public marketing surface**. There is no landing page, no analytics, no SEO, no email templates, no social presence, and no automated payment processing. The frontend is an empty scaffold (Vite + React with no built pages). The project is a **pure backend API** with solid trading infrastructure and a functional referral system, but it has no way to attract, convert, or retain users through marketing channels. An automated payment flow (Stripe webhooks, recurring billing) and a basic marketing site are prerequisites before any growth investment pays off.

**Overall marketing maturity score: 34/100**

---

## Findings by Skill

### 1. landing
- **Rating: F**
- No landing page, marketing site, or public-facing HTML exists. `templates/` only has `health.html` and admin templates. The Vite frontend scaffold has zero built pages. Frontend `src/pages/` directory does not exist on disk.

### 2. pricing-strategy
- **Rating: B**
- Three plan systems exist: Telegram Signal Plans (monthly/quarterly/yearly), Bot Subscription Plans (30/90/180/365 days), and user subscription tiers (free/basic/premium/enterprise). Plans are well-structured with feature limits and trial days. **But**: no pricing page, no automated payment flow, and the manual-approval crypto flow creates conversion friction.

### 3. referral-program
- **Rating: B**
- Fully implemented referral system: auto-generated 8-char codes, registration integration (`?ref=` query param + POST body), tracking endpoints (`/api/referrals/my-stats/`, `/api/referrals/apply/`), USDT bonus payouts, self-referral guard. **Gaps**: no reward tiers, no milestone bonuses, no leaderboard, no referral link sharing UI.

### 4. signup-flow-cro
- **Rating: C**
- Registration works (email + password) with email verification and optional referral code. Brute-force lockout (5 attempts/15 min). Google OAuth exists. Phone verification is a stub (SMS not actually sent). **Missing**: progressive profiling, welcome tour, empty-state guidance, CTA after registration.

### 5. email-sequence
- **Rating: D**
- Basic `django.core.mail.send_mail()` calls exist (welcome email, verification, password reset) but all are **plain text**. No email template directory (`templates/email/` does not exist). No Mailjet/SendGrid/SES integration. No triggered sequences (onboarding drip, re-engagement, win-back).

### 6. analytics-tracking
- **Rating: F**
- No GA4, no GTM, no Mixpanel/Amplitude/PostHog. No tracking pixels, no event tracking, no conversion tracking. Sentry (error tracking) is configured. Zero marketing analytics infrastructure.

### 7. seo-audit / schema-markup / site-architecture / programmatic-seo
- **Rating: F** (all four)
- No `sitemap.xml`, no `robots.txt`, no meta tags, no Open Graph/Twitter Card tags, no structured data. The backend has no HTML-rendered pages. SEO is entirely inapplicable to the current state.

### 8. copywriting / content-production / content-strategy
- **Rating: D**
- No marketing copy exists outside README.md. No blog, no case studies, no feature descriptions. `docs/implementation.md` contains the closest thing to product copy but is developer-oriented.

### 9. churn-prevention
- **Rating: D**
- No cancel flow exists (no self-service cancellation — subscriptions expire passively). No dunning sequence for failed payments. No exit surveys. No win-back offers. The `auto_renew` field exists on models but no code implements it.

### 10. paywall-upgrade-cro
- **Rating: N/A**
- No in-app upgrade flow. The frontend is not built. All upgrades are handled through the admin panel (manual approval of crypto payments).

### 11. page-cro / popup-cro / form-cro
- **Rating: N/A**
- No marketing pages, no popups, no public forms exist to optimize.

### 12. marketing-strategy-pmm
- **Rating: D**
- No positioning document, no ICP definition, no competitive analysis, no GTM plan. The README describes the product but doesn't differentiate.

### 13. social-content / social-media-manager / campaign-analytics
- **Rating: N/A**
- No social media presence, no content calendar, no campaign data to analyze.

### 14. paid-ads / webinar-marketing / cold-email / competitor-alternatives
- **Rating: N/A**
- No paid advertising, no webinar strategy, no outbound sales, no alternative pages. These skills are premature given the lack of a marketing site.

---

## Summary Table

| Skill | Score | Key Finding |
|-------|-------|-------------|
| pricing-strategy | B | 3 plan systems with feature limits and trial days |
| referral-program | B | Full implementation with registration integration |
| signup-flow-cro | C | Functional registration, Google OAuth, brute-force lockout |
| email-sequence | D | Plain-text only, no templates, no triggered sequences |
| copywriting/content | D | No marketing copy outside README |
| churn-prevention | D | No cancel flow, no dunning, no auto-renewal |
| marketing-strategy | D | No positioning, no ICP, no GTM plan |
| landing | F | No marketing site, no public HTML |
| analytics-tracking | F | No GA4/GTM/analytics infrastructure |
| seo-audit/schema/site | F | No SEO infrastructure (inapplicable to API-only) |
| paid-ads/webinar/email | N/A | Premature — needs marketing site first |
| page/popup/form CRO | N/A | No pages/popups/forms to optimize |

---

## Recommendations

### P0 — Automated payment processing
Implement Stripe/PayPal webhook integration for subscription payments. The manual-approval crypto flow is the #1 blocker to user acquisition. Add checkout sessions and recurring billing.

### P0 — Build a landing page
Create a single-page marketing site (separate from the app) with: product overview, bot type descriptions, pricing table, FAQ, and CTA to register.

### P1 — Email template system
Add HTML email templates (using Django's template engine or a service like SendGrid/MJML). Implement triggered sequences: onboarding drip (day 0/3/7), trial-expiry warning, inactive-user re-engagement.

### P2 — Analytics foundation
Install GA4 or PostHog on the landing page and app dashboard. Track: signup conversion rate, subscription conversion rate, bot creation rate, referral conversion.

### P2 — Self-service cancellation
Build a cancel flow with exit survey, save offer (discount/pause), and dunning for failed payments. Implement `auto_renew` logic.

### P3 — Pricing page
Create a public pricing page on the landing site reflecting the 3 plan systems. Add comparison table, FAQ, and CTA.

### P3 — Positioning + ICP
Write a positioning document (20-word brand promise, target persona, key differentiators, competitive landscape). Use it to guide all future marketing content.

### P4 — Amplify referral program
Add tiered rewards, milestone bonuses, and a shareable referral landing page with social sharing buttons.

---

## Data Sources

| Source | Details |
|--------|---------|
| `apps/subscriptions/models.py` | TelegramSignalPlan with monthly/quarterly/yearly pricing |
| `apps/payments/models.py` | SubscriptionPlan, BotSubscriptionPlan, BotSubscription |
| `apps/users/models.py` | User subscription_plan field (free/basic/premium/enterprise) |
| `apps/referrals/` | Full referral system (code generation, endpoints, registration mixin) |
| `apps/authentication/views.py` | Registration, email verification, phone verification (stub), Google OAuth |
| `frontend/src/` | Empty scaffold (no built pages, `pages/` dir missing) |
| `templates/` | Only health.html + admin templates |
| `.env.example` | Twilio config (unused), Sentry DSN |
| `core/telegram_service.py` | Telegram notification integration (bot alerts) |

---

## 2026-08-11 Live Re-assessment: 34/100 confirmed (grade holds; one cross-cutting risk added)

**Method:** Re-verified every F/D rating against the live tree and working directory, plus the git state that anchors "project is a pure backend API with no marketing surface."

**Verified — all absence findings still hold:** `frontend/src/` has only the Jun-09 scaffold (`App.jsx`, `main.jsx`, empty `components/`/`contexts/`/`services/`) with no `pages/` dir and **no `dist/` build ever produced**; `templates/` is still just `admin/` + `health.html` (no `templates/email/`); no HTML landing/pricing/hero page exists anywhere in the tree (the only HTML match repo-wide is the generated `graphify-out/GRAPH_TREE.html`); `.env.example` still carries unused Twilio + Sentry DSN stubs as the only marketing-adjacent infrastructure. Stripe still never wired (`stripe_price_id` CharField at `apps/payments/models.py:40`, zero `import stripe`); `auto_renew` still a field-only stub with no implementing logic ⇒ churn-prevention D stands. Email remains plain-text `django.core.mail.send_mail()` ⇒ email-sequence D stands.

**Minor refinement (copywriting D, content D):** the report's "no marketing copy exists outside README.md" overstates slightly — `docs/PROJECT.md` (Overview + Four Bot Types, committed 2026-07-11 pre-eval) and `docs/QUICK_START.md` are product-oriented copy. Still developer-facing, not customer-facing; D rating unchanged. No positioning/ICP/GTM/SEO/social/analytics of any kind has appeared since 07-28. The four B/C ratings (pricing-strategy, referral-program, signup-flow-cro) verified unchanged and accurate.

**New cross-cutting risk (external to the 15 marketing skills but score-relevant):** the working tree carries **522 tracked changes + 422 untracked files (1303 total)** and HEAD is frozen at `ce51a49` (2026-07-11) — **30 days of commits-zero history**. All marketing-adjacent and platform work since 07-11 (docs/, internal SOPs/COMMS, AGENTS.md/CLAUDE.md, rate-limiter/grid-monitor/test-suite changes) is **uncommitted**. For marketing specifically this means: no release notes, no changelog-backed story, and a hard dependency on whoever holds the working tree — if that copy is lost, there is no committed artifact to recover from. It also means none of the recommendations (landing page, pricing page, analytics) can even be staged as a PR until the repo is re-baselined.

**Net: grade remains 34/100.** No marketing capability has been built since the audit; every F/D stands, B/C records verified, one product-copy nuance corrected, and a 30-day-commit-free repo is surfaced as the uppermost constraint on any marketing execution. Original text retained verbatim.
