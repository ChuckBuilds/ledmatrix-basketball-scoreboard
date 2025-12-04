import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytz
import requests

from basketball import Basketball, BasketballLive
from sports import SportsRecent, SportsUpcoming

# Constants
ESPN_NCAAWB_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard"
)


class BaseNCAAWBasketballManager(Basketball):
    """Base class for NCAA Women's Basketball managers with common functionality."""

    # Class variables for warning tracking
    _no_data_warning_logged = False
    _last_warning_time = 0
    _warning_cooldown = 60
    _shared_data = None
    _last_shared_update = 0

    def __init__(self, config: Dict[str, Any], display_manager, cache_manager):
        self.logger = logging.getLogger("NCAAW")
        super().__init__(
            config=config,
            display_manager=display_manager,
            cache_manager=cache_manager,
            logger=self.logger,
            sport_key="ncaaw",
        )

        # Check display modes to determine what data to fetch
        display_modes = self.mode_config.get("display_modes", {})
        self.recent_enabled = display_modes.get("ncaaw_recent", False)
        self.upcoming_enabled = display_modes.get("ncaaw_upcoming", False)
        self.live_enabled = display_modes.get("ncaaw_live", False)

        self.logger.info(
            f"Initialized NCAA Women's manager with display dimensions: {self.display_width}x{self.display_height}"
        )
        self.logger.info(f"Logo directory: {self.logo_dir}")
        self.logger.info(
            f"Display modes - Recent: {self.recent_enabled}, Upcoming: {self.upcoming_enabled}, Live: {self.live_enabled}"
        )
        self.league = "womens-college-basketball"

    def _fetch_ncaaw_api_data(self, use_cache: bool = True) -> Optional[Dict]:
        """
        Fetches the full season schedule for NCAA Women's Basketball using background threading.
        Returns cached data immediately if available, otherwise starts background fetch.
        """
        now = datetime.now(pytz.utc)
        season_year = now.year
        # NCAA season typically runs from November to April
        if now.month < 11:
            season_year = now.year - 1
        datestring = f"{season_year}1101-{season_year+1}0430"
        cache_key = f"{self.sport_key}_schedule_{season_year}"

        # Check cache first
        if use_cache:
            cached_data = self.cache_manager.get(cache_key)
            if cached_data:
                if isinstance(cached_data, dict) and "events" in cached_data:
                    self.logger.info(f"Using cached schedule for {season_year}")
                    return cached_data
                elif isinstance(cached_data, list):
                    self.logger.info(
                        f"Using cached schedule for {season_year} (legacy format)"
                    )
                    return {"events": cached_data}
                else:
                    self.logger.warning(
                        f"Invalid cached data format for {season_year}: {type(cached_data)}"
                    )
                    self.cache_manager.delete(cache_key)

        # Start background fetch if service is available
        if self.background_service and self.background_enabled:
            self.logger.info(
                f"Starting background fetch for {season_year} season schedule..."
            )

            def fetch_callback(result):
                """Callback when background fetch completes."""
                if result.success:
                    self.logger.info(
                        f"Background fetch completed for {season_year}: {len(result.data.get('events'))} events"
                    )
                else:
                    self.logger.error(
                        f"Background fetch failed for {season_year}: {result.error}"
                    )

                if season_year in self.background_fetch_requests:
                    del self.background_fetch_requests[season_year]

            background_config = self.mode_config.get("background_service", {})
            timeout = background_config.get("request_timeout", 30)
            max_retries = background_config.get("max_retries", 3)
            priority = background_config.get("priority", 2)

            request_id = self.background_service.submit_fetch_request(
                sport="basketball",
                year=season_year,
                url=ESPN_NCAAWB_SCOREBOARD_URL,
                cache_key=cache_key,
                params={"dates": datestring, "limit": 1000},
                headers=self.headers,
                timeout=timeout,
                max_retries=max_retries,
                priority=priority,
                callback=fetch_callback,
            )

            self.background_fetch_requests[season_year] = request_id

            partial_data = self._get_weeks_data()
            if partial_data:
                return partial_data
        else:
            self.logger.warning(
                "Background service not available, using synchronous fetch"
            )
            try:
                response = self.session.get(
                    ESPN_NCAAWB_SCOREBOARD_URL,
                    params={"dates": datestring, "limit": 1000},
                    headers=self.headers,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                self.cache_manager.set(cache_key, data)
                self.logger.info(f"Synchronously fetched {season_year} season schedule")
                return data

            except Exception as e:
                self.logger.error(f"Failed to fetch {season_year} season schedule: {e}")
                return None

    def _fetch_data(self) -> Optional[Dict]:
        """Fetch data using shared data mechanism or direct fetch for live."""
        if isinstance(self, NCAAWBasketballLiveManager):
            return self._fetch_todays_games()
        else:
            return self._fetch_ncaaw_api_data(use_cache=True)


class NCAAWBasketballLiveManager(BaseNCAAWBasketballManager, BasketballLive):
    """Manager for live NCAA Women's Basketball games."""

    def __init__(self, config: Dict[str, Any], display_manager, cache_manager):
        super().__init__(config, display_manager, cache_manager)
        self.logger = logging.getLogger("NCAAWBasketballLiveManager")

        if self.test_mode:
            self.current_game = {
                "id": "test001",
                "home_abbr": "UCONN",
                "home_id": "123",
                "away_abbr": "SCAR",
                "away_id": "456",
                "home_score": "72",
                "away_score": "68",
                "period": 2,
                "period_text": "Q2",
                "clock": "03:45",
                "home_logo_path": Path(self.logo_dir, "UCONN.png"),
                "away_logo_path": Path(self.logo_dir, "SCAR.png"),
                "is_live": True,
                "is_final": False,
                "is_upcoming": False,
                "is_halftime": False,
                "status_text": "Q2 03:45",
            }
            self.live_games = [self.current_game]
            self.logger.info("Initialized NCAAWBasketballLiveManager with test game: SCAR vs UCONN")
        else:
            self.logger.info("Initialized NCAAWBasketballLiveManager in live mode")


class NCAAWBasketballRecentManager(BaseNCAAWBasketballManager, SportsRecent):
    """Manager for recently completed NCAA Women's Basketball games."""

    def __init__(self, config: Dict[str, Any], display_manager, cache_manager):
        super().__init__(config, display_manager, cache_manager)
        self.logger = logging.getLogger("NCAAWBasketballRecentManager")
        self.logger.info(
            f"Initialized NCAAWBasketballRecentManager with {len(self.favorite_teams)} favorite teams"
        )


class NCAAWBasketballUpcomingManager(BaseNCAAWBasketballManager, SportsUpcoming):
    """Manager for upcoming NCAA Women's Basketball games."""

    def __init__(self, config: Dict[str, Any], display_manager, cache_manager):
        super().__init__(config, display_manager, cache_manager)
        self.logger = logging.getLogger("NCAAWBasketballUpcomingManager")
        self.logger.info(
            f"Initialized NCAAWBasketballUpcomingManager with {len(self.favorite_teams)} favorite teams"
        )

