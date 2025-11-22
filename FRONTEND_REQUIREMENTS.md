# Frontend Requirements - Torgovo Trading Platform

This document provides comprehensive specifications for building a modern web frontend for the Torgovo cryptocurrency trading platform. It includes detailed API integration requirements, user interface specifications, and technical implementation guidelines.

## 📋 Overview

**Platform**: Torgovo Crypto Trading Platform
**Backend**: Django REST API (http://localhost:8000/api/)
**Target Users**: Cryptocurrency traders, from beginners to professionals
**Features**: Automated trading bots, portfolio management, real-time market data

## 🎯 Core Requirements

### Technology Stack
- **Framework**: React 18+, Vue 3+, or Angular 14+ (React recommended)
- **Language**: TypeScript (strongly recommended)
- **State Management**: Redux Toolkit, Zustand, or Pinia
- **Styling**: Tailwind CSS, Styled Components, or Material-UI
- **HTTP Client**: Axios with interceptors
- **WebSocket**: Socket.io or native WebSocket API
- **Charts**: Chart.js, TradingView Charts, or D3.js
- **Forms**: React Hook Form, Formik, or VeeValidate
- **Testing**: Jest, React Testing Library, Cypress
- **Build Tool**: Vite, Webpack, or Create React App

### Browser Support
- Chrome 90+, Firefox 88+, Safari 14+, Edge 90+
- Mobile responsive (iOS Safari, Android Chrome)
- Progressive Web App (PWA) support

## 🏗 Application Architecture

### Folder Structure
```
src/
├── components/           # Reusable UI components
│   ├── common/          # Generic components (Button, Modal, etc.)
│   ├── forms/           # Form components
│   ├── charts/          # Trading charts
│   └── layout/          # Layout components
├── pages/               # Page components
│   ├── auth/           # Authentication pages
│   ├── dashboard/      # Dashboard
│   ├── trading/        # Trading interfaces
│   ├── bots/           # Bot management
│   ├── portfolio/      # Portfolio tracking
│   ├── settings/       # User settings
│   └── admin/          # Admin interface
├── hooks/              # Custom React hooks
├── services/           # API services
├── store/              # State management
├── utils/              # Utility functions
├── types/              # TypeScript type definitions
├── constants/          # Application constants
├── assets/             # Static assets
└── styles/             # Global styles
```

### State Management Structure
```typescript
interface RootState {
  auth: {
    user: User | null;
    token: string | null;
    refreshToken: string | null;
    isAuthenticated: boolean;
    isLoading: boolean;
  };
  trading: {
    bots: TradingBot[];
    orders: Order[];
    positions: Position[];
    marketData: Record<string, MarketData>;
  };
  portfolio: {
    balances: Balance[];
    performance: PerformanceMetrics;
    history: TransactionHistory[];
  };
  ui: {
    theme: 'light' | 'dark';
    sidebarOpen: boolean;
    notifications: Notification[];
    loading: Record<string, boolean>;
  };
}
```

## 🔐 Authentication System

### API Integration
```typescript
// Authentication Service
class AuthService {
  private baseURL = 'http://localhost:8000/api/auth/';

  async register(data: RegisterRequest): Promise<AuthResponse> {
    const response = await axios.post(`${this.baseURL}register/`, data);
    return response.data;
  }

  async login(credentials: LoginRequest): Promise<AuthResponse> {
    const response = await axios.post(`${this.baseURL}login/`, credentials);
    this.setTokens(response.data);
    return response.data;
  }

  async googleOAuth(token: string): Promise<AuthResponse> {
    const response = await axios.post(`${this.baseURL}google/`, { access_token: token });
    this.setTokens(response.data);
    return response.data;
  }

  async refreshToken(): Promise<TokenResponse> {
    const response = await axios.post(`${this.baseURL}refresh/`, {
      refresh: localStorage.getItem('refreshToken')
    });
    this.updateTokens(response.data);
    return response.data;
  }

  async logout(): Promise<void> {
    await axios.post(`${this.baseURL}logout/`);
    this.clearTokens();
  }
}
```

### Required Authentication Pages

#### 1. Login Page (`/login`)
**Components:**
- Email input field with validation
- Password input field with show/hide toggle
- Remember me checkbox
- Google OAuth button
- Forgot password link
- Register link

**API Integration:**
- POST `/api/auth/login/`
- POST `/api/auth/google/`

**Validation:**
- Email format validation
- Password minimum length (8 characters)
- Required field validation

#### 2. Register Page (`/register`)
**Components:**
- Email input with verification
- Password input with strength indicator
- Confirm password input
- Full name input
- Phone number input (optional)
- Terms and conditions checkbox
- Google OAuth button

**API Integration:**
- POST `/api/auth/register/`
- POST `/api/auth/verify-email/`
- POST `/api/auth/verify-phone/`

**Validation:**
- Email uniqueness check
- Password strength validation
- Phone number format validation

#### 3. Email Verification Page (`/verify-email`)
**Components:**
- Verification code input (6 digits)
- Resend verification button
- Countdown timer
- Success/error messages

**API Integration:**
- POST `/api/auth/verify-email/`
- POST `/api/auth/resend-verification/`

#### 4. Forgot Password Page (`/forgot-password`)
**Components:**
- Email input field
- Submit button
- Success message
- Back to login link

**API Integration:**
- POST `/api/auth/password-reset/`

#### 5. Reset Password Page (`/reset-password/:token`)
**Components:**
- New password input
- Confirm password input
- Password strength indicator
- Submit button

**API Integration:**
- POST `/api/auth/password-reset-confirm/`

## 📊 Dashboard Overview

### Main Dashboard (`/dashboard`)
**Layout Components:**
- Sidebar navigation
- Header with user profile and notifications
- Main content area with grid layout

**Dashboard Widgets:**
1. **Portfolio Overview**
   - Total portfolio value
   - 24h profit/loss
   - Asset allocation chart
   - Quick stats

2. **Active Bots Status**
   - Number of active bots
   - Bot performance summary
   - Recent trades list
   - Quick actions (start/stop)

3. **Market Overview**
   - Top gainers/losers
   - Market trends
   - Price alerts
   - News feed

4. **Recent Activity**
   - Recent trades
   - Bot activities
   - Account activities
   - System notifications

**API Integrations:**
- GET `/api/users/stats/overview/`
- GET `/api/bots/stats/overview/`
- GET `/api/portfolio/balances/`
- GET `/api/exchanges/rates/`

## 🤖 Trading Bots Management

### Bot Management Page (`/bots`)
**Features:**
- Bot creation wizard
- Bot list with filters and search
- Bot detail view with controls
- Performance charts and analytics

#### 1. Bot Creation Wizard
**Step 1: Select Bot Type**
- Webhook Alert Bot
- Grid Trading Bot
- Martingale Bot
- Quantum AI Bot

**Step 2: Exchange Configuration**
- Exchange selection (Binance, Bybit, etc.)
- API key input (encrypted)
- Testnet/Production toggle

**Step 3: Trading Parameters**
- Trading pair selection
- Investment amount
- Risk settings (stop loss, take profit)
- Bot-specific parameters

**Step 4: Review and Deploy**
- Configuration summary
- Risk warnings
- Deploy button

**API Integrations:**
- GET `/api/exchanges/list/`
- GET `/api/exchanges/supported-pairs/`
- POST `/api/webhook-alerts/`
- POST `/api/grid-bots/`
- POST `/api/martingale-bots/`
- POST `/api/quantum-ai-bots/`

#### 2. Bot List Interface
**Table Columns:**
- Bot name and type
- Exchange and trading pair
- Status (Active, Paused, Stopped)
- Performance metrics
- Created date
- Actions (Start/Stop/Edit/Delete)

**Features:**
- Search and filter by type, exchange, status
- Sort by performance, creation date
- Bulk actions (start multiple bots)
- Export functionality

#### 3. Bot Detail View
**Information Tabs:**
1. **Overview**
   - Bot configuration
   - Current status
   - Performance metrics

2. **Performance**
   - Profit/loss chart
   - Win rate statistics
   - Trade history
   - Risk metrics

3. **Settings**
   - Edit parameters
   - Risk management
   - Notification preferences

4. **Logs**
   - Execution logs
   - Error logs
   - Debug information

**Control Buttons:**
- Start/Stop bot
- Pause/Resume
- Emergency stop
- Edit configuration
- Delete bot

**API Integrations:**
- GET `/api/grid-bots/{id}/`
- POST `/api/grid/{bot_id}/start/`
- POST `/api/grid/{bot_id}/stop/`
- GET `/api/bots/stats/performance/{bot_id}/`

## 📈 Trading Interface

### Trading View (`/trading`)
**Components:**
1. **Market Selection**
   - Exchange dropdown
   - Trading pair search
   - Market depth display
   - Recent trades list

2. **Price Chart**
   - Candlestick chart
   - Technical indicators (EMA, RSI, Bollinger Bands)
   - Time frame selector
   - Drawing tools
   - Fullscreen option

3. **Order Panel**
   - Buy/Sell tabs
   - Order type selection (Market, Limit, Stop)
   - Amount input
   - Price input (for limit orders)
   - Order preview
   - Place order button

4. **Order Book**
   - Buy orders table
   - Sell orders table
   - Market depth visualization
   - Spread information

5. **Open Positions**
   - Active positions list
   - Position size and entry price
   - Current P&L
   - Close position button

6. **Order History**
   - Order status
   - Execution details
   - Cancel option for pending orders

**API Integrations:**
- GET `/api/exchanges/{exchange}/symbols/`
- GET `/api/exchanges/rates/`
- POST `/api/webhooks/trading/`
- GET `/api/bots/orders/`
- POST `/api/trading/order/`

## 💼 Portfolio Management

### Portfolio Page (`/portfolio`)
**Sections:**

1. **Holdings Overview**
   - Total portfolio value
   - Asset allocation pie chart
   - 24h performance chart
   - Asset list with prices

2. **Asset Details**
   - Individual asset performance
   - Buy/sell history
   - Average cost calculation
   - Realized/unrealized P&L

3. **Transaction History**
   - Deposits and withdrawals
   - Trade history
   - Fee summary
   - Export functionality

4. **Performance Analytics**
   - Time-based performance charts
   - Return on investment (ROI)
   - Risk metrics
   - Comparison with benchmarks

**API Integrations:**
- GET `/api/portfolio/balances/`
- GET `/api/portfolio/history/`
- GET `/api/portfolio/performance/`
- GET `/api/payments/transactions/`

## 🎛 User Settings

### Settings Page (`/settings`)
**Setting Categories:**

#### 1. Profile Settings
- Personal information
- Email and phone verification
- Avatar upload
- Password change
- Two-factor authentication

**API Integrations:**
- GET `/api/auth/profile/`
- PUT `/api/auth/profile/`
- PUT `/api/auth/change-password/`
- POST `/api/auth/enable-2fa/`

#### 2. Exchange Accounts
- Add/remove exchange credentials
- API key management
- Test connection
- Permission settings

**API Integrations:**
- GET `/api/exchanges/credentials/`
- POST `/api/exchanges/credentials/`
- PUT `/api/exchanges/credentials/{id}/`
- DELETE `/api/exchanges/credentials/{id}/`

#### 3. Notifications
- Email notification preferences
- Telegram integration
- Price alerts
- Bot status notifications

**API Integrations:**
- GET `/api/users/notifications/`
- PUT `/api/users/notifications/`
- POST `/api/users/price-alerts/`

#### 4. Subscription Management
- Current plan status
- Upgrade/downgrade options
- Payment methods
- Billing history

**API Integrations:**
- GET `/api/subscriptions/current/`
- GET `/api/subscriptions/plans/`
- POST `/api/payments/invoices/`
- GET `/api/payments/methods/`

#### 5. Security Settings
- Active sessions
- Login history
- API key management
- Privacy settings

**API Integrations:**
- GET `/api/auth/sessions/`
- DELETE `/api/auth/sessions/{id}/`
- GET `/api/auth/api-keys/`

## 🔔 Real-time Features

### WebSocket Integration
```typescript
class WebSocketService {
  private socket: WebSocket;
  private baseURL = 'ws://localhost:8000/ws/';

  connect(token: string) {
    this.socket = new WebSocket(`${this.baseURL}?token=${token}`);

    this.socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };
  }

  subscribeToBotUpdates(botId: string) {
    this.socket.send(JSON.stringify({
      type: 'subscribe_bot',
      bot_id: botId
    }));
  }

  subscribeToMarketData(pairs: string[]) {
    this.socket.send(JSON.stringify({
      type: 'subscribe_market',
      pairs: pairs
    }));
  }

  private handleMessage(data: any) {
    switch (data.type) {
      case 'bot_update':
        store.dispatch(updateBot(data.payload));
        break;
      case 'price_update':
        store.dispatch(updatePrice(data.payload));
        break;
      case 'order_update':
        store.dispatch(updateOrder(data.payload));
        break;
    }
  }
}
```

### Real-time Updates
1. **Bot Status Updates**
   - Execution status changes
   - Trade notifications
   - Error notifications
   - Performance updates

2. **Market Data Updates**
   - Price changes
   - Order book updates
   - Trade notifications
   - Technical indicator updates

3. **Portfolio Updates**
   - Balance changes
   - P&L updates
   - Transaction confirmations
   - Position updates

4. **System Notifications**
   - Maintenance announcements
   - Feature updates
   - Security alerts
   - Price alerts

## 📱 Mobile Responsiveness

### Responsive Design Requirements
1. **Mobile-First Approach**
   - Design for mobile screens first (320px+)
   - Progressive enhancement for larger screens
   - Touch-friendly interface elements

2. **Breakpoints**
   - Mobile: 320px - 768px
   - Tablet: 768px - 1024px
   - Desktop: 1024px+

3. **Mobile-Specific Features**
   - Bottom navigation for mobile
   - Swipe gestures for charts
   - Pull-to-refresh functionality
   - Offline capability

4. **Performance**
   - Lazy loading for heavy components
   - Optimized images and assets
   - Minimal initial bundle size
   - Service worker for caching

## 🎨 UI/UX Requirements

### Design System
1. **Color Palette**
   ```css
   :root {
     --primary: #6366f1;
     --primary-dark: #4f46e5;
     --success: #10b981;
     --danger: #ef4444;
     --warning: #f59e0b;
     --info: #3b82f6;
     --dark: #1f2937;
     --light: #f9fafb;
     --border: #e5e7eb;
   }
   ```

2. **Typography**
   - Primary font: Inter, system-ui, sans-serif
   - Monospace font: Jet Brains Mono, monospace
   - Consistent font sizes and weights

3. **Spacing**
   - 4px base unit
   - Consistent padding and margins
   - Responsive spacing scales

4. **Components**
   - Consistent button styles
   - Form input styles
   - Card components
   - Modal and dialog styles

### Accessibility Requirements
1. **WCAG 2.1 AA Compliance**
   - Semantic HTML structure
   - ARIA labels and roles
   - Keyboard navigation
   - Screen reader support

2. **Visual Accessibility**
   - Sufficient color contrast
   - Focus indicators
   - Resizable text
   - Reduced motion support

3. **Interaction Accessibility**
   - Large click targets (44px minimum)
   - Clear error messages
   - Form validation
   - Loading indicators

## 🔧 Technical Implementation

### API Client Configuration
```typescript
// API Service Configuration
const apiClient = axios.create({
  baseURL: 'http://localhost:8000/api/',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request Interceptor
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response Interceptor for token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      const newToken = await authService.refreshToken();
      apiClient.defaults.headers.Authorization = `Bearer ${newToken}`;
      return apiClient(originalRequest);
    }
    return Promise.reject(error);
  }
);
```

### Error Handling Strategy
```typescript
// Global Error Handler
const handleApiError = (error: any) => {
  if (error.response) {
    // Server responded with error status
    switch (error.response.status) {
      case 401:
        // Redirect to login
        authActions.logout();
        break;
      case 403:
        // Show permission denied message
        notification.error('You do not have permission to perform this action');
        break;
      case 429:
        // Rate limit exceeded
        notification.warning('Too many requests. Please try again later.');
        break;
      case 500:
        // Server error
        notification.error('Server error. Please try again later.');
        break;
      default:
        notification.error(error.response.data.error || 'An error occurred');
    }
  } else if (error.request) {
    // Network error
    notification.error('Network error. Please check your connection.');
  } else {
    // Other error
    notification.error('An unexpected error occurred');
  }
};
```

### Loading States Management
```typescript
// Loading Hook
const useLoading = () => {
  const [loadingStates, setLoadingStates] = useState<Record<string, boolean>>({});

  const setLoading = (key: string, loading: boolean) => {
    setLoadingStates(prev => ({
      ...prev,
      [key]: loading
    }));
  };

  const isLoading = (key: string) => loadingStates[key] || false;

  return { setLoading, isLoading };
};

// Usage Example
const { setLoading, isLoading } = useLoading();

const handleSubmit = async (data: FormData) => {
  setLoading('submit', true);
  try {
    await apiClient.post('/endpoint/', data);
    notification.success('Operation completed successfully');
  } catch (error) {
    handleApiError(error);
  } finally {
    setLoading('submit', false);
  }
};
```

## 📊 Data Visualization Requirements

### Trading Charts
1. **Candlestick Charts**
   - Price data visualization
   - Volume indicators
   - Technical indicators overlay
   - Drawing tools support

2. **Depth Charts**
   - Order book visualization
   - Market depth analysis
   - Support and resistance levels

3. **Performance Charts**
   - P&L visualization
   - Portfolio composition
   - Historical performance
   - Benchmark comparison

### Statistical Charts
1. **Pie Charts**
   - Asset allocation
   - Portfolio distribution
   - Trade type breakdown

2. **Line Charts**
   - Historical performance
   - Balance over time
   - Profit/loss trends

3. **Bar Charts**
   - Trading volume analysis
   - Bot performance comparison
   - Monthly statistics

## 🧪 Testing Requirements

### Unit Testing
```typescript
// Example Component Test
import { render, screen, fireEvent } from '@testing-library/react';
import { Provider } from 'react-redux';
import { store } from '../store';
import LoginForm from '../components/LoginForm';

test('login form submits with correct data', async () => {
  const mockLogin = jest.fn();

  render(
    <Provider store={store}>
      <LoginForm onSubmit={mockLogin} />
    </Provider>
  );

  fireEvent.change(screen.getByLabelText('Email'), {
    target: { value: 'test@example.com' }
  });

  fireEvent.change(screen.getByLabelText('Password'), {
    target: { value: 'password123' }
  });

  fireEvent.click(screen.getByText('Login'));

  expect(mockLogin).toHaveBeenCalledWith({
    email: 'test@example.com',
    password: 'password123'
  });
});
```

### Integration Testing
```typescript
// Example API Integration Test
import { renderHook, act } from '@testing-library/react-hooks';
import { useAuth } from '../hooks/useAuth';
import { AuthProvider } from '../context/AuthContext';

test('login flow works correctly', async () => {
  const wrapper = ({ children }) => (
    <AuthProvider>{children}</AuthProvider>
  );

  const { result } = renderHook(() => useAuth(), { wrapper });

  await act(async () => {
    await result.current.login({
      email: 'test@example.com',
      password: 'password123'
    });
  });

  expect(result.current.isAuthenticated).toBe(true);
  expect(result.current.user).toBeTruthy();
});
```

### E2E Testing
```typescript
// Example Cypress Test
describe('Bot Creation Flow', () => {
  beforeEach(() => {
    cy.login('test@example.com', 'password123');
    cy.visit('/bots/create');
  });

  it('creates a grid bot successfully', () => {
    cy.get('[data-testid="bot-type-grid"]').click();
    cy.get('[data-testid="exchange-select"]').select('binance');
    cy.get('[data-testid="trading-pair-input"]').type('BTC/USDT');
    cy.get('[data-testid="investment-amount"]').type('1000');
    cy.get('[data-testid="create-bot-button"]').click();

    cy.url().should('include', '/bots/');
    cy.contains('Bot created successfully');
  });
});
```

## 🚀 Performance Requirements

### Bundle Size Optimization
- Initial bundle < 1MB
- Code splitting by routes
- Lazy loading heavy components
- Tree shaking for unused code

### Runtime Performance
- Time to Interactive < 3 seconds
- First Contentful Paint < 1.5 seconds
- Smooth animations (60fps)
- Memory usage < 100MB

### Caching Strategy
- Service worker for API responses
- Browser caching for static assets
- CDN for global distribution
- Cache invalidation strategy

## 📱 Progressive Web App (PWA)

### PWA Features
1. **Offline Capability**
   - Cache critical resources
   - Offline dashboard view
   - Offline queue for actions

2. **Installable App**
   - Web App Manifest
   - App icons and splash screens
   - Standalone mode support

3. **Push Notifications**
   - Trade notifications
   - Price alerts
   - System announcements

### Service Worker Configuration
```typescript
// Service Worker Registration
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((registration) => {
        console.log('SW registered: ', registration);
      })
      .catch((registrationError) => {
        console.log('SW registration failed: ', registrationError);
      });
  });
}
```

## 🔒 Security Considerations

### Frontend Security
1. **Input Validation**
   - Client-side validation
   - XSS prevention
   - CSRF protection
   - Content Security Policy

2. **Token Security**
   - Secure storage (httpOnly cookies recommended)
   - Token rotation
   - Automatic logout on token expiry
   - Secure token transmission

3. **Data Protection**
   - Sensitive data masking
   - Local storage encryption
   - Secure API communication
   - Audit logging

## 📋 Deployment Checklist

### Pre-deployment Requirements
- [ ] Environment variables configured
- [ ] API endpoints tested
- [ ] Performance optimization completed
- [ ] Accessibility audit passed
- [ ] Security review completed
- [ ] Browser compatibility tested
- [ ] Mobile responsiveness verified
- [ ] Error handling implemented
- [ ] Loading states added
- [ ] Form validation complete

### Production Build
```bash
# Build optimization
npm run build

# Bundle analysis
npm run analyze

# Performance testing
npm run test:lighthouse

# E2E testing
npm run test:e2e:prod
```

This comprehensive frontend requirements document provides all the necessary specifications for building a modern, feature-rich frontend for the Torgovo trading platform. It includes detailed API integration guidelines, UI/UX requirements, technical implementation details, and deployment considerations.