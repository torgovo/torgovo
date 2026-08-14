ORGOVO FRONTEND PROMPT - Stepwise Implementation

    Project: Build React 18 + Vite frontend for Torgovo Crypto Trading Platform
    Backend API: http://localhost:8000/api/
    Technology: React 18, TypeScript, Zustand, Axios, React Query, React Hook Form, JWT Auth
    Design: Dark theme admin dashboard + user dashboard (responsive)



    Phase 1: Setup & Configuration (Mandatory First Step)

    1.  Initialize Project
        Create React 18 + TypeScript + Vite project:
        bash
        npm create vite@latest torgovo-frontend -- --template react-ts
        cd torgovo-frontend
        npm install


    2.  Install Dependencies
        bash
        npm install axios zustand @tanstack/react-query react-hook-form react-router-dom
        npm install -D @types/node autoprefixer postcss tailwindcss
        npx tailwindcss init


    3.  Configure Vite Proxy
        Edit vite.config.ts:
        typescript
        import { defineConfig } from 'vite'
        import react from '@vitejs/plugin-react'

        export default defineConfig({
          plugins: [react()],
          server: {
            port: 3000,
            proxy: {
              '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
              }
            }
          }
        })


    4.  Setup Authentication Context
        Create src/contexts/AuthContext.tsx:
        typescript
        interface User {
          id: string;
          email: string;
          is_staff: boolean;
          subscription_plan: string;
        }

        interface AuthState {
          user: User | null;
          token: string | null;
          refreshToken: string | null;
          loading: boolean;
          login: (credentials: {email: string; password: string}) => Promise<void>;
          register: (data: RegisterData) => Promise<void>;
          logout: () => void;
        }




    Phase 2: Model & Type Definitions (Define All Data Structures)

    Create src/types/api.ts with all interfaces:

    typescript
    // ===== USERS =====
    export interface User {
      id: string;
      email: string;
      is_active: boolean;
      is_staff: boolean;
      date_joined: string;
      profile: {
        telegram_token?: string;
        telegram_chat_id?: string;
        subscription_plan: string;
      };
    }

    // ===== BOTS =====
    export interface Bot {
      id: string;
      bot_type: 'signal' | 'grid' | 'martingale' | 'quantum';
      name: string;
      exchange_name: string;
      trading_pair: string;
      is_active: boolean;
      is_running?: boolean;
      created_at: string;
    }

    export interface Order {
      id: string;
      user_id: string;
      exchange: string;
      symbol: string;
      side: 'BUY' | 'SELL';
      amount: string;
      price: string;
      timestamp: string;
      outcome: 'executed' | 'failed' | 'pending';
    }

    // ===== PAYMENTS & INVESTMENTS =====
    export interface Deposit {
      id: string;
      user_id: string;
      amount: string;
      status: 'pending' | 'approved' | 'rejected';
      tx_hash?: string;
      created_at: string;
    }

    export interface Withdrawal {
      id: string;
      user_id: string;
      amount: string;
      status: 'pending' | 'completed' | 'failed';
      blockchain_address: string;
      created_at: string;
    }

    // ===== SUBSCRIPTIONS =====
    export interface SubscriptionPlan {
      id: string;
      name: string;
      price: number;
      features: string[];
    }

    // ===== REFERRALS =====
    export interface Referral {
      id: string;
      referrer_id: string;
      referred_id: string;
      bonus_amount: string;
    }

    // ===== EXCHANGES =====
    export interface ExchangeCredentials {
      id: string;
      exchange_name: string;
      api_key_masked: string;
      is_active: boolean;
    }

    export interface ExchangeRate {
      symbol: string;
      price: string;
      exchange: string;
      change_24h?: string;
      volume_24h?: string;
    }

    // ===== API RESPONSES =====
    export interface PaginatedResponse<T> {
      count: number;
      next: string | null;
      previous: string | null;
      results: T[];
    }

    export interface ErrorResponse {
      error: {
        code: string;
        message: string;
        details?: Record<string, any>;
      };
    }




    Phase 3: API Service Layer (Implement All HTTP Calls)

    Create src/services/api.ts:

    Authentication Endpoints
    typescript
    // POST /api/auth/login/
    export interface LoginRequest {
      email: string;
      password: string;
    }
    export interface LoginResponse {
      access: string;
      refresh: string;
      user: User;
    }

    // POST /api/auth/register/
    export interface RegisterRequest {
      email: string;
      password: string;
      full_name: string;
    }
    export interface RegisterResponse {
      id: string;
      email: string;
    }

    // POST /api/auth/logout/
    export interface LogoutRequest {
      refresh: string;
    }


    Admin Dashboard Endpoints
    typescript
    // GET /api/users/admin/
    // Response: PaginatedResponse<User>
    // Query params: ?is_active=true&date_joined=2024-01-01

    // GET /api/users/admin/dashboard/stats/
    export interface AdminStatsResponse {
      user_statistics: {
        total_users: number;
        active_users: number;
        new_users_today: number;
        new_users_month: number;
        subscription_distribution: Record<string, {count: number; display_name: string; percentage: number}>;
      };
      bot_statistics: {
        total_bots: number;
        running_bots: number;
        webhook_alerts: number;
        grid_bots: number;
        martingale_bots: number;
        quantum_ai_bots: number;
        exchange_distribution: Record<string, number>;
      };
      trading_statistics: {
        total_trades: number;
        trades_today: number;
        trades_month: number;
      };
      financial_statistics: {
        total_deposits_usdt: number;
        total_deposit_count: number;
        pending_deposits: number;
      };
    }

    // GET /api/users/admin/bots/overview/
    export interface BotsOverviewResponse {
      total_bots: number;
      running_bots: number;
      total_users: number;
      daily_trades: number;
      platform_volume: number;
      by_type: {
        webhook_alerts: {total: number; active: number; running: number; exchanges: Record<string, number>};
        grid_bots: {total: number; active: number; running: number; exchanges: Record<string, number>};
        martingale_bots: {total: number; active: number; running: number; exchanges: Record<string, number>};
        quantum_ai: {total: number; active: number; running: number; total_deposited: number; total_profit_loss: number};
      };
      by_exchange: Record<string, number>;
    }

    // GET /api/users/admin/trade-logs/
    // Query params: ?user_id=uuid&exchange=binance&bot_id=uuid&start_date=2024-01-01&end_date=2024-12-31
    // Response: PaginatedResponse<Order>

    // POST /api/users/admin/users/{pk}/restrict/
    export interface RestrictUserRequest {
      action: 'enable' | 'disable' | 'restrict';
      reason?: string;
    }
    export interface RestrictUserResponse {
      message: string;
      user_id: string;
      is_active: boolean;
    }

    // POST /api/users/admin/emails/send/
    export interface SendEmailRequest {
      type: 'system';
      subject: string;
      message: string;
      recipients: string[] | 'all';  // Array of user IDs or 'all'
    }
    export interface SendEmailResponse {
      message: string;
      successful: number;
      failed: number;
    }

    // POST /api/users/admin/blockchain-addresses/
    export interface CreateBlockchainAddressRequest {
      coin_type: string;
      blockchain: string;
      address: string;
    }
    export interface CreateBlockchainAddressResponse {
      message: string;
      address: {
        id: string;
        coin_type: string;
        blockchain: string;
        address: string;
        is_active: boolean;
        admin_only_configurable: boolean;
        created_at: string;
      };
    }

    // POST /api/users/admin/withdrawals/process/
    export interface ProcessWithdrawalsResponse {
      message: string;
      successful: number;
      failed: number;
    }


    Bot Management Endpoints
    typescript
    // GET /api/bots/signal-bots/ | /grid-bots/ | /martingale-bots/
    // POST /api/bots/{type}-bots/ (Create)
    export interface CreateBotRequest {
      exchange_name: string;
      trading_pair: string;
      parameters: Record<string, any>;
    }
    export interface CreateBotResponse {
      id: string;
      webhook_url?: string;
      secret_key?: string;
    }

    // PATCH /api/bots/{type}-bots/{id}/ (Enable/Disable)
    export interface UpdateBotRequest {
      is_active?: boolean;
      is_running?: boolean;
    }

    // POST /api/bots/grid/{bot_id}/start/
    // POST /api/bots/grid/{bot_id}/stop/
    // POST /api/bots/martingale/{bot_id}/start/
    // POST /api/bots/martingale/{bot_id}/stop/
    export interface BotActionResponse {
      success: boolean;
      message: string;
    }

    // GET /api/bots/orders/
    // Query params: ?user_id=uuid&exchange=binance&status=executed
    // Response: PaginatedResponse<Order>


    Payment & Investment Endpoints
    typescript
    // POST /api/investments/quantum/ (Submit deposit)
    export interface SubmitDepositRequest {
      amount: number;
      tx_hash?: string;
      screenshot?: File;
      blockchain: 'ERC20' | 'Aptos';
    }
    export interface SubmitDepositResponse {
      id: string;
      status: 'pending';
      message: string;
    }

    // GET /api/payments/admin/pending/ (Admin only)
    // PUT /api/payments/admin/deposits/{id}/approve/ (Admin only)
    // PUT /api/payments/admin/deposits/{id}/reject/ (Admin only)
    export interface ApproveDepositRequest {
      notes?: string;
    }

    // GET /api/investments/balance/
    export interface BalanceResponse {
      balance: string;
      total_deposited: string;
      total_withdrawn: string;
    }


    Exchange & Trading Endpoints
    typescript
    // GET /api/exchanges/list/
    // GET /api/exchanges/supported-pairs/
    export interface TradingPair {
      symbol: string;
      base_asset: string;
      quote_asset: string;
      exchange_name: string;
      is_active: boolean;
    }

    // GET /api/exchanges/credentials/
    // POST /api/exchanges/credentials/
    export interface ExchangeCredentialsRequest {
      exchange_name: string;
      api_key: string;
      secret_key: string;
      passphrase?: string;
    }
    export interface ExchangeCredentialsResponse {
      id: string;
      exchange_name: string;
      api_key_masked: string;
      is_active: boolean;
    }

    // GET /api/exchanges/rates/
    // Query: ?pairs=BTC/USDT,ETH/USDT&exchange=bybit
    // Response: ExchangeRate[]

    // POST /api/webhooks/tradingview/{signal_bot_id}/
    export interface TradingViewWebhookRequest {
      bot_id: string;
      buy_sell: 'buy' | 'sell';
      symbol: string;
      exchange: string;
      amount: string;
      timestamp: string;
      secret_key: string;
    }




    Phase 4: Component Architecture (Build in Order)

    1. Layout Components

    src/components/
    ├── Layout.tsx (Header + Sidebar + Main)
    ├── ProtectedRoute.tsx
    ├── DataTable.tsx (reusable table with filters)
    ├── FormModal.tsx (reusable modal)
    ├── StatusBadge.tsx (colored badges for active/pending/failed)
    └── LoadingSpinner.tsx


    2. Authentication Pages

    src/pages/
    ├── Login.tsx
    ├── Register.tsx
    ├── ForgotPassword.tsx


    Login Requirements:
    - Email/password inputs with validation
    - Submit POST /api/auth/login/
    - Store tokens in localStorage
    - Redirect to dashboard on success
    - Show errors as toast notifications

    Register Requirements:
    - Email, password, confirm password, full_name
    - Password strength indicator
    - Submit POST /api/auth/register/
    - Redirect to login on success

    3. Dashboard Page

    src/pages/Dashboard.tsx


    Sections:
    1. Stats Cards (top row)
       - Total bots
       - Active users
       - 24h trades
       - Platform volume

    2. Recent Orders table (left)
       - Symbol, side, amount, price, timestamp
       - Auto-refresh every 30s

    3. Exchange Rates (right)
       - Live prices from GET /api/exchanges/rates/
       - Green/red for 24h change

    4. Admin Dashboard

    src/pages/admin/
    ├── AdminDashboard.tsx
    ├── AdminUsers.tsx
    ├── AdminBotsOverview.tsx
    ├── AdminTradeLogs.tsx
    ├── AdminDeposits.tsx
    └── AdminEmailComposer.tsx


    AdminDashboard.tsx Requirements:
    - Stats from GET /api/users/admin/dashboard/stats/
    - User distribution pie chart
    - Bot distribution bar chart
    - Recent deposits approval queue

    AdminUsers.tsx Requirements:
    - DataTable with users from GET /api/users/admin/
    - Columns: email, is_active, bots_count, date_joined
    - Actions: Edit, Disable/Enable (POST to restrict endpoint)
    - Search filter by email

    AdminTradeLogs.tsx Requirements:
    - DataTable with filters:
      - Select: user_id
      - Select: exchange
      - Date range: start_date, end_date
    - Export CSV button
    - Paginated infinite scroll

    AdminDeposits.tsx Requirements:
    - Table of pending deposits from GET /api/payments/admin/pending/
    - Columns: user, amount, tx_hash, screenshot, created_at
    - Actions: Approve (green), Reject (red) with reason modal

    AdminEmailComposer.tsx Requirements:
    - To: 'all' or select specific users
    - Subject input
    - Message textarea (Markdown support)
    - Send button → POST /api/users/admin/emails/send/
    - Progress bar showing successful/failed counts

    5. Bot Management Pages

    src/pages/bots/
    ├── BotList.tsx
    ├── BotCreate.tsx
    ├── BotDetail.tsx


    BotList.tsx Requirements:
    - Tabs: Signal | Grid | Martingale | Quantum
    - DataTable with columns: name, type, status, exchange, pair, actions
    - Bulk actions: Start Selected, Stop Selected
    - Search by symbol/exchange

    BotCreate.tsx Requirements:
    - Multi-step wizard:
      1. Select bot type (radio buttons)
      2. Exchange + API key selection (dropdown + masked display)
      3. Trading pair search (autocomplete)
      4. Parameters based on type:
         - Grid: percentage_difference, levels_per_side
         - Martingale: multiplier, max_levels
      5. Review + Deploy

    BotDetail.tsx Requirements:
    - Tabs: Overview | Performance | Settings | Logs
    - Start/Stop/Pause buttons
    - Real-time P&L updates (poll every 5s)
    - Delete with confirmation

    6. Settings Pages

    src/pages/settings/
    ├── Profile.tsx
    ├── ExchangeAccounts.tsx
    ├── TelegramConfig.tsx
    └── Subscription.tsx


    TelegramConfig.tsx Requirements:
    - Input: Telegram Bot Token
    - Input: Telegram Chat ID
    - Test button (send test message)
    - Save → PUT /api/users/profile/



    Phase 5: State Management (Zustand Stores)

    Create src/stores/:

    typescript
    // authStore.ts
    interface AuthStore {
      user: User | null;
      token: string | null;
      login: (credentials: {email: string; password: string}) => Promise<void>;
      logout: () => void;
    }

    // botsStore.ts
    interface BotsStore {
      bots: Bot[];
      selectedBot: Bot | null;
      fetchBots: (type: string) => Promise<void>;
      startBot: (id: string, type: string) => Promise<void>;
      stopBot: (id: string, type: string) => Promise<void>;
    }

    // adminStore.ts
    interface AdminStore {
      users: User[];
      stats: AdminStatsResponse | null;
      fetchUsers: (filters?: Record<string, any>) => Promise<void>;
      fetchStats: () => Promise<void>;
      restrictUser: (userId: string, action: string) => Promise<void>;
    }




    Phase 6: Real-time Updates & Polling

    For pages requiring live data (Dashboard, Bot Detail):

    typescript
    import { useQuery } from '@tanstack/react-query';

    const { data, isLoading, refetch } = useQuery({
      queryKey: ['orders', { page: 1, limit: 20 }],
      queryFn: () => api.get('/api/bots/orders/').then(r => r.data),
      refetchInterval: 5000, // Poll every 5s
      refetchOnWindowFocus: true,
    });




    Phase 7: Error Handling & Notifications

    Create src/utils/notifications.ts:

    typescript
    interface Notification {
      id: string;
      type: 'success' | 'error' | 'warning' | 'info';
      message: string;
      autoClose?: boolean;
    }

    export const showNotification = (message: string, type: Notification['type']) => {
      // Use toast library or custom implementation
    };


    Handle all API errors:
    - 401 Unauthorized → auto logout + redirect to login
    - 403 Forbidden → show "Admin access required"
    - 404 Not Found → show "Resource not found"
    - 500 Server Error → show "Server error occurred"



    Phase 8: Admin-Only Features

    Admin Route Protection:
    typescript
    // src/components/AdminRoute.tsx
    const AdminRoute = ({ children }) => {
      const { user } = useAuth();
      if (!user?.is_staff) return <Navigate to="/" replace />;
      return children;
    };


    Admin-only menu items (render only if user.is_staff === true):
    - Users Management
    - Bot Overview
    - Trade Logs
    - Deposits Approval
    - Email Composer



    Phase 9: Testing Checklist

    Per Component:
    - [ ] Empty state (no data)
    - [ ] Loading state (spinners)
    - [ ] Error state (API failure)
    - [ ] Success state (data loaded)
    - [ ] Form validation (all fields)
    - [ ] Mobile responsiveness (viewport < 768px)
    - [ ] Keyboard navigation (Tab key)
    - [ ] Screen reader compatibility (aria-labels)



    Phase 10: Build & Deployment

    Build command:
    bash
    npm run build
    Output: dist/ folder with static files


    Deployment config:
    typescript
    // vercel.json (if deploying to Vercel)
    {
      "rewrites": [
        { "source": "/api/:path", "destination": "http://localhost:8000/api/:path" }
      ]
    }




    Critical Requirements:
    1. JWT Token Handling: Include Authorization: Bearer <token> in all requests after login
    2. File Uploads: Use FormData for screenshots/Proof (multipart/form-data)
    3. Pagination: All list endpoints return PaginatedResponse<T> - implement "Load More" buttons
    4. Admin Access: Check user.is_staff before showing admin routes
    5. Telegram Config: Show Telegram settings only to premium users (subscription_plan !== 'Free')
    6. Real-time: Poll active bot status every 5 seconds using React Query
    7. CSV Export: Add export buttons for Trade Logs (convert JSON to CSV in browser)

    Start with Phase 1 → Phase 2 → Phase 3 in order. Do not skip steps.
