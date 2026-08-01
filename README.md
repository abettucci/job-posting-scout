# LinkedIn Job Scout

Monitors LinkedIn job searches, scores each listing with Claude Haiku against your candidate profile, and notifies you on Telegram. Includes a Kanban-style interview tracker.

## How it works

```
EventBridge (4×/day, Mon–Fri)
        ↓
Scraper Lambda (Playwright)
        ↓
LinkedIn search URLs → raw job listings
        ↓
DynamoDB dedup (per user)
        ↓
Claude Haiku scoring (0–100)
        ↓  score ≥ threshold
Telegram notification
```

Each user configures their own search URLs and candidate profile (must-have skills, deal-breakers, preferences). The scraper runs using a single LinkedIn account owned by the service.

## Stack

| Layer | Tech |
|---|---|
| Scraper | Python · Playwright · Chromium |
| Scoring | Anthropic Claude Haiku (`claude-haiku-4-5`) |
| API | FastAPI · Mangum · AWS Lambda |
| Bot | Telegram webhook · AWS Lambda |
| Storage | DynamoDB (6 tables) |
| Infra | CloudFormation · ECR · EventBridge · API Gateway |
| Frontend | Next.js 14 · Tailwind CSS |
| Deploy | Vercel (frontend) · AWS (backend) |

## Features

- **Job monitoring** — scrapes your saved LinkedIn search URLs on a schedule and deduplicates across runs
- **AI scoring** — Claude Haiku returns a 0–100 score, reasons, and a recommendation (APPLY / MAYBE / SKIP) based on your profile
- **Telegram notifications** — only jobs above your score threshold land in your chat
- **Multi-user** — each user has their own searches, profile, and Telegram account; <20 users
- **Interview tracker** — Kanban board (Applied → Phone → Technical → Onsite → Offer) with Google Calendar deep links
- **"Track Interview" flow** — one click from any job card opens the interview form pre-filled with company, role, and score

## Project structure

```
linkedin-job-scout/
├── aws/
│   ├── infra/
│   │   └── template.yaml          # CloudFormation — all resources
│   └── lambdas/
│       ├── shared/                # Config, DynamoDB client, auth, scorer, Telegram client
│       ├── api/                   # FastAPI + Mangum (auth, searches, profile, jobs, interviews)
│       ├── scraper/               # Playwright scraper + handler
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
├── Makefile                       # build / push / deploy / logs / set-webhook
└── .env.example
```

## Setup

### Prerequisites

- AWS CLI configured
- Docker
- Node.js 20+
- Python 3.11+

### 1. Clone and configure

```bash
git clone <repo>
cd linkedin-job-scout
cp .env.example .env
# Fill in all values in .env
```

Required secrets:

| Variable | Where to get it |
|---|---|
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_WEBHOOK_SECRET` | Any random 32+ char string (`openssl rand -hex 32`) |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `JWT_SECRET` | Any random 32+ char string |
| `LINKEDIN_EMAIL` | Your LinkedIn account |
| `LINKEDIN_PASSWORD` | Your LinkedIn account |
| `FRONTEND_URL` | Your Vercel deployment URL |

### 2. First deploy (CloudFormation + ECR repos)

```bash
# Export env vars from your .env file
export $(grep -v '^#' .env | xargs)

# Build and push images (creates ECR repos first via CFN)
make deploy          # creates all AWS resources
make push            # builds and pushes Docker images
make update-functions  # points Lambdas to the new images
```

### 3. Register the Telegram webhook

After deploy, get the API Gateway URL from CloudFormation outputs:

```bash
# Get the webhook URL from CFN outputs
WEBHOOK_URL=$(aws cloudformation describe-stacks \
  --stack-name linkedin-job-scout-prod \
  --query "Stacks[0].Outputs[?OutputKey=='TelegramWebhookUrl'].OutputValue" \
  --output text)

make set-webhook WEBHOOK_URL=$WEBHOOK_URL
```

### 4. Deploy the frontend

```bash
cd frontend
cp .env.local.example .env.local
# Set NEXT_PUBLIC_API_URL to your API Gateway URL
npm install && npm run build

# Deploy to Vercel
npx vercel --prod
```

### 5. Create your account

Open the frontend URL, sign up, then go to **Settings** to:
1. Configure your candidate profile (must-have, nice-to-have, deal-breakers)
2. Link your Telegram account using the 6-digit code flow
3. Add your LinkedIn search URLs in **Dashboard**

## Makefile reference

```bash
make build              # Build all 3 Docker images
make push               # Build + tag + push to ECR
make deploy             # Deploy/update CloudFormation stack
make update-functions   # Point Lambdas to latest image tag
make invoke-scraper     # Manually trigger one scraper run
make logs-api           # Tail API Lambda logs
make logs-scraper       # Tail Scraper Lambda logs
make logs-bot           # Tail Telegram Bot Lambda logs
make set-webhook        # Register Telegram webhook URL
make frontend-dev       # npm install + next dev
```

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
| Claude Haiku | ~$2–5/month |
| Lambda | Free tier |
| DynamoDB | Free tier |
| API Gateway | Free tier |
| ECR | ~$0.50/month |
| **Total** | **~$3–6/month** |

## Notes on LinkedIn scraping

The scraper uses Playwright with your LinkedIn credentials stored in AWS Secrets Manager. Session cookies are persisted between runs to avoid repeated logins. To reduce detection risk, the scraper runs at most 4 times per day on weekdays, uses random delays between actions, and is capped at 30 jobs per search URL per run.

Automated scraping may violate LinkedIn's Terms of Service. Use at your own discretion.
