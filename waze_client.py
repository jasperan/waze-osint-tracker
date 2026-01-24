# waze_client.py
import requests
from typing import Tuple, List, Dict, Any

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
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.waze.com/live-map",
            "Accept": "application/json",
        })

    def get_traffic_notifications(
        self,
        lat_top: float,
        lat_bottom: float,
        lon_left: float,
        lon_right: float
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Query Waze for traffic notifications in a bounding box.
        Returns (alerts, jams) tuple.
        """
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
        response.raise_for_status()
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
                # Extract username from wazeData if available (format: "world,lon,lat,uuid")
                "reportBy": self._extract_username(alert)
            }
            alerts.append(transformed)

        return alerts, data.get("jams", [])

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

    def health_check(self) -> bool:
        """Check if the Waze API is responding."""
        try:
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
            return response.status_code == 200
        except requests.RequestException:
            return False
