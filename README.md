# LinkedIn Job Scout

Monitors job searches across LinkedIn, company ATS boards, and remote-job aggregators, scores each listing with a configurable AI-provider cascade against your candidate profile, and notifies you on Telegram. Includes a Kanban-style interview tracker.

## How it works

```
EventBridge (4×/day, Mon–Fri)
        ↓
Scraper Lambda
        ↓
LinkedIn (Playwright) / ATS APIs / Aggregator APIs → raw job listings
        ↓
DynamoDB dedup (per user)
        ↓
AI provider cascade scoring (0–100)
        ↓  score ≥ threshold
Telegram notification
```

Each user configures their own searches and candidate profile (must-have skills, deal-breakers, preferences). LinkedIn scraping runs using a single LinkedIn account owned by the service; ATS and aggregator sources are fetched from public, unauthenticated APIs.

### Job sources

| Type | Sources | How it works |
|---|---|---|
| LinkedIn (specific URL) | LinkedIn | Playwright scrapes a saved search URL you paste yourself — full control over LinkedIn's own filters (time posted, boolean keywords, etc.) |
| Multi-board (profile search) | LinkedIn + RemoteOK + Working Nomads + Remotive + Arbeitnow + CompuJobs + OnlineJobs.ph + Y Combinator + FreeHire + Hashtag Web3 + Wellfound + SimplyHired | One search — job title, seniority, location — fanned out across every global source: a LinkedIn URL is auto-built (seniority maps to LinkedIn's native `f_E` experience-level filter), and the job title is used as the keyword filter on the other boards. YC contributes public Buenos Aires and worldwide-remote listings. |
| Public board (keyword search) | JustJoin.IT, Dixcover Hub | Direct, opt-in sources with public listings. They are not fanned into Multi-board because their remote roles are frequently country/region-specific. |
| ATS (per-company) | Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Workday, Deel | Public API or public careers page per company, filtered by keywords/location |

Seniority is only a real, structured filter on LinkedIn — the other boards do not expose a compatible seniority field, so a multi-board search doesn't apply it to them (see `handler.py`'s "Multi-board fan-out" section for why). Company size/type isn't filterable on any source yet; none of them expose it via a public API without a paid company-database lookup.

The scraper reads ordinary public pages or documented/public feeds only. It does not authenticate into job boards, use private endpoints, proxies, CAPTCHA solving, or any challenge bypass. A board becoming unavailable is isolated to that source and appears in the per-run dashboard and Telegram report.

### Requested-board audit (2026-10-08)

| Requested source | Status |
|---|---|
| Working Nomads, Remotive, OnlineJobs.ph, CompuJobs, YC, FreeHire, Greenhouse, Lever, Ashby, Workday, Deel | Already supported before this audit |
| SimplyHired, Wellfound (formerly AngelList), JustJoin.IT, Dixcover Hub | Added as public sources in this release |
| Snaphunt, Virtual Vocations, RemoteHub, Naukri, FlexJobs, Flexible Hire | Not enabled: the public path was unavailable, blocked for ordinary requests, subscription-gated, or the supplied name did not identify a stable canonical job-board URL. They remain candidates for a future integration only if a stable public listing endpoint is available. |
| InfoRegister, Trustpilot, Crunchbase, Glassdoor, levels.fyi, Sacra, PitchBook | Company-research links, not job-listing sources; retained as human-opened research links rather than automated scrapers. |

## Stack

| Layer | Tech |
|---|---|
| Scraper | Python · Playwright · Chromium |
| AI features | Confirmed Gemini free tier → OpenRouter Free → paid Claude Haiku → paid Groq fallback |
| API | FastAPI · Mangum · AWS Lambda |
| Bot | Telegram webhook · AWS Lambda |
| Storage | DynamoDB |
| Infra | Terraform · ECR · EventBridge · API Gateway |
| Frontend | Next.js 14 · Tailwind CSS |
| Deploy | Vercel (frontend) · AWS (backend) |

## Features

- **Job monitoring** — scrapes your saved LinkedIn search URLs, tracked ATS company boards, and remote-job aggregators on a schedule, deduplicating across runs
- **AI scoring** — the configured provider cascade returns a 0–100 score, reasons, and a recommendation (APPLY / MAYBE / SKIP) based on your profile
- **Telegram notifications** — only jobs above your score threshold land in your chat
- **Multi-user** — each user has their own searches, profile, and Telegram account; <20 users
- **Interview tracker** — Kanban board (Applied → Phone → Technical → Onsite → Offer) with Google Calendar deep links
- **"Track Interview" flow** — one click from any job card opens the interview form pre-filled with company, role, and score

## Project structure

```
linkedin-job-scout/
├── main.tf                        # Terraform — AWS resources and Lambda environment
├── .github/workflows/deploy.yml   # Docker build/push, Terraform deploy, Telegram webhook
├── aws/
│   └── lambdas/
│       ├── shared/                # Config, DynamoDB client, auth, scorer, Telegram client
│       ├── api/                   # FastAPI + Mangum (auth, searches, profile, jobs, interviews)
│       ├── scraper/               # Playwright scraper + handler
│       │   └── providers/         # ATS (greenhouse, lever, ashby, workable, smartrecruiters) +
│       │                          # aggregator fetchers (including YC public listings)
│       ├── telegram_bot/          # Webhook handler (/start, /status, /pause, /resume)
│       ├── Dockerfile.api
│       ├── Dockerfile.scraper     # Includes Chromium
│       └── Dockerfile.telegram_bot
├── frontend/
│   └── src/
│       ├── app/                   # Next.js App Router pages
│       │   ├── page.tsx           # Login / sign-up
│       │   ├── dashboard/         # Search management + recent matches
│       │   ├── jobs/              # Full job history with score filter
│       │   ├── interviews/        # Kanban interview tracker
│       │   └── settings/          # Candidate profile + Telegram linking
│       ├── components/
│       │   ├── JobCard            # Score badge, reasons, Track Interview button
│       │   ├── KanbanBoard        # Drag-and-drop by stage, archive section
│       │   ├── InterviewCard      # Stage selector, Google Calendar link
│       │   ├── ProfileEditor      # Tag-style editor for skills/deal-breakers
│       │   ├── TelegramLink       # 6-digit code linking flow
│       │   └── SearchForm
│       └── lib/
│           ├── api.ts             # Typed API client
│           ├── auth.ts            # JWT auth context
│           └── gcal.ts            # Google Calendar deep link (no OAuth)
```

## Setup

### Prerequisites

- AWS CLI configured
- Docker
- Node.js 20+
- Python 3.11+

### 1. Clone the repository

```bash
git clone <repo>
cd linkedin-job-scout
```

Required secrets:

| Variable | Where to get it |
|---|---|
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_WEBHOOK_SECRET` | Any random 32+ char string (`openssl rand -hex 32`) |
| `GEMINI_API_KEY` *(optional)* | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `GROQ_API_KEY` *(optional)* | [Groq Console](https://console.groq.com/keys) |
| `OPENROUTER_API_KEY` *(optional)* | [OpenRouter](https://openrouter.ai/settings/keys) |
| `ANTHROPIC_API_KEY` *(optional final fallback)* | [console.anthropic.com](https://console.anthropic.com) |
| `JWT_SECRET` | Any random 32+ char string |
| `LINKEDIN_EMAIL` *(optional)* | Your LinkedIn account (used if session cookies need renewal) |
| `LINKEDIN_PASSWORD` *(optional)* | Your LinkedIn account (used if session cookies need renewal) |
| `FRONTEND_URL` | Your Vercel deployment URL |

Text generation tries Gemini Flash first only when
`GEMINI_FREE_TIER_CONFIRMED=true`; this is an explicit operator assertion that
the Google project/key uses a non-billable tier. OpenRouter's `openrouter/free`
is next. If both free providers are unavailable, Haiku is the first paid
fallback and Groq GPT-OSS 120B is only the next paid fallback. Groq is not
treated as free because its model has published per-token pricing. Providers
without keys are skipped. Legacy OmniRoute settings are not part of this chain.

Paid requests reserve an estimated maximum against a shared DynamoDB budget
before leaving the app. The default cap is **US$1 per UTC day**, configurable
with Terraform variable `ai_paid_daily_budget_usd`; use `0` to disable paid
fallback entirely. The estimate uses prompt length and max output tokens, then
settles to provider-reported usage where available. Failed/time-out paid calls
retain their reservation for the day so a timeout cannot accidentally permit
unbounded retries. The existing scraper cap of 150 scoring calls per run is
separate from this global paid-spend guard. A failed paid-budget reservation
fails closed. Legacy OmniRoute settings are not part of this chain.
If every configured provider is unavailable, each new job is saved as
`pending` and retried automatically on later scheduled runs.

Privacy note: Gemini's free-tier terms may allow submitted content to be used
to improve Google products. Resume tailoring sends resume data and job
descriptions to whichever configured provider responds first. Use providers
for sensitive resume data only if you accept their current data-handling terms.
Gemini is skipped unless `gemini_free_tier_confirmed=true` is set in Terraform;
the API itself cannot enforce that an API key stays on a free billing tier.
Google's free-tier terms may also allow submitted content to improve its
products. OpenRouter Free may route to different underlying models/providers,
so review their current data handling terms before sending a resume or other
personal information. This matters because whichever provider is attempted
receives the request content.

### 2. Configure GitHub Actions secrets

In the personal repository settings, open **Secrets and variables → Actions**
and add the following. The deployment job (not the Docker build job) passes
these values as sensitive Terraform inputs; the Docker images do not contain
credentials.

Required: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ACCOUNT_ID`,
`AWS_REGION`, `FRONTEND_URL`, `TELEGRAM_WEBHOOK_SECRET`,
`TELEGRAM_BOT_TOKEN`, and `JWT_SECRET`. Configure at least one of
`GEMINI_API_KEY`, `GROQ_API_KEY`, `OPENROUTER_API_KEY`, or
`ANTHROPIC_API_KEY` for AI features.

Optional: `LINKEDIN_EMAIL`, `LINKEDIN_PASSWORD`, `WAWEB_SIDECAR_URL`,
`WAWEB_SHARED_SECRET`, `OMNIROUTE_BASE_URL`, `OMNIROUTE_API_KEY`, and
`OMNIROUTE_MODEL`.

Terraform marks secret variables as sensitive, but Terraform state can still
contain their values. The GitHub-hosted deploy runner uses local, ephemeral
state; do not persist or share that state file. At runtime the app reads static
credentials from Lambda environment variables. Only the mutable LinkedIn
session cookie remains in Secrets Manager.

### 3. First deploy (Terraform + ECR repos)

Push to `main` or run the **Deploy** workflow manually. It builds and pushes
the three Lambda Docker images to ECR, then applies Terraform and registers
the Telegram webhook. Secrets are supplied at deploy time and never baked
into the images. After a successful rollout and smoke test, delete the old
static `linkedin-job-scout/prod` Secrets Manager secret to stop its monthly
charge; retain `linkedin-job-scout/linkedin-cookies`, which the app updates
while managing the LinkedIn session.

### 4. Telegram webhook

The deploy workflow registers the webhook automatically. To inspect the URL,
run `terraform output -raw telegram_webhook_url` from the Terraform working
directory after deployment.

### 5. Deploy the frontend

```bash
cd frontend
cp .env.local.example .env.local
# Set NEXT_PUBLIC_API_URL to your API Gateway URL
npm install && npm run build

# Deploy to Vercel
npx vercel --prod
```

### 6. Create your account

Open the frontend URL, sign up, then go to **Settings** to:
1. Configure your candidate profile (must-have, nice-to-have, deal-breakers)
2. Link your Telegram account using the 6-digit code flow
3. Optionally enable WhatsApp alerts and add your international phone number
4. Add your LinkedIn search URLs in **Dashboard**

### WhatsApp job alerts

WhatsApp delivery uses the private WhatsApp Web sidecar's `POST /send` endpoint. Add
`WAWEB_SIDECAR_URL` and `WAWEB_SHARED_SECRET` as GitHub Actions repository
secrets. The deploy workflow passes them through Terraform to the scraper
Lambda's environment. Keep the shared secret server-side; never add it to
Vercel or frontend environment variables. Then enable WhatsApp in **Settings →
New job notifications**, entering the phone with its country code (for example
`+54911…`).
Telegram remains enabled by default for existing profiles; each channel can be toggled
independently. Only new jobs that pass the configured filters and score threshold are
sent.

## API endpoints

```
POST   /auth/signup
POST   /auth/login
GET    /auth/me

GET    /searches
POST   /searches
PATCH  /searches/{id}
DELETE /searches/{id}

GET    /profile
PUT    /profile

POST   /telegram/start-link

GET    /jobs?min_score=&limit=

GET    /interviews
POST   /interviews
PATCH  /interviews/{id}
DELETE /interviews/{id}

GET    /health
```

## Interview stages

```
applied → phone → technical → onsite → offer → accepted
                                              → rejected
                                              → withdrawn
```

Drag cards between Kanban columns or use the "Move" dropdown. Accepted / rejected / withdrawn cards move to a collapsible archive section. Cards with a scheduled date show a "Add to Google Calendar" button (deep link, no OAuth needed).

## DynamoDB tables

| Table | Key | TTL |
|---|---|---|
| `users` | `user_id` (+ GSI on `email`) | — |
| `searches` | `user_id` / `search_id` | — |
| `profiles` | `user_id` | — |
| `jobs` | `user_id` / `job_id` | 60 days |
| `interviews` | `user_id` / `interview_id` | — |
| `telegram-codes` | `code` | 10 min |

## Telegram bot commands

| Command | Description |
|---|---|
| `/start <code>` | Link your account using the 6-digit code from Settings |
| `/status` | Show linked account and active search count |
| `/pause` | Deactivate all searches (mute notifications) |
| `/resume` | Reactivate all searches |

## Cost estimate

At 4 runs/day × 5 days/week × 3 users × 30 jobs/search:

| Service | Estimated cost |
|---|---|
| AI providers | Free providers are attempted first; paid fallback usage depends on provider availability and volume |
| Lambda | Free tier |
| DynamoDB | Free tier |
| API Gateway | Free tier |
| ECR | ~$0.50/month |
| Secrets Manager | One mutable LinkedIn-cookie secret remains |

## Notes on LinkedIn scraping

The scraper reads LinkedIn login credentials from the Lambda environment configured by Terraform and persists session cookies in Secrets Manager between runs. To reduce detection risk, the scraper runs at most 4 times per day on weekdays, uses random delays between actions, and is capped at 30 jobs per search URL per run.

Automated scraping may violate LinkedIn's Terms of Service. Use at your own discretion.