# NCAA Men's Basketball Score Display Fix - Verification Guide

## Summary
Fixed the score extraction logic to properly handle stringified dict scores from the ESPN API. The fix adds JSON parsing support to handle cases where scores come as JSON strings (e.g., `'{"value": 75}'`) instead of just numeric values.

## Changes Made

1. **Added `json` import** to `sports.py`
2. **Enhanced `extract_score()` function** in `sports.py` to:
   - Detect JSON strings (starting with `{` or `[`)
   - Parse JSON strings using `json.loads()`
   - Extract numeric values from parsed dicts
   - Fall back to regex extraction if JSON parsing fails
   - Added comprehensive debug logging
3. **Enhanced `format_score()` functions** in:
   - `basketball.py` (BasketballLive class)
   - `sports.py` (SportsRecent class)
   - Both now handle stringified dicts the same way

## Testing

### Unit Tests
All unit tests pass (27/27):
```bash
python -m pytest plugins/basketball-scoreboard/test_score_extraction.py -v
```

### Manual Testing with Emulator

To test with the emulator using real ESPN API data:

1. **Enable NCAA Men's Basketball in config**:
   Edit `config/config.json` and ensure:
   ```json
   {
     "basketball-scoreboard": {
       "enabled": true,
       "ncaam": {
         "enabled": true,
         "display_modes": {
           "ncaam_live": true,
           "ncaam_recent": true,
           "ncaam_upcoming": true
         },
         "favorite_teams": ["DUKE", "UNC"]  // Optional
       }
     }
   }
   ```

2. **Run emulator**:
   ```bash
   export EMULATOR=true
   python run.py
   ```
   Or use the script:
   ```bash
   ./run_emulator.sh
   ```

3. **Monitor logs** for score extraction:
   - Look for debug messages showing score values and types
   - Check for any warnings about score extraction failures
   - Verify scores display as numbers (e.g., "75") not strings (e.g., "{'value': 75}")

4. **Verify display**:
   - Check that scores appear correctly on the emulator display
   - Test with live, recent, and upcoming games
   - Verify edge cases: zero scores, missing scores, overtime scores

## Expected Behavior

### Before Fix
- Scores might display as raw API strings: `"{'value': 75}"`
- Warning logs: "Could not extract score from string"

### After Fix
- Scores display as clean numbers: `"75"`
- JSON strings are properly parsed
- Debug logs show successful extraction
- No warnings for valid score formats

## Debug Logging

The fix includes comprehensive debug logging. To see score extraction details:

1. Enable debug logging in config or set log level to DEBUG
2. Look for log messages like:
   - `Raw score value: {...}, type: <class 'dict'>`
   - `Processing string score: '...'`
   - `Parsed JSON string: {...}`
   - `Final extracted score: 75`

## Regression Testing

Verify other sports still work correctly:
- NBA
- WNBA  
- NCAA Women's Basketball
- Other sports using the same base classes

## Files Modified

1. `plugins/basketball-scoreboard/sports.py`
   - Added `import json`
   - Enhanced `extract_score()` function (lines 705-739)
   - Enhanced `format_score()` in SportsRecent class (lines 1689-1727)

2. `plugins/basketball-scoreboard/basketball.py`
   - Enhanced `format_score()` in BasketballLive class (lines 151-185)

3. `plugins/basketball-scoreboard/test_score_extraction.py` (new)
   - Comprehensive unit tests for all score formats

## Known Issues

None. All test cases pass and the fix maintains backward compatibility with existing score formats.

