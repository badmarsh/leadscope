# Jenex AI / LeadScope Platform

A high-performance lead generation, evaluation, and AI-powered intelligence platform built with Next.js 16 (App Router), PostgreSQL, microservices, and Docker.

---

## 🏛️ System Architecture

```
                       ┌─────────────────────────┐
                       │   Next.js 16 Dashboard  │
                       │  (App Router + Tailwind)│
                       └────────────┬────────────┘
                                    │
                         ┌──────────┴──────────┐
                         │   iron-session Auth │
                         └──────────┬──────────┘
                                    │
             ┌──────────────────────┼──────────────────────┐
             │                      │                      │
   ┌─────────▼─────────┐  ┌─────────▼─────────┐  ┌─────────▼─────────┐
   │ PostgreSQL DB     │  │ Evaluator Service │  │ TCP Proxy Services│
   │ (leadscope pool)  │  │ (Python FastAPI)  │  │ (127.0.0.1:8045)  │
   └───────────────────┘  └───────────────────┘  └───────────────────┘
```

---

## 🔒 Security & Defensive Hardening

- **Authentication & Middleware**: Protected page routes are gated behind iron-session HTTP-only cookies with server-side redirects in `middleware.ts`.
- **Credential Protection**: Plaintext logging has been removed from authentication endpoints. Secret environment variables use fallback expansion (`${VAR:-default}`).
- **Network Isolation**: Proxy listeners in `proxy.py` and `new_proxy.py` strictly bind to `127.0.0.1`.
- **Container Hardening**: `Dockerfile.dashboard` operates under a non-root `node` user and enforces runtime container health checks.

---

## 🚀 Quick Start & Local Setup

### Prerequisites
- Node.js 22+
- pnpm 9+
- Docker & Docker Compose

### Installation & Execution

1. **Environment Setup**:
   ```bash
   cp .env.example .env
   ```

2. **Run Development Server**:
   ```bash
   pnpm install
   pnpm dev
   ```

3. **Run via Docker Compose**:
   ```bash
   docker compose up -d --build
   ```

---

## 🧪 Testing Strategy

The repository uses **Vitest** for unit & component testing and **Playwright** for End-to-End browser tests.

```bash
# Run Unit & Integration Tests
npx vitest run

# Run E2E Playwright Suite
npx playwright test
```
