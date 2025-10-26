"""
Basketball Scoreboard Plugin for LEDMatrix - Standalone Version

Completely independent plugin that doesn't rely on Basketball or Sports base classes.
Contains all functionality needed for displaying basketball games.

API Version: 1.0.0
"""

import logging
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image, ImageDraw

from src.plugin_system.base_plugin import BasePlugin
from basketball_helpers import BasketballHelpers

logger = logging.getLogger(__name__)

# ESPN API URLs
ESPN_NBA_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_WNBA_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard"
ESPN_NCAAMB_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
ESPN_NCAAWB_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball/scoreboard"


class BasketballPluginManager(BasePlugin):
    """
    Standalone basketball scoreboard plugin.
    
    No dependencies on Basketball or Sports base classes.
    All functionality is self-contained.
    """
    
    def __init__(
        self,
        plugin_id: str,
        config: Dict[str, Any],
        display_manager,
        cache_manager,
        plugin_manager
    ):
        """Initialize the standalone basketball plugin."""
        super().__init__(plugin_id, config, display_manager, cache_manager, plugin_manager)
        
        # Get display dimensions
        self.display_width = display_manager.matrix.width
        self.display_height = display_manager.matrix.height
        
        # Initialize helpers with display dimensions
        self.helpers = BasketballHelpers(self.logger, self.display_width, self.display_height)
        
        # Load fonts
        self.fonts = self.helpers.load_fonts()
        
        # Set up HTTP session with headers
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'LEDMatrix-Basketball-Plugin/1.0',
            'Accept': 'application/json',
        }
        
        # Configure leagues
        self.league_configs = self._build_league_configs(config)
        
        # State tracking
        self.current_games = []
        self.current_game = None
        self.current_mode = None
        
        # Configuration
        self.display_duration = config.get('display_duration', 15)
        
        # Log initialization
        enabled = [k for k, v in self.league_configs.items() if v['enabled']]
        self.logger.info(f"Basketball plugin initialized with leagues: {enabled}")
    
    def _build_league_configs(self, config: Dict) -> Dict:
        """Build league configuration dictionary."""
        return {
            'nba': {
                'enabled': config.get('nba_enabled', True),
                'url': ESPN_NBA_SCOREBOARD_URL,
                'logo_dir': Path('assets/sports/nba_logos'),
                'favorite_teams': config.get('nba_favorite_teams', []),
                'display_modes': {
                    'nba_live': config.get('nba_display_modes_live', True),
                    'nba_recent': config.get('nba_display_modes_recent', True),
                    'nba_upcoming': config.get('nba_display_modes_upcoming', True),
                },
            },
            'wnba': {
                'enabled': config.get('wnba_enabled', False),
                'url': ESPN_WNBA_SCOREBOARD_URL,
                'logo_dir': Path('assets/sports/wnba_logos'),
                'favorite_teams': config.get('wnba_favorite_teams', []),
                'display_modes': {
                    'wnba_live': config.get('wnba_display_modes_live', True),
                    'wnba_recent': config.get('wnba_display_modes_recent', True),
                    'wnba_upcoming': config.get('wnba_display_modes_upcoming', True),
                },
            },
            'ncaam': {
                'enabled': config.get('ncaam_basketball_enabled', False),
                'url': ESPN_NCAAMB_SCOREBOARD_URL,
                'logo_dir': Path('assets/sports/ncaa_logos'),
                'favorite_teams': config.get('ncaam_basketball_favorite_teams', []),
                'display_modes': {
                    'ncaam_basketball_live': config.get('ncaam_basketball_display_modes_live', True),
                    'ncaam_basketball_recent': config.get('ncaam_basketball_display_modes_recent', True),
                    'ncaam_basketball_upcoming': config.get('ncaam_basketball_display_modes_upcoming', True),
                },
            },
            'ncaaw': {
                'enabled': config.get('ncaaw_basketball_enabled', False),
                'url': ESPN_NCAAWB_SCOREBOARD_URL,
                'logo_dir': Path('assets/sports/ncaa_logos'),
                'favorite_teams': config.get('ncaaw_basketball_favorite_teams', []),
                'display_modes': {
                    'ncaaw_basketball_live': config.get('ncaaw_basketball_display_modes_live', True),
                    'ncaaw_basketball_recent': config.get('ncaaw_basketball_display_modes_recent', True),
                    'ncaaw_basketball_upcoming': config.get('ncaaw_basketball_display_modes_upcoming', True),
                },
            },
        }
    
    def update(self) -> None:
        """Update game data for all enabled leagues."""
        try:
            all_games = []
            
            for league_key, league_config in self.league_configs.items():
                if not league_config['enabled']:
                    continue
                
                games = self._fetch_league_games(league_key, league_config)
                for game in games:
                    game['league_key'] = league_key
                    game['league_config'] = league_config
                all_games.extend(games)
            
            self.current_games = all_games
            self.logger.debug(f"Updated basketball data: {len(all_games)} total games")
            
        except Exception as e:
            self.logger.error(f"Error updating basketball data: {e}", exc_info=True)
    
    def _fetch_league_games(self, league_key: str, league_config: Dict) -> List[Dict]:
        """Fetch games for a specific league."""
        try:
            # Build cache key
            cache_key = f"basketball_{league_key}_{datetime.now().strftime('%Y%m%d')}"
            
            # Check cache
            cached = self.cache_manager.get(cache_key)
            if cached:
                self.logger.debug(f"Using cached data for {league_key}")
                return cached
            
            # Fetch from API
            response = self.session.get(league_config['url'], headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Extract games
            games = []
            for event in data.get('events', []):
                game = self.helpers.extract_game_details(event)
                if game:
                    # Add logo paths
                    logo_dir = league_config['logo_dir']
                    game['home_logo_path'] = logo_dir / f"{game['home_abbr']}.png"
                    game['away_logo_path'] = logo_dir / f"{game['away_abbr']}.png"
                    games.append(game)
            
            # Cache the results
            self.cache_manager.set(cache_key, games, ttl=3600)
            
            return games
            
        except Exception as e:
            self.logger.error(f"Error fetching {league_key} games: {e}", exc_info=True)
            return []
    
    def display(self, force_clear: bool = False, display_mode: str = None) -> None:
        """Display basketball games."""
        try:
            mode = display_mode or self._determine_display_mode()
            
            if not mode:
                self._display_no_games()
                return
            
            # Filter games for mode
            filtered_games = self._filter_games_for_mode(mode)
            
            if not filtered_games:
                self._display_no_games()
                return
            
            # Display first game
            self.current_game = filtered_games[0]
            self._draw_scorebug_layout(self.current_game, force_clear)
            
        except Exception as e:
            self.logger.error(f"Error displaying game: {e}", exc_info=True)
    
    def _determine_display_mode(self) -> Optional[str]:
        """Determine display mode based on available games."""
        # Priority: live > recent > upcoming
        for game in self.current_games:
            if game.get('is_live'):
                return f"{game['league_key']}_live"
        for game in self.current_games:
            if game.get('is_final'):
                return f"{game['league_key']}_recent"
        for game in self.current_games:
            if game.get('is_upcoming'):
                return f"{game['league_key']}_upcoming"
        return None
    
    def _filter_games_for_mode(self, mode: str) -> List[Dict]:
        """Filter games based on display mode."""
        filtered = []
        
        for game in self.current_games:
            league_config = game.get('league_config', {})
            display_modes = league_config.get('display_modes', {})
            
            if mode in display_modes and display_modes[mode]:
                if 'live' in mode and game.get('is_live'):
                    filtered.append(game)
                elif 'recent' in mode and game.get('is_final'):
                    filtered.append(game)
                elif 'upcoming' in mode and game.get('is_upcoming'):
                    filtered.append(game)
        
        return filtered[:5]
    
    def _draw_scorebug_layout(self, game: Dict, force_clear: bool = False) -> None:
        """Draw the basketball scorebug layout."""
        try:
            # Create main image and overlay
            main_img = Image.new('RGBA', (self.display_width, self.display_height), (0, 0, 0, 255))
            overlay = Image.new('RGBA', (self.display_width, self.display_height), (0, 0, 0, 0))
            draw_overlay = ImageDraw.Draw(overlay)
            
            # Load logos
            logo_dir = game['league_config']['logo_dir']
            home_logo_path = logo_dir / f"{game['home_abbr']}.png"
            away_logo_path = logo_dir / f"{game['away_abbr']}.png"
            
            home_logo = self.helpers.load_and_resize_logo(game['home_abbr'], home_logo_path)
            away_logo = self.helpers.load_and_resize_logo(game['away_abbr'], away_logo_path)
            
            if not home_logo or not away_logo:
                self.logger.error("Failed to load logos")
                draw_final = ImageDraw.Draw(main_img.convert('RGB'))
                self.helpers.draw_text_with_outline(
                    draw_final, "Logo Error", (5, 5), self.fonts['status']
                )
                self.display_manager.image.paste(main_img.convert('RGB'), (0, 0))
                self.display_manager.update_display()
                return
            
            center_y = self.display_height // 2
            
            # Draw logos
            home_x = self.display_width - home_logo.width + 10
            home_y = center_y - (home_logo.height // 2)
            main_img.paste(home_logo, (home_x, home_y), home_logo)
            
            away_x = -10
            away_y = center_y - (away_logo.height // 2)
            main_img.paste(away_logo, (away_x, away_y), away_logo)
            
            # Period and clock (top center)
            period_clock_text = f"{game.get('period_text', '')} {game.get('clock', '')}".strip()
            status_width = draw_overlay.textlength(period_clock_text, font=self.fonts['time'])
            status_x = (self.display_width - status_width) // 2
            self.helpers.draw_text_with_outline(
                draw_overlay, period_clock_text, (status_x, 1), self.fonts['time']
            )
            
            # Scores (centered)
            score_text = f"{game.get('away_score', '0')}-{game.get('home_score', '0')}"
            score_width = draw_overlay.textlength(score_text, font=self.fonts['score'])
            score_x = (self.display_width - score_width) // 2
            score_y = (self.display_height // 2) - 3
            self.helpers.draw_text_with_outline(
                draw_overlay, score_text, (score_x, score_y), self.fonts['score']
            )
            
            # Composite and display
            main_img = Image.alpha_composite(main_img, overlay)
            main_img = main_img.convert('RGB')
            
            self.display_manager.image.paste(main_img, (0, 0))
            self.display_manager.update_display()
            
        except Exception as e:
            self.logger.error(f"Error drawing scorebug: {e}", exc_info=True)
    
    def _display_no_games(self) -> None:
        """Display 'no games' message."""
        try:
            img = Image.new('RGB', (self.display_width, self.display_height), (0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.text((5, 12), "No Games", fill=(150, 150, 150))
            self.display_manager.image = img.copy()
            self.display_manager.update_display()
        except Exception as e:
            self.logger.error(f"Error displaying no games: {e}", exc_info=True)
    
    def get_display_duration(self) -> float:
        """Get display duration."""
        return self.display_duration
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        self.current_games = []
        self.logger.info("Basketball plugin cleaned up")
