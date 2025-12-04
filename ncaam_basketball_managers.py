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
ESPN_NCAAMB_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
)


class BaseNCAAMBasketballManager(Basketball):
    """Base class for NCAA Men's Basketball managers with common functionality."""

    # Class variables for warning tracking
    _no_data_warning_logged = False
    _last_warning_time = 0
    _warning_cooldown = 60
    _shared_data = None
    _last_shared_update = 0

    def __init__(self, config: Dict[str, Any], display_manager, cache_manager):
        self.logger = logging.getLogger("NCAAM")
        super().__init__(
            config=config,
            display_manager=display_manager,
            cache_manager=cache_manager,
            logger=self.logger,
            sport_key="ncaam",
        )

        # Check display modes to determine what data to fetch
        display_modes = self.mode_config.get("display_modes", {})
        self.recent_enabled = display_modes.get("ncaam_recent", False)
        self.upcoming_enabled = display_modes.get("ncaam_upcoming", False)
        self.live_enabled = display_modes.get("ncaam_live", False)

        self.logger.info(
            f"Initialized NCAA Men's manager with display dimensions: {self.display_width}x{self.display_height}"
        )
        self.logger.info(f"Logo directory: {self.logo_dir}")
        self.logger.info(
            f"Display modes - Recent: {self.recent_enabled}, Upcoming: {self.upcoming_enabled}, Live: {self.live_enabled}"
        )
        self.league = "mens-college-basketball"

    def _fetch_ncaam_api_data(self, use_cache: bool = True) -> Optional[Dict]:
        """
        Fetches the full season schedule for NCAA Men's Basketball using background threading.
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
                url=ESPN_NCAAMB_SCOREBOARD_URL,
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
                    ESPN_NCAAMB_SCOREBOARD_URL,
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
        if isinstance(self, NCAAMBasketballLiveManager):
            return self._fetch_todays_games()
        else:
            return self._fetch_ncaam_api_data(use_cache=True)


class NCAAMBasketballLiveManager(BaseNCAAMBasketballManager, BasketballLive):
    """Manager for live NCAA Men's Basketball games."""

    def __init__(self, config: Dict[str, Any], display_manager, cache_manager):
        super().__init__(config, display_manager, cache_manager)
        self.logger = logging.getLogger("NCAAMBasketballLiveManager")

        if self.test_mode:
            self.current_game = {
                "id": "test001",
                "home_abbr": "DUKE",
                "home_id": "123",
                "away_abbr": "UNC",
                "away_id": "456",
                "home_score": "78",
                "away_score": "75",
                "period": 2,
                "period_text": "Q2",
                "clock": "05:30",
                "home_logo_path": Path(self.logo_dir, "DUKE.png"),
                "away_logo_path": Path(self.logo_dir, "UNC.png"),
                "is_live": True,
                "is_final": False,
                "is_upcoming": False,
                "is_halftime": False,
                "status_text": "Q2 05:30",
            }
            self.live_games = [self.current_game]
            self.logger.info("Initialized NCAAMBasketballLiveManager with test game: UNC vs DUKE")
        else:
            self.logger.info("Initialized NCAAMBasketballLiveManager in live mode")


class NCAAMBasketballRecentManager(BaseNCAAMBasketballManager, SportsRecent):
    """Manager for recently completed NCAA Men's Basketball games."""

    def __init__(self, config: Dict[str, Any], display_manager, cache_manager):
        super().__init__(config, display_manager, cache_manager)
        self.logger = logging.getLogger("NCAAMBasketballRecentManager")
        self.logger.info(
            f"Initialized NCAAMBasketballRecentManager with {len(self.favorite_teams)} favorite teams"
        )


class NCAAMBasketballUpcomingManager(BaseNCAAMBasketballManager, SportsUpcoming):
    """Manager for upcoming NCAA Men's Basketball games."""

    def __init__(self, config: Dict[str, Any], display_manager, cache_manager):
        super().__init__(config, display_manager, cache_manager)
        self.logger = logging.getLogger("NCAAMBasketballUpcomingManager")
        self.logger.info(
            f"Initialized NCAAMBasketballUpcomingManager with {len(self.favorite_teams)} favorite teams"
        )

