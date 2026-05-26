"""
Global configuration for the WQ Shadow Scorer project.

Controls date ranges, cache paths, demo mode, and data source settings.
"""

from pathlib import Path

# === Paths ===
PROJECT_ROOT = Path(__file__).parent
CACHE_DIR = PROJECT_ROOT / 'cache'
CACHE_DIR.mkdir(exist_ok=True)

# Reference data paths
CONSTANTS_DIR = PROJECT_ROOT.parent / 'constants'
FIELD_CATALOG_PATH = CONSTANTS_DIR / 'data_fields_cache_USA_1_TOP3000.json'
FIELD_CATALOG_D0_PATH = CONSTANTS_DIR / 'data_fields_cache_USA_0_TOP1000.json'

# === Date Ranges ===
DATE_START = '2018-01-01'
DATE_END = '2026-04-30'

# In-sample period
IS_START = '2019-01-01'
IS_END = '2022-12-31'

# Out-of-sample period
OOS_START = '2023-01-01'
OOS_END = '2026-04-30'

# === Data Source Settings ===
DEMO_MODE = True  # Use small ticker list (~50) for testing; set False for full ~3500

# yfinance batch size to avoid rate limiting
YFINANCE_BATCH_SIZE = 100

# Cache invalidation (seconds) — default 7 days
CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

# === API Keys (stubs — user must configure) ===
WIND_API_KEY = 'ak_TZiXoYVbwmgTPa3TeUqP61_FEY9pk3be'
TUSHARE_TOKEN = 'ddd1b26b20ff085ac9b60c9bd902ae76bbff60910863e8cc0168da53'

# SimFin API key placeholder (register free at simfin.com)
SIMFIN_API_KEY = None  # Set via environment variable SIMFIN_API_KEY or here

# === Universe Definitions ===
UNIVERSE_SIZES = {
    'TOP500': 500,
    'TOP1000': 1000,
    'TOP2000': 2000,
    'TOP3000': 3000,
}

# === Demo Tickers ===
# Representative ~50 stocks spanning sectors for testing
DEMO_TICKERS = [
    # Technology
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSM', 'AVGO', 'ORCL', 'CRM',
    # Financials
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'BRK-B', 'V', 'MA',
    # Healthcare
    'JNJ', 'UNH', 'PFE', 'ABBV', 'MRK', 'LLY',
    # Consumer
    'WMT', 'PG', 'KO', 'PEP', 'COST', 'HD', 'NKE', 'MCD',
    # Energy
    'XOM', 'CVX', 'COP', 'SLB',
    # Industrials
    'CAT', 'BA', 'GE', 'HON', 'UPS',
    # Communication
    'DIS', 'NFLX', 'CMCSA', 'T', 'VZ',
    # Materials & Utilities
    'LIN', 'APD', 'NEE', 'DUK', 'SO',
    # Real Estate
    'PLD', 'AMT',
]
