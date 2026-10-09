"""
Locust load testing configuration for Torgovo2.

Usage:
    pip install locust
    locust -f locustfile.py --host=http://localhost:8000

Then open http://localhost:8089 to configure and start the test.
"""

import random
import string
import time

from locust import HttpUser, between, events, task


class AnonymousUser(HttpUser):
    """Simulates anonymous (unauthenticated) API traffic."""

    weight = 3
    wait_time = between(1, 3)

    @task(5)
    def health_check(self):
        self.client.get("/health/", name="/health/")

    @task(3)
    def metrics(self):
        self.client.get("/metrics", name="/metrics")

    @task(2)
    def admin_login_page(self):
        self.client.get("/admin/login/", name="/admin/login/")

    @task(1)
    def api_root(self):
        self.client.get("/api/", name="/api/")


class AuthenticatedUser(HttpUser):
    """Simulates authenticated API traffic with JWT tokens."""

    weight = 5
    wait_time = between(2, 5)

    def on_start(self):
        """Login and get JWT token."""
        phone = "+92300" + "".join(random.choices(string.digits, k=7))
        # Request OTP
        self.client.post(
            "/api/auth/otp/request/",
            json={"phone": phone},
            name="/api/auth/otp/request/",
        )
        # In real test, you'd verify the OTP and get tokens
        # For now, just set a dummy token
        self.token = None
        self.headers = {}

    @task(3)
    def list_bots(self):
        self.client.get("/api/bots/", headers=self.headers, name="/api/bots/")

    @task(2)
    def list_exchanges(self):
        self.client.get("/api/exchanges/", headers=self.headers, name="/api/exchanges/")

    @task(2)
    def dashboard_summary(self):
        self.client.get("/api/bots/dashboard/", headers=self.headers, name="/api/bots/dashboard/")

    @task(1)
    def subscriptions(self):
        self.client.get("/api/subscriptions/", headers=self.headers, name="/api/subscriptions/")

    @task(1)
    def investments(self):
        self.client.get("/api/investments/", headers=self.headers, name="/api/investments/")


class WebhookUser(HttpUser):
    """Simulates TradingView webhook traffic."""

    weight = 2
    wait_time = between(5, 15)

    @task
    def send_webhook(self):
        payload = {
            "secret": "test_secret_" + "".join(random.choices(string.ascii_lowercase, k=8)),
            "bot_id": str(random.randint(1000, 9999)),
            "Pair": random.choice(["BTCUSDT", "ETHUSDT", "SOLUSDT"]),
            "position_size": str(round(random.uniform(0.01, 1.0), 4)),
            "exchange": random.choice(["bybit", "binance"]),
            "timestamp": str(int(time.time())),
            "side": random.choice(["buy", "sell"]),
        }
        self.client.post(
            "/api/webhooks/custombot/",
            json=payload,
            name="/api/webhooks/custombot/",
        )


class AdminUser(HttpUser):
    """Simulates admin panel traffic."""

    weight = 1
    wait_time = between(3, 8)

    @task(3)
    def admin_dashboard(self):
        self.client.get("/admin/", name="/admin/")

    @task(2)
    def admin_users(self):
        self.client.get("/admin/authentication/user/", name="/admin/users/")

    @task(1)
    def admin_bots(self):
        self.client.get("/admin/bots/signalbot/", name="/admin/bots/")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test start."""
    print(f"Starting load test against {environment.host}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Log test completion."""
    print("Load test completed")
