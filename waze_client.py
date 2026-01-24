# waze_client.py
import requests
from typing import Tuple, List, Dict, Any

class WazeClient:
    def __init__(self, server_url: str, timeout: int = 30):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout

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
        response = requests.get(
            f"{self.server_url}/waze/traffic-notifications",
            params={
                "latTop": str(lat_top),
                "latBottom": str(lat_bottom),
                "lonLeft": str(lon_left),
                "lonRight": str(lon_right)
            },
            timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()
        return data.get("alerts", []), data.get("jams", [])

    def health_check(self) -> bool:
        """Check if the Waze server is responding."""
        try:
            response = requests.get(
                f"{self.server_url}/waze/addressList",
                params={"address": "test"},
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False
