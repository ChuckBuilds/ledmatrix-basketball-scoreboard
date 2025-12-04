"""
Basketball Scoreboard Plugin for LEDMatrix - Using Existing Managers

This plugin provides NBA, WNBA, NCAA Men's, and NCAA Women's basketball scoreboard 
functionality by reusing proven, working manager classes.
"""

import logging
import time
from typing import Dict, Any, Set, Optional

from PIL import ImageFont

try:
    from src.plugin_system.base_plugin import BasePlugin
    from background_data_service import get_background_service
    from base_odds_manager import BaseOddsManager
except ImportError:
    BasePlugin = None
    get_background_service = None
    BaseOddsManager = None

# Import the manager classes
from nba_managers import NBALiveManager, NBARecentManager, NBAUpcomingManager
from wnba_managers import WNBALiveManager, WNBARecentManager, WNBAUpcomingManager
from ncaam_basketball_managers import (
    NCAAMBasketballLiveManager,
    NCAAMBasketballRecentManager,
    NCAAMBasketballUpcomingManager,
)
from ncaaw_basketball_managers import (
    NCAAWBasketballLiveManager,
    NCAAWBasketballRecentManager,
    NCAAWBasketballUpcomingManager,
)

logger = logging.getLogger(__name__)


class BasketballScoreboardPlugin(BasePlugin if BasePlugin else object):
    """
    Basketball scoreboard plugin using existing manager classes.

    This plugin provides NBA, WNBA, NCAA Men's, and NCAA Women's basketball 
    scoreboard functionality by delegating to proven manager classes.
    """

    def __init__(
        self,
        plugin_id: str,
        config: Dict[str, Any],
        display_manager,
        cache_manager,
        plugin_manager,
    ):
        """Initialize the basketball scoreboard plugin."""
        if BasePlugin:
            super().__init__(
                plugin_id, config, display_manager, cache_manager, plugin_manager
            )

        self.plugin_id = plugin_id
        self.config = config
        self.display_manager = display_manager
        self.cache_manager = cache_manager
        self.plugin_manager = plugin_manager

        self.logger = logger

        # Basic configuration
        self.is_enabled = config.get("enabled", True)
        # Get display dimensions from display_manager properties
        if hasattr(display_manager, 'matrix') and display_manager.matrix is not None:
            self.display_width = display_manager.matrix.width
            self.display_height = display_manager.matrix.height
        else:
            self.display_width = getattr(display_manager, "width", 128)
            self.display_height = getattr(display_manager, "height", 32)

        # League configurations
        self.logger.debug(f"Basketball plugin received config keys: {list(config.keys())}")
        self.logger.debug(f"NBA config: {config.get('nba', {})}")
        
        self.nba_enabled = config.get("nba", {}).get("enabled", False)
        self.wnba_enabled = config.get("wnba", {}).get("enabled", False)
        self.ncaam_enabled = config.get("ncaam", {}).get("enabled", False)
        self.ncaaw_enabled = config.get("ncaaw", {}).get("enabled", False)
        
        self.logger.info(
            f"League enabled states - NBA: {self.nba_enabled}, WNBA: {self.wnba_enabled}, "
            f"NCAA Men's: {self.ncaam_enabled}, NCAA Women's: {self.ncaaw_enabled}"
        )

        # Global settings
        self.display_duration = float(config.get("display_duration", 30))
        self.game_display_duration = float(config.get("game_display_duration", 15))

        # Live priority per league
        self.nba_live_priority = self.config.get("nba", {}).get("live_priority", False)
        self.wnba_live_priority = self.config.get("wnba", {}).get("live_priority", False)
        self.ncaam_live_priority = self.config.get("ncaam", {}).get("live_priority", False)
        self.ncaaw_live_priority = self.config.get("ncaaw", {}).get("live_priority", False)

        # Initialize background service if available
        self.background_service = None
        if get_background_service:
            try:
                self.background_service = get_background_service(
                    self.cache_manager, max_workers=1
                )
                self.logger.info("Background service initialized")
            except Exception as e:
                self.logger.warning(f"Could not initialize background service: {e}")

        # Initialize managers
        self._initialize_managers()

        # Mode cycling
        self.current_mode_index = 0
        self.last_mode_switch = 0
        self.modes = self._get_available_modes()

        self.logger.info(
            f"Basketball scoreboard plugin initialized - {self.display_width}x{self.display_height}"
        )
        self.logger.info(
            f"NBA enabled: {self.nba_enabled}, WNBA enabled: {self.wnba_enabled}, "
            f"NCAA Men's enabled: {self.ncaam_enabled}, NCAA Women's enabled: {self.ncaaw_enabled}"
        )

        # Dynamic duration tracking
        self._dynamic_cycle_seen_modes: Set[str] = set()
        self._dynamic_mode_to_manager_key: Dict[str, str] = {}
        self._dynamic_manager_progress: Dict[str, Set[str]] = {}
        self._dynamic_managers_completed: Set[str] = set()
        self._dynamic_cycle_complete = False
        
        # Track current display context for granular dynamic duration
        self._current_display_league: Optional[str] = None  # 'nba', 'wnba', 'ncaam', 'ncaaw'
        self._current_display_mode_type: Optional[str] = None  # 'live', 'recent', 'upcoming'

    def _initialize_managers(self):
        """Initialize all manager instances."""
        try:
            # Create adapted configs for managers
            nba_config = self._adapt_config_for_manager("nba")
            wnba_config = self._adapt_config_for_manager("wnba")
            ncaam_config = self._adapt_config_for_manager("ncaam")
            ncaaw_config = self._adapt_config_for_manager("ncaaw")

            # Initialize NBA managers if enabled
            if self.nba_enabled:
                self.nba_live = NBALiveManager(
                    nba_config, self.display_manager, self.cache_manager
                )
                self.nba_recent = NBARecentManager(
                    nba_config, self.display_manager, self.cache_manager
                )
                self.nba_upcoming = NBAUpcomingManager(
                    nba_config, self.display_manager, self.cache_manager
                )
                self.logger.info("NBA managers initialized")

            # Initialize WNBA managers if enabled
            if self.wnba_enabled:
                self.wnba_live = WNBALiveManager(
                    wnba_config, self.display_manager, self.cache_manager
                )
                self.wnba_recent = WNBARecentManager(
                    wnba_config, self.display_manager, self.cache_manager
                )
                self.wnba_upcoming = WNBAUpcomingManager(
                    wnba_config, self.display_manager, self.cache_manager
                )
                self.logger.info("WNBA managers initialized")

            # Initialize NCAA Men's managers if enabled
            if self.ncaam_enabled:
                self.ncaam_live = NCAAMBasketballLiveManager(
                    ncaam_config, self.display_manager, self.cache_manager
                )
                self.ncaam_recent = NCAAMBasketballRecentManager(
                    ncaam_config, self.display_manager, self.cache_manager
                )
                self.ncaam_upcoming = NCAAMBasketballUpcomingManager(
                    ncaam_config, self.display_manager, self.cache_manager
                )
                self.logger.info("NCAA Men's managers initialized")

            # Initialize NCAA Women's managers if enabled
            if self.ncaaw_enabled:
                self.ncaaw_live = NCAAWBasketballLiveManager(
                    ncaaw_config, self.display_manager, self.cache_manager
                )
                self.ncaaw_recent = NCAAWBasketballRecentManager(
                    ncaaw_config, self.display_manager, self.cache_manager
                )
                self.ncaaw_upcoming = NCAAWBasketballUpcomingManager(
                    ncaaw_config, self.display_manager, self.cache_manager
                )
                self.logger.info("NCAA Women's managers initialized")

        except Exception as e:
            self.logger.error(f"Error initializing managers: {e}", exc_info=True)

    def _adapt_config_for_manager(self, league: str) -> Dict[str, Any]:
        """
        Adapt plugin config format to manager expected format.

        Plugin uses: nba: {...}, wnba: {...}, etc.
        Managers expect: nba_scoreboard: {...}, wnba_scoreboard: {...}, etc.
        """
        league_config = self.config.get(league, {})
        
        self.logger.debug(f"DEBUG: league_config for {league} = {league_config}")

        # Extract nested configurations
        game_limits = league_config.get("game_limits", {})
        display_options = league_config.get("display_options", {})
        filtering = league_config.get("filtering", {})
        display_modes_config = league_config.get("display_modes", {})

        manager_display_modes = {
            f"{league}_live": display_modes_config.get("show_live", True),
            f"{league}_recent": display_modes_config.get("show_recent", True),
            f"{league}_upcoming": display_modes_config.get("show_upcoming", True),
        }

        # Explicitly check if keys exist for show_favorite_teams_only
        if "show_favorite_teams_only" in filtering:
            show_favorites_only = filtering["show_favorite_teams_only"]
        elif "show_favorite_teams_only" in league_config:
            show_favorites_only = league_config["show_favorite_teams_only"]
        elif "favorite_teams_only" in league_config:
            show_favorites_only = league_config["favorite_teams_only"]
        else:
            show_favorites_only = False
        
        self.logger.debug(
            f"Config reading for {league}: "
            f"league_config.show_favorite_teams_only={league_config.get('show_favorite_teams_only', 'NOT_SET')}, "
            f"filtering.show_favorite_teams_only={filtering.get('show_favorite_teams_only', 'NOT_SET')}, "
            f"final show_favorites_only={show_favorites_only}"
        )

        # Explicitly check if key exists for show_all_live
        if "show_all_live" in filtering:
            show_all_live = filtering["show_all_live"]
        elif "show_all_live" in league_config:
            show_all_live = league_config["show_all_live"]
        else:
            show_all_live = False
        
        self.logger.debug(
            f"Config reading for {league}: "
            f"league_config.show_all_live={league_config.get('show_all_live', 'NOT_SET')}, "
            f"filtering.show_all_live={filtering.get('show_all_live', 'NOT_SET')}, "
            f"final show_all_live={show_all_live}"
        )

        # Logo directory mapping
        LOGO_DIRECTORIES = {
            'nba': 'assets/sports/nba_logos',
            'wnba': 'assets/sports/wnba_logos',
            'ncaam': 'assets/sports/ncaa_logos',
            'ncaaw': 'assets/sports/ncaa_logos',
        }
        
        # Get logo directory from config or use mapping
        default_logo_dir = LOGO_DIRECTORIES.get(league, f"assets/sports/{league}_logos")

        # Create manager config with expected structure
        manager_config = {
            f"{league}_scoreboard": {
                "enabled": league_config.get("enabled", False),
                "favorite_teams": league_config.get("favorite_teams", []),
                "display_modes": manager_display_modes,
                "recent_games_to_show": game_limits.get("recent_games_to_show", 5),
                "upcoming_games_to_show": game_limits.get("upcoming_games_to_show", 10),
                "logo_dir": league_config.get("logo_dir", default_logo_dir),
                "show_records": display_options.get("show_records", False),
                "show_ranking": display_options.get("show_ranking", False),
                "show_odds": display_options.get("show_odds", False),
                "test_mode": league_config.get("test_mode", False),
                "update_interval_seconds": league_config.get(
                    "update_interval_seconds", 300
                ),
                "live_update_interval": league_config.get("live_update_interval", 30),
                "live_game_duration": league_config.get("live_game_duration", 20),
                "live_priority": league_config.get("live_priority", False),
                "show_favorite_teams_only": show_favorites_only,
                "show_all_live": show_all_live,
                "filtering": filtering,
                "background_service": {
                    "request_timeout": 30,
                    "max_retries": 3,
                    "priority": 2,
                },
            }
        }

        # Add global config - get timezone from cache_manager's config_manager if available
        timezone_str = self.config.get("timezone")
        if not timezone_str and hasattr(self.cache_manager, 'config_manager'):
            timezone_str = self.cache_manager.config_manager.get_timezone()
        if not timezone_str:
            timezone_str = "UTC"
        
        # Get display config from main config if available
        display_config = self.config.get("display", {})
        if not display_config and hasattr(self.cache_manager, 'config_manager'):
            display_config = self.cache_manager.config_manager.get_display_config()
        
        manager_config.update(
            {
                "timezone": timezone_str,
                "display": display_config,
            }
        )
        
        self.logger.debug(f"Using timezone: {timezone_str} for {league} managers")

        return manager_config

    def _get_available_modes(self) -> list:
        """Get list of available display modes based on enabled leagues."""
        modes = []

        def league_modes(league: str) -> Dict[str, bool]:
            league_config = self.config.get(league, {})
            display_modes = league_config.get("display_modes", {})
            return {
                "live": display_modes.get("show_live", True),
                "recent": display_modes.get("show_recent", True),
                "upcoming": display_modes.get("show_upcoming", True),
            }

        if self.nba_enabled:
            flags = league_modes("nba")
            prefix = "nba"
            if flags["live"]:
                modes.append(f"{prefix}_live")
            if flags["recent"]:
                modes.append(f"{prefix}_recent")
            if flags["upcoming"]:
                modes.append(f"{prefix}_upcoming")

        if self.wnba_enabled:
            flags = league_modes("wnba")
            prefix = "wnba"
            if flags["live"]:
                modes.append(f"{prefix}_live")
            if flags["recent"]:
                modes.append(f"{prefix}_recent")
            if flags["upcoming"]:
                modes.append(f"{prefix}_upcoming")

        if self.ncaam_enabled:
            flags = league_modes("ncaam")
            prefix = "ncaam"
            if flags["live"]:
                modes.append(f"{prefix}_live")
            if flags["recent"]:
                modes.append(f"{prefix}_recent")
            if flags["upcoming"]:
                modes.append(f"{prefix}_upcoming")

        if self.ncaaw_enabled:
            flags = league_modes("ncaaw")
            prefix = "ncaaw"
            if flags["live"]:
                modes.append(f"{prefix}_live")
            if flags["recent"]:
                modes.append(f"{prefix}_recent")
            if flags["upcoming"]:
                modes.append(f"{prefix}_upcoming")

        # Default to NBA if no leagues enabled
        if not modes:
            modes = ["nba_live", "nba_recent", "nba_upcoming"]

        return modes

    def _get_current_manager(self):
        """Get the current manager based on the current mode."""
        if not self.modes:
            return None

        current_mode = self.modes[self.current_mode_index]

        if current_mode.startswith("nba_"):
            if not self.nba_enabled:
                return None
            mode_type = current_mode.split("_", 1)[1]  # "live", "recent", "upcoming"
            if mode_type == "live":
                return self.nba_live
            elif mode_type == "recent":
                return self.nba_recent
            elif mode_type == "upcoming":
                return self.nba_upcoming

        elif current_mode.startswith("wnba_"):
            if not self.wnba_enabled:
                return None
            mode_type = current_mode.split("_", 1)[1]
            if mode_type == "live":
                return self.wnba_live
            elif mode_type == "recent":
                return self.wnba_recent
            elif mode_type == "upcoming":
                return self.wnba_upcoming

        elif current_mode.startswith("ncaam_"):
            if not self.ncaam_enabled:
                return None
            mode_type = current_mode.split("_", 1)[1]
            if mode_type == "live":
                return self.ncaam_live
            elif mode_type == "recent":
                return self.ncaam_recent
            elif mode_type == "upcoming":
                return self.ncaam_upcoming

        elif current_mode.startswith("ncaaw_"):
            if not self.ncaaw_enabled:
                return None
            mode_type = current_mode.split("_", 1)[1]
            if mode_type == "live":
                return self.ncaaw_live
            elif mode_type == "recent":
                return self.ncaaw_recent
            elif mode_type == "upcoming":
                return self.ncaaw_upcoming

        return None

    def update(self) -> None:
        """Update basketball game data."""
        if not self.is_enabled:
            return

        try:
            # Update NBA managers if enabled
            if self.nba_enabled:
                self.nba_live.update()
                self.nba_recent.update()
                self.nba_upcoming.update()

            # Update WNBA managers if enabled
            if self.wnba_enabled:
                self.wnba_live.update()
                self.wnba_recent.update()
                self.wnba_upcoming.update()

            # Update NCAA Men's managers if enabled
            if self.ncaam_enabled:
                self.ncaam_live.update()
                self.ncaam_recent.update()
                self.ncaam_upcoming.update()

            # Update NCAA Women's managers if enabled
            if self.ncaaw_enabled:
                self.ncaaw_live.update()
                self.ncaaw_recent.update()
                self.ncaaw_upcoming.update()

        except Exception as e:
            self.logger.error(f"Error updating managers: {e}", exc_info=True)

    def display(self, display_mode: str = None, force_clear: bool = False) -> bool:
        """Display basketball games with mode cycling.
        
        Args:
            display_mode: Optional mode name (e.g., 'basketball_live', 'basketball_recent', 'basketball_upcoming').
                         If provided, displays that specific mode. If None, uses internal mode cycling.
            force_clear: If True, clear display before rendering
        """
        if not self.is_enabled:
            return False

        try:
            # If display_mode is provided, use it to determine which manager to call
            if display_mode:
                self.logger.debug(f"Display called with mode: {display_mode}")
                # Map external mode names to internal managers
                # External modes: basketball_live, basketball_recent, basketball_upcoming
                # Internal modes: nba_live, nba_recent, nba_upcoming, wnba_live, etc.
                
                # Extract the mode type (live, recent, upcoming)
                mode_type = None
                if display_mode.endswith('_live'):
                    mode_type = 'live'
                elif display_mode.endswith('_recent'):
                    mode_type = 'recent'
                elif display_mode.endswith('_upcoming'):
                    mode_type = 'upcoming'
                
                if not mode_type:
                    self.logger.warning(f"Unknown display_mode: {display_mode}")
                    return False
                
                self.logger.debug(
                    f"Mode type: {mode_type}, NBA enabled: {self.nba_enabled}, "
                    f"WNBA enabled: {self.wnba_enabled}, NCAA Men's enabled: {self.ncaam_enabled}, "
                    f"NCAA Women's enabled: {self.ncaaw_enabled}"
                )
                
                # Determine which manager to use based on enabled leagues
                # Try leagues in priority order: NBA > WNBA > NCAA Men's > NCAA Women's
                managers_to_try = []
                
                if self.nba_enabled:
                    if mode_type == 'live' and hasattr(self, 'nba_live'):
                        managers_to_try.append(self.nba_live)
                    elif mode_type == 'recent' and hasattr(self, 'nba_recent'):
                        managers_to_try.append(self.nba_recent)
                    elif mode_type == 'upcoming' and hasattr(self, 'nba_upcoming'):
                        managers_to_try.append(self.nba_upcoming)
                
                if self.wnba_enabled:
                    if mode_type == 'live' and hasattr(self, 'wnba_live'):
                        managers_to_try.append(self.wnba_live)
                    elif mode_type == 'recent' and hasattr(self, 'wnba_recent'):
                        managers_to_try.append(self.wnba_recent)
                    elif mode_type == 'upcoming' and hasattr(self, 'wnba_upcoming'):
                        managers_to_try.append(self.wnba_upcoming)
                
                if self.ncaam_enabled:
                    if mode_type == 'live' and hasattr(self, 'ncaam_live'):
                        managers_to_try.append(self.ncaam_live)
                    elif mode_type == 'recent' and hasattr(self, 'ncaam_recent'):
                        managers_to_try.append(self.ncaam_recent)
                    elif mode_type == 'upcoming' and hasattr(self, 'ncaam_upcoming'):
                        managers_to_try.append(self.ncaam_upcoming)
                
                if self.ncaaw_enabled:
                    if mode_type == 'live' and hasattr(self, 'ncaaw_live'):
                        managers_to_try.append(self.ncaaw_live)
                    elif mode_type == 'recent' and hasattr(self, 'ncaaw_recent'):
                        managers_to_try.append(self.ncaaw_recent)
                    elif mode_type == 'upcoming' and hasattr(self, 'ncaaw_upcoming'):
                        managers_to_try.append(self.ncaaw_upcoming)
                
                # Try each manager until one returns True (has content)
                for current_manager in managers_to_try:
                    if current_manager:
                        # Track which league we're displaying for granular dynamic duration
                        if current_manager == self.nba_live or current_manager == self.nba_recent or current_manager == self.nba_upcoming:
                            self._current_display_league = 'nba'
                        elif current_manager == self.wnba_live or current_manager == self.wnba_recent or current_manager == self.wnba_upcoming:
                            self._current_display_league = 'wnba'
                        elif current_manager == self.ncaam_live or current_manager == self.ncaam_recent or current_manager == self.ncaam_upcoming:
                            self._current_display_league = 'ncaam'
                        elif current_manager == self.ncaaw_live or current_manager == self.ncaaw_recent or current_manager == self.ncaaw_upcoming:
                            self._current_display_league = 'ncaaw'
                        self._current_display_mode_type = mode_type
                        
                        result = current_manager.display(force_clear)
                        # If display returned True, we have content to show
                        if result is True:
                            try:
                                self._record_dynamic_progress(current_manager)
                            except Exception as progress_err:
                                self.logger.debug(
                                    "Dynamic progress tracking failed: %s", progress_err
                                )
                            self._evaluate_dynamic_cycle_completion()
                            return result
                        # If result is False, try next manager
                        elif result is False:
                            continue
                        # If result is None or other, assume success
                        else:
                            try:
                                self._record_dynamic_progress(current_manager)
                            except Exception as progress_err:
                                self.logger.debug(
                                    "Dynamic progress tracking failed: %s", progress_err
                                )
                            self._evaluate_dynamic_cycle_completion()
                            return True
                
                # No manager had content
                if not managers_to_try:
                    self.logger.warning(
                        f"No managers available for mode: {display_mode} "
                        f"(NBA: {self.nba_enabled}, WNBA: {self.wnba_enabled}, "
                        f"NCAA Men's: {self.ncaam_enabled}, NCAA Women's: {self.ncaaw_enabled})"
                    )
                else:
                    self.logger.debug(
                        f"No content available for mode: {display_mode} after trying {len(managers_to_try)} manager(s)"
                    )
                
                # Clear display when no content available (safety measure)
                if force_clear:
                    try:
                        self.display_manager.clear()
                        self.display_manager.update_display()
                    except Exception as clear_err:
                        self.logger.debug(f"Error clearing display when no content: {clear_err}")
                return False
            
            # Fall back to internal mode cycling if no display_mode provided
            current_time = time.time()

            # Check if we should stay on live mode
            should_stay_on_live = False
            if self.has_live_content():
                # Get current mode name
                current_mode = self.modes[self.current_mode_index] if self.modes else None
                # If we're on a live mode, stay there
                if current_mode and current_mode.endswith('_live'):
                    should_stay_on_live = True
                # If we're not on a live mode but have live content, switch to it
                elif not (current_mode and current_mode.endswith('_live')):
                    # Find the first live mode
                    for i, mode in enumerate(self.modes):
                        if mode.endswith('_live'):
                            self.current_mode_index = i
                            force_clear = True
                            self.last_mode_switch = current_time
                            self.logger.info(f"Live content detected - switching to display mode: {mode}")
                            break

            # Handle mode cycling only if not staying on live
            if not should_stay_on_live and current_time - self.last_mode_switch >= self.display_duration:
                self.current_mode_index = (self.current_mode_index + 1) % len(
                    self.modes
                )
                self.last_mode_switch = current_time
                force_clear = True

                current_mode = self.modes[self.current_mode_index]
                self.logger.info(f"Switching to display mode: {current_mode}")

            # Get current manager and display
            current_manager = self._get_current_manager()
            if current_manager:
                # Track which league/mode we're displaying for granular dynamic duration
                current_mode = self.modes[self.current_mode_index] if self.modes else None
                if current_mode:
                    if current_mode.startswith("nba_"):
                        self._current_display_league = 'nba'
                        self._current_display_mode_type = current_mode.split("_", 1)[1]
                    elif current_mode.startswith("wnba_"):
                        self._current_display_league = 'wnba'
                        self._current_display_mode_type = current_mode.split("_", 1)[1]
                    elif current_mode.startswith("ncaam_"):
                        self._current_display_league = 'ncaam'
                        self._current_display_mode_type = current_mode.split("_", 1)[1]
                    elif current_mode.startswith("ncaaw_"):
                        self._current_display_league = 'ncaaw'
                        self._current_display_mode_type = current_mode.split("_", 1)[1]
                
                result = current_manager.display(force_clear)
                if result is not False:
                    try:
                        self._record_dynamic_progress(current_manager)
                    except Exception as progress_err:
                        self.logger.debug(
                            "Dynamic progress tracking failed: %s", progress_err
                        )
                else:
                    # Manager returned False (no content) - ensure display is cleared
                    if force_clear:
                        try:
                            self.display_manager.clear()
                            self.display_manager.update_display()
                        except Exception as clear_err:
                            self.logger.debug(f"Error clearing display when manager returned False: {clear_err}")
                self._evaluate_dynamic_cycle_completion()
                return result
            else:
                self.logger.warning("No manager available for current mode")
                return False

        except Exception as e:
            self.logger.error(f"Error in display method: {e}", exc_info=True)
            return False

    def has_live_priority(self) -> bool:
        if not self.is_enabled:
            return False
        return (
            (self.nba_enabled and self.nba_live_priority)
            or (self.wnba_enabled and self.wnba_live_priority)
            or (self.ncaam_enabled and self.ncaam_live_priority)
            or (self.ncaaw_enabled and self.ncaaw_live_priority)
        )

    def has_live_content(self) -> bool:
        if not self.is_enabled:
            return False

        # Check NBA live content
        nba_live = False
        if (
            self.nba_enabled
            and self.nba_live_priority
            and hasattr(self, "nba_live")
        ):
            live_games = getattr(self.nba_live, "live_games", [])
            if live_games:
                favorite_teams = getattr(self.nba_live, "favorite_teams", [])
                if favorite_teams:
                    nba_live = any(
                        game.get("home_abbr") in favorite_teams
                        or game.get("away_abbr") in favorite_teams
                        for game in live_games
                    )
                else:
                    nba_live = True

        # Check WNBA live content
        wnba_live = False
        if (
            self.wnba_enabled
            and self.wnba_live_priority
            and hasattr(self, "wnba_live")
        ):
            live_games = getattr(self.wnba_live, "live_games", [])
            if live_games:
                favorite_teams = getattr(self.wnba_live, "favorite_teams", [])
                if favorite_teams:
                    wnba_live = any(
                        game.get("home_abbr") in favorite_teams
                        or game.get("away_abbr") in favorite_teams
                        for game in live_games
                    )
                else:
                    wnba_live = True

        # Check NCAA Men's live content
        ncaam_live = False
        if (
            self.ncaam_enabled
            and self.ncaam_live_priority
            and hasattr(self, "ncaam_live")
        ):
            live_games = getattr(self.ncaam_live, "live_games", [])
            if live_games:
                favorite_teams = getattr(self.ncaam_live, "favorite_teams", [])
                if favorite_teams:
                    ncaam_live = any(
                        game.get("home_abbr") in favorite_teams
                        or game.get("away_abbr") in favorite_teams
                        for game in live_games
                    )
                else:
                    ncaam_live = True

        # Check NCAA Women's live content
        ncaaw_live = False
        if (
            self.ncaaw_enabled
            and self.ncaaw_live_priority
            and hasattr(self, "ncaaw_live")
        ):
            live_games = getattr(self.ncaaw_live, "live_games", [])
            if live_games:
                favorite_teams = getattr(self.ncaaw_live, "favorite_teams", [])
                if favorite_teams:
                    ncaaw_live = any(
                        game.get("home_abbr") in favorite_teams
                        or game.get("away_abbr") in favorite_teams
                        for game in live_games
                    )
                else:
                    ncaaw_live = True

        return nba_live or wnba_live or ncaam_live or ncaaw_live

    def get_live_modes(self) -> list:
        if not self.is_enabled:
            return []

        prioritized_modes = []
        if self.nba_enabled and self.nba_live_priority and "nba_live" in self.modes:
            prioritized_modes.append("nba_live")

        if self.wnba_enabled and self.wnba_live_priority and "wnba_live" in self.modes:
            prioritized_modes.append("wnba_live")

        if self.ncaam_enabled and self.ncaam_live_priority and "ncaam_live" in self.modes:
            prioritized_modes.append("ncaam_live")

        if self.ncaaw_enabled and self.ncaaw_live_priority and "ncaaw_live" in self.modes:
            prioritized_modes.append("ncaaw_live")

        if prioritized_modes:
            return prioritized_modes

        # Fallback: no prioritized league enabled; expose any live modes available
        return [mode for mode in self.modes if mode.endswith("_live")]

    def get_info(self) -> Dict[str, Any]:
        """Get plugin information."""
        try:
            current_manager = self._get_current_manager()
            current_mode = self.modes[self.current_mode_index] if self.modes else "none"

            info = {
                "plugin_id": self.plugin_id,
                "name": "Basketball Scoreboard",
                "version": "2.0.0",
                "enabled": self.is_enabled,
                "display_size": f"{self.display_width}x{self.display_height}",
                "nba_enabled": self.nba_enabled,
                "wnba_enabled": self.wnba_enabled,
                "ncaam_enabled": self.ncaam_enabled,
                "ncaaw_enabled": self.ncaaw_enabled,
                "current_mode": current_mode,
                "available_modes": self.modes,
                "display_duration": self.display_duration,
                "game_display_duration": self.game_display_duration,
                "live_priority": {
                    "nba": self.nba_enabled and self.nba_live_priority,
                    "wnba": self.wnba_enabled and self.wnba_live_priority,
                    "ncaam": self.ncaam_enabled and self.ncaam_live_priority,
                    "ncaaw": self.ncaaw_enabled and self.ncaaw_live_priority,
                },
                "show_records": getattr(current_manager, "mode_config", {}).get(
                    "show_records"
                )
                if current_manager
                else None,
                "show_ranking": getattr(current_manager, "mode_config", {}).get(
                    "show_ranking"
                )
                if current_manager
                else None,
                "show_odds": getattr(current_manager, "mode_config", {}).get(
                    "show_odds"
                )
                if current_manager
                else None,
                "managers_initialized": {
                    "nba_live": hasattr(self, "nba_live"),
                    "nba_recent": hasattr(self, "nba_recent"),
                    "nba_upcoming": hasattr(self, "nba_upcoming"),
                    "wnba_live": hasattr(self, "wnba_live"),
                    "wnba_recent": hasattr(self, "wnba_recent"),
                    "wnba_upcoming": hasattr(self, "wnba_upcoming"),
                    "ncaam_live": hasattr(self, "ncaam_live"),
                    "ncaam_recent": hasattr(self, "ncaam_recent"),
                    "ncaam_upcoming": hasattr(self, "ncaam_upcoming"),
                    "ncaaw_live": hasattr(self, "ncaaw_live"),
                    "ncaaw_recent": hasattr(self, "ncaaw_recent"),
                    "ncaaw_upcoming": hasattr(self, "ncaaw_upcoming"),
                },
            }

            # Add manager-specific info if available
            if current_manager and hasattr(current_manager, "get_info"):
                try:
                    manager_info = current_manager.get_info()
                    info["current_manager_info"] = manager_info
                except Exception as e:
                    info["current_manager_info"] = f"Error getting manager info: {e}"

            return info

        except Exception as e:
            self.logger.error(f"Error getting plugin info: {e}")
            return {
                "plugin_id": self.plugin_id,
                "name": "Basketball Scoreboard",
                "error": str(e),
            }

    # ------------------------------------------------------------------
    # Dynamic duration hooks
    # ------------------------------------------------------------------
    def reset_cycle_state(self) -> None:
        """Reset dynamic cycle tracking."""
        super().reset_cycle_state()
        self._dynamic_cycle_seen_modes.clear()
        self._dynamic_mode_to_manager_key.clear()
        self._dynamic_manager_progress.clear()
        self._dynamic_managers_completed.clear()
        self._dynamic_cycle_complete = False

    def is_cycle_complete(self) -> bool:
        """Report whether the plugin has shown a full cycle of content."""
        if not self._dynamic_feature_enabled():
            return True
        self._evaluate_dynamic_cycle_completion()
        return self._dynamic_cycle_complete

    def _dynamic_feature_enabled(self) -> bool:
        """Return True when dynamic duration should be active."""
        if not self.is_enabled:
            return False
        return self.supports_dynamic_duration()
    
    def supports_dynamic_duration(self) -> bool:
        """
        Check if dynamic duration is enabled for the current display context.
        Checks granular settings: per-league/per-mode > per-mode > per-league > global.
        """
        if not self.is_enabled:
            return False
        
        # If no current display context, check global setting
        if not self._current_display_league or not self._current_display_mode_type:
            return super().supports_dynamic_duration()
        
        league = self._current_display_league
        mode_type = self._current_display_mode_type
        
        # Check per-league/per-mode setting first (most specific)
        league_config = self.config.get(league, {})
        league_dynamic = league_config.get("dynamic_duration", {})
        league_modes = league_dynamic.get("modes", {})
        mode_config = league_modes.get(mode_type, {})
        if "enabled" in mode_config:
            return bool(mode_config.get("enabled", False))
        
        # Check per-league setting
        if "enabled" in league_dynamic:
            return bool(league_dynamic.get("enabled", False))
        
        # Check global per-mode setting
        global_dynamic = self.config.get("dynamic_duration", {})
        global_modes = global_dynamic.get("modes", {})
        global_mode_config = global_modes.get(mode_type, {})
        if "enabled" in global_mode_config:
            return bool(global_mode_config.get("enabled", False))
        
        # Fall back to global setting
        return super().supports_dynamic_duration()
    
    def get_dynamic_duration_cap(self) -> Optional[float]:
        """
        Get dynamic duration cap for the current display context.
        Checks granular settings: per-league/per-mode > per-mode > per-league > global.
        """
        if not self.is_enabled:
            return None
        
        # If no current display context, check global setting
        if not self._current_display_league or not self._current_display_mode_type:
            return super().get_dynamic_duration_cap()
        
        league = self._current_display_league
        mode_type = self._current_display_mode_type
        
        # Check per-league/per-mode setting first (most specific)
        league_config = self.config.get(league, {})
        league_dynamic = league_config.get("dynamic_duration", {})
        league_modes = league_dynamic.get("modes", {})
        mode_config = league_modes.get(mode_type, {})
        if "max_duration_seconds" in mode_config:
            try:
                cap = float(mode_config.get("max_duration_seconds"))
                if cap > 0:
                    return cap
            except (TypeError, ValueError):
                pass
        
        # Check per-league setting
        if "max_duration_seconds" in league_dynamic:
            try:
                cap = float(league_dynamic.get("max_duration_seconds"))
                if cap > 0:
                    return cap
            except (TypeError, ValueError):
                pass
        
        # Check global per-mode setting
        global_dynamic = self.config.get("dynamic_duration", {})
        global_modes = global_dynamic.get("modes", {})
        global_mode_config = global_modes.get(mode_type, {})
        if "max_duration_seconds" in global_mode_config:
            try:
                cap = float(global_mode_config.get("max_duration_seconds"))
                if cap > 0:
                    return cap
            except (TypeError, ValueError):
                pass
        
        # Fall back to global setting
        return super().get_dynamic_duration_cap()

    def _get_manager_for_mode(self, mode_name: str):
        """Resolve manager instance for a given display mode."""
        if mode_name.startswith("nba_"):
            if not self.nba_enabled:
                return None
            suffix = mode_name.split("_", 1)[1]
            if suffix == "live":
                return getattr(self, "nba_live", None)
            if suffix == "recent":
                return getattr(self, "nba_recent", None)
            if suffix == "upcoming":
                return getattr(self, "nba_upcoming", None)
        elif mode_name.startswith("wnba_"):
            if not self.wnba_enabled:
                return None
            suffix = mode_name.split("_", 1)[1]
            if suffix == "live":
                return getattr(self, "wnba_live", None)
            if suffix == "recent":
                return getattr(self, "wnba_recent", None)
            if suffix == "upcoming":
                return getattr(self, "wnba_upcoming", None)
        elif mode_name.startswith("ncaam_"):
            if not self.ncaam_enabled:
                return None
            suffix = mode_name.split("_", 1)[1]
            if suffix == "live":
                return getattr(self, "ncaam_live", None)
            if suffix == "recent":
                return getattr(self, "ncaam_recent", None)
            if suffix == "upcoming":
                return getattr(self, "ncaam_upcoming", None)
        elif mode_name.startswith("ncaaw_"):
            if not self.ncaaw_enabled:
                return None
            suffix = mode_name.split("_", 1)[1]
            if suffix == "live":
                return getattr(self, "ncaaw_live", None)
            if suffix == "recent":
                return getattr(self, "ncaaw_recent", None)
            if suffix == "upcoming":
                return getattr(self, "ncaaw_upcoming", None)
        return None

    def _record_dynamic_progress(self, current_manager) -> None:
        """Track progress through managers/games for dynamic duration."""
        if not self._dynamic_feature_enabled() or not self.modes:
            self._dynamic_cycle_complete = True
            return

        current_mode = self.modes[self.current_mode_index]
        self._dynamic_cycle_seen_modes.add(current_mode)

        manager_key = self._build_manager_key(current_mode, current_manager)
        self._dynamic_mode_to_manager_key[current_mode] = manager_key

        total_games = self._get_total_games_for_manager(current_manager)
        if total_games <= 1:
            # Single (or no) game - treat as complete once visited
            self._dynamic_managers_completed.add(manager_key)
            return

        current_index = getattr(current_manager, "current_game_index", None)
        if current_index is None:
            # Fall back to zero if the manager does not expose an index
            current_index = 0
        identifier = f"index-{current_index}"

        progress_set = self._dynamic_manager_progress.setdefault(manager_key, set())
        progress_set.add(identifier)

        # Drop identifiers that no longer exist if game list shrinks
        valid_identifiers = {f"index-{idx}" for idx in range(total_games)}
        progress_set.intersection_update(valid_identifiers)

        if len(progress_set) >= total_games:
            self._dynamic_managers_completed.add(manager_key)

    def _evaluate_dynamic_cycle_completion(self) -> None:
        """Determine whether all enabled modes have completed their cycles."""
        if not self._dynamic_feature_enabled():
            self._dynamic_cycle_complete = True
            return

        if not self.modes:
            self._dynamic_cycle_complete = True
            return

        required_modes = [mode for mode in self.modes if mode]
        if not required_modes:
            self._dynamic_cycle_complete = True
            return

        for mode_name in required_modes:
            if mode_name not in self._dynamic_cycle_seen_modes:
                self._dynamic_cycle_complete = False
                return

            manager_key = self._dynamic_mode_to_manager_key.get(mode_name)
            if not manager_key:
                self._dynamic_cycle_complete = False
                return

            if manager_key not in self._dynamic_managers_completed:
                manager = self._get_manager_for_mode(mode_name)
                total_games = self._get_total_games_for_manager(manager)
                if total_games <= 1:
                    self._dynamic_managers_completed.add(manager_key)
                else:
                    self._dynamic_cycle_complete = False
                    return

        self._dynamic_cycle_complete = True

    @staticmethod
    def _build_manager_key(mode_name: str, manager) -> str:
        manager_name = manager.__class__.__name__ if manager else "None"
        return f"{mode_name}:{manager_name}"

    @staticmethod
    def _get_total_games_for_manager(manager) -> int:
        if manager is None:
            return 0
        for attr in ("live_games", "games_list", "recent_games", "upcoming_games"):
            value = getattr(manager, attr, None)
            if isinstance(value, list):
                return len(value)
        return 0

    def cleanup(self) -> None:
        """Clean up resources."""
        try:
            if hasattr(self, "background_service") and self.background_service:
                # Clean up background service if needed
                pass
            self.logger.info("Basketball scoreboard plugin cleanup completed")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
