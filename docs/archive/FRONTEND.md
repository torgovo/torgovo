# Frontend Requirements

## Stack

- React 18 + TypeScript
- Vite (build tool)
- Tailwind CSS (styling)
- Axios (HTTP client, base URL configurable)
- React Router v6 (routing)

## Implementation Status

**Scaffold exists** in `frontend/` (project root). Existing files: `App.jsx`, `main.jsx`, `AuthContext.jsx`, `ProtectedRoute.jsx`. No page components or build pipeline yet.

## Pages Required

### Public
1. **Landing Page** — product overview, features, pricing
2. **Login / Register** — JWT authentication
3. **Password Reset** — OTP-based recovery

### Authenticated (User)
4. **Dashboard** — bot status, portfolio summary, recent trades
5. **Bot Management**
   - Bot list (all types in unified view)
   - Create bot wizard (Signal / Grid / Martingale)
   - Bot detail (config, orders, P/L chart)
   - Start / Stop controls
6. **Exchange Credentials** — add/edit/test API keys
7. **Subscriptions** — plan selection, upgrade/downgrade
8. **Referrals** — code + stats overview
9. **Transactions** — deposit/withdrawal history
10. **Profile** — settings, API usage

### Authenticated (Admin)
11. **Admin Dashboard** — KPIs (active bots, users, deposits, profits)
12. **User Management** — list/detail, toggle active, adjust balance
13. **Quantum AI Management** — create fund, monitor performance
14. **Deposit/Withdrawal Approval** — confirm/reject pending requests
15. **Audit Logs** — user activity log viewer

## API Integration Notes

- Auth: store JWT access token in memory, refresh in httpOnly cookie or localStorage
- Axios interceptor for automatic token refresh on 401
- Rate limit: handle 429 with exponential backoff
- All API responses follow consistent format (see `docs/API.md`)
- Bot start/stop are async (Celery) — poll status endpoint or use WebSocket
- WebSocket planned but not implemented — fallback to polling
- Supported exchanges: Binance, Bybit, OKX, MEXC, Alpaca, Coinbase

## Component Architecture

```
src/
  components/
    layout/            Sidebar, Header, MainLayout
    common/            Loading, Error, EmptyState, Pagination
    auth/              LoginForm, RegisterForm, PasswordReset
    bots/              BotCard, BotForm, BotDetail, OrderList
    payments/          PlanCard, DepositForm, TransactionList
    exchanges/         CredentialForm
    admin/             KPICard, UserTable, AuditTable
  pages/
    ...
  hooks/
    useAuth, useBots, usePayments, useExchange
  services/
    api.js             Axios instance + interceptors
  store/
    authStore.js       Zustand or Context for auth state
```

## Required npm Packages

```json
{
  "react": "^18",
  "react-dom": "^18",
  "react-router-dom": "^6",
  "axios": "^1.6",
  "recharts": "^2",
  "zustand": "^4"
}
```

Dev: `vite`, `tailwindcss`, `@tailwindcss/forms`, `@types/react`, `typescript`

## Design Principles

- Mobile-first responsive design
- Dark mode support via Tailwind
- Real-time updates via WebSocket (when implemented)
- All mutations show loading + error states
- Optimistic UI updates for start/stop actions
