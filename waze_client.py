# waze_client.py
import requests
import time
import random
from typing import Tuple, List, Dict, Any


class RateLimiter:
    """Simple rate limiter with exponential backoff."""

    def __init__(self, min_delay: float = 1.0, max_delay: float = 10.0, backoff_factor: float = 2.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.current_delay = min_delay
        self.last_request_time = 0
        self.consecutive_errors = 0

    def wait(self):
        """Wait before making next request."""
        elapsed = time.time() - self.last_request_time
        # Add jitter to avoid synchronized requests
        jitter = random.uniform(0, 0.5)
        wait_time = max(0, self.current_delay + jitter - elapsed)
        if wait_time > 0:
            time.sleep(wait_time)
        self.last_request_time = time.time()

    def success(self):
        """Call after successful request to reset backoff."""
        self.consecutive_errors = 0
        self.current_delay = self.min_delay

    def error(self):
        """Call after failed request to increase backoff."""
        self.consecutive_errors += 1
        self.current_delay = min(
            self.max_delay,
            self.min_delay * (self.backoff_factor ** self.consecutive_errors)
        )


class WazeClient:
    """Client for querying Waze live traffic data directly."""

    WAZE_API_URL = "https://www.waze.com/live-map/api/georss"

    def __init__(self, server_url: str = None, timeout: int = 30):
        """
        Initialize WazeClient.

        Args:
            server_url: Ignored - kept for backwards compatibility.
                       We now query Waze API directly.
            timeout: Request timeout in seconds.
        """
        self.timeout = timeout
        self.rate_limiter = RateLimiter(min_delay=1.5, max_delay=30.0)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.waze.com/live-map",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        })

    def get_traffic_notifications(
        self,
        lat_top: float,
        lat_bottom: float,
        lon_left: float,
        lon_right: float,
        max_retries: int = 3
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Query Waze for traffic notifications in a bounding box.
        Returns (alerts, jams) tuple.
        Implements retry logic with exponential backoff.
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                # Wait according to rate limiter
                self.rate_limiter.wait()

                response = self.session.get(
                    self.WAZE_API_URL,
                    params={
                        "top": str(lat_top),
                        "bottom": str(lat_bottom),
                        "left": str(lon_left),
                        "right": str(lon_right),
                        "env": "row",
                        "types": "alerts,traffic,users"
                    },
                    timeout=self.timeout
                )

                # Check for rate limiting responses
                if response.status_code == 429:
                    self.rate_limiter.error()
                    retry_after = int(response.headers.get("Retry-After", 60))
                    time.sleep(retry_after)
                    continue

                if response.status_code == 403:
                    self.rate_limiter.error()
                    # Possible IP block, wait longer
                    time.sleep(30 + random.uniform(0, 30))
                    continue

                response.raise_for_status()
                self.rate_limiter.success()

                data = response.json()

                # Transform alerts to normalize the location format
                alerts = []
                for alert in data.get("alerts", []):
                    # Extract location from nested structure
                    loc = alert.get("location", {})
                    transformed = {
                        **alert,
                        "latitude": loc.get("y", alert.get("latitude")),
                        "longitude": loc.get("x", alert.get("longitude")),
                        # Extract username from wazeData if available
                        "reportBy": self._extract_username(alert)
                    }
                    alerts.append(transformed)

                return alerts, data.get("jams", [])

            except requests.exceptions.RequestException as e:
                self.rate_limiter.error()
                last_error = e
                if attempt < max_retries - 1:
                    # Wait with exponential backoff before retry
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait_time)

        # All retries failed
        raise last_error or Exception("Failed to fetch data after retries")

    def _extract_username(self, alert: Dict[str, Any]) -> str:
        """Extract username from alert data."""
        # wazeData format: "world,lon,lat,uuid" or sometimes contains username
        waze_data = alert.get("wazeData", "")
        if waze_data:
            parts = waze_data.split(",")
            if len(parts) >= 1:
                # First part is often the username prefix (e.g., "world")
                # or could be an actual username
                return parts[0] if parts[0] != "world" else f"world_{parts[-1][:8]}"

        # Fallback: use uuid as identifier
        uuid = alert.get("uuid", "")
        if uuid:
            return f"user_{uuid[:8]}"

        return "anonymous"

    def get_users(
        self,
        lat_top: float,
        lat_bottom: float,
        lon_left: float,
        lon_right: float
    ) -> List[Dict[str, Any]]:
        """Get active Waze users in a bounding box."""
        self.rate_limiter.wait()

        try:
            response = self.session.get(
                self.WAZE_API_URL,
                params={
                    "top": str(lat_top),
                    "bottom": str(lat_bottom),
                    "left": str(lon_left),
                    "right": str(lon_right),
                    "env": "row",
                    "types": "users"
                },
                timeout=self.timeout
            )
            response.raise_for_status()
            self.rate_limiter.success()
            data = response.json()

            users = []
            for user in data.get("users", []):
                loc = user.get("location", {})
                users.append({
                    **user,
                    "latitude": loc.get("y"),
                    "longitude": loc.get("x"),
                })
            return users
        except requests.RequestException:
            self.rate_limiter.error()
            raise

    def health_check(self) -> bool:
        """Check if the Waze API is responding."""
        try:
            self.rate_limiter.wait()
            response = self.session.get(
                self.WAZE_API_URL,
                params={
                    "top": "40.43",
                    "bottom": "40.42",
                    "left": "-3.71",
                    "right": "-3.70",
                    "env": "row",
                    "types": "alerts"
                },
                timeout=5
            )
            if response.status_code == 200:
                self.rate_limiter.success()
                return True
            self.rate_limiter.error()
            return False
        except requests.RequestException:
            self.rate_limiter.error()
            return False

    def get_rate_limit_status(self) -> dict:
        """Get current rate limiter status."""
        return {
            "current_delay": self.rate_limiter.current_delay,
            "consecutive_errors": self.rate_limiter.consecutive_errors,
            "last_request": self.rate_limiter.last_request_time
        }
