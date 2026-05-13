"""
Data Field Fetcher
Fetches and caches data fields from WorldQuant Brain API
"""

import logging
import json
import os
import requests
from typing import List, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class DataFieldFetcher:
    """
    Fetches data fields from WorldQuant Brain API
    
    Caches data fields by region for cold start
    """
    
    def __init__(self, session: requests.Session = None, cache_dir: str = "constants"):
        """
        Initialize data field fetcher
        
        Args:
            session: Authenticated requests session
            cache_dir: Directory for caching data fields
        """
        self.session = session
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.data_fields: Dict[str, List[Dict]] = {}  # {region: [fields]}
    
    def fetch_data_fields(
        self,
        region: str,
        delay: int = 1,
        universe: str = None,
        force_refresh: bool = False,
        try_all_universes: bool = False
    ) -> List[Dict]:
        """
        Get data fields for a specific region and delay with local caching
        (Matching generation_one approach: fetch by dataset with pagination)
        
        Args:
            region: Region code (USA, EUR, CHN, ASI, etc.)
            delay: Delay value (default: 1)
            universe: Universe code (e.g., "TOP3000", "MINVOL1M")
            force_refresh: Force refresh from API even if cache exists
            try_all_universes: If True and universe fails, try all universes for the region
            
        Returns:
            List of data field dictionaries
        """
        # If universe not specified, try all universes for the region
        if not universe:
            if try_all_universes:
                try:
                    from ..core.region_config import get_all_universes
                    universes_to_try = get_all_universes(region)
                    logger.info(f"[{region}] No universe specified, will try all universes: {universes_to_try}")
                except ImportError:
                    try:
                        from ..core.region_config import get_default_universe
                        universes_to_try = [get_default_universe(region)]
                    except ImportError:
                        universes_to_try = ['TOP3000']
            else:
                try:
                    from ..core.region_config import get_default_universe
                    universes_to_try = [get_default_universe(region)]
                except ImportError:
                    universes_to_try = ['TOP3000']
        else:
            universes_to_try = [universe]
        
        # Try each universe until one succeeds
        all_fields = []
        for universe_to_try in universes_to_try:
            fields = self._fetch_data_fields_for_universe(region, delay, universe_to_try, force_refresh)
            if fields:
                logger.info(f"[{region}] ✅ Successfully fetched {len(fields)} fields for universe {universe_to_try}")
                return fields
            else:
                logger.warning(f"[{region}] ⚠️ No fields found for universe {universe_to_try}, trying next...")
        
        logger.error(f"[{region}] ❌ Failed to fetch fields for any universe: {universes_to_try}")
        return []
    
    def _fetch_data_fields_for_universe(
        self,
        region: str,
        delay: int,
        universe: str,
        force_refresh: bool = False
    ) -> List[Dict]:
        """
        Internal method to fetch data fields for a specific universe
        """
        # Cache file name includes delay and universe (matching generation_one)
        cache_key = f"{region}_{delay}_{universe}"
        cache_file = self.cache_dir / f"data_fields_cache_{cache_key}.json"
        
        # Try cache first (OPTIMIZED: check if already loaded in memory)
        if region in self.data_fields and self.data_fields[region]:
            logger.debug(f"Using in-memory cache for {region} ({len(self.data_fields[region])} fields)")
            return self.data_fields[region]
        
        if not force_refresh and cache_file.exists():
            try:
                logger.info(f"Loading cached data fields for {region} delay={delay}")
                # OPTIMIZED: Check file size first, warn if large
                file_size = cache_file.stat().st_size
                if file_size > 10 * 1024 * 1024:  # > 10MB
                    logger.warning(f"Large cache file ({file_size / 1024 / 1024:.1f}MB), loading may take a moment...")
                
                # OPTIMIZED: Use streaming JSON parser for large files if available
                try:
                    import ijson  # Optional dependency for streaming JSON parsing
                    with open(cache_file, 'rb') as f:
                        cached_data = list(ijson.items(f, 'item'))
                    logger.info(f"Loaded {len(cached_data)} cached fields for {region} delay={delay} (streaming)")
                except ImportError:
                    # Fall back to regular JSON load
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                    logger.info(f"Loaded {len(cached_data)} cached fields for {region} delay={delay}")
                except Exception as e:
                    logger.warning(f"Streaming parser failed: {e}, falling back to regular load")
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                    logger.info(f"Loaded {len(cached_data)} cached fields for {region} delay={delay}")
                
                # Validate that cached data matches the expected parameters
                if cached_data and universe:
                    matching_fields = []
                    for field in cached_data:
                        field_region = field.get('region', '')
                        field_universe = field.get('universe', '')
                        field_delay = field.get('delay', -1)
                        
                        # Only include fields that match ALL parameters exactly
                        if (field_region == region and 
                            field_universe == universe and 
                            field_delay == delay):
                            matching_fields.append(field)
                    
                    if len(matching_fields) == 0:
                        logger.warning(f"⚠️ Cached data doesn't match expected parameters!")
                        logger.warning(f"   Expected: region={region}, universe={universe}, delay={delay}")
                        # Don't return cached data, let it refetch
                    else:
                        logger.info(f"✅ Cached data validation: {len(matching_fields)} fields match exact parameters")
                        self.data_fields[region] = matching_fields
                        return matching_fields
                else:
                    # No universe specified, return all cached data
                    self.data_fields[region] = cached_data
                    return cached_data
                    
            except Exception as e:
                logger.warning(f"Error loading cache: {e}, fetching from API")
        
        # Fetch from API (matching generation_one approach)
        if not self.session:
            logger.error("No session available for fetching data fields")
            return []
        
        if not universe:
            logger.warning(f"No universe specified for {region}, using default")
            # Import region config for default universes
            try:
                from ..core.region_config import get_default_universe
                universe = get_default_universe(region)
            except ImportError:
                # Fallback if region_config not available
                universe_map = {
                    'USA': 'TOP3000',
                    'EUR': 'TOP2500',  # Fixed: was TOP3000
                    'CHN': 'TOP2000U',  # Fixed: was TOP3000
                    'ASI': 'MINVOL1M',
                    'GLB': 'TOP3000',
                    'IND': 'TOP500'
                }
                universe = universe_map.get(region, 'TOP3000')
        
        try:
            logger.info(f"[{region}] No cache found for delay={delay}, fetching from API...")
            logger.info(f"[{region}] Using universe: {universe}")
            
            # First get available datasets from multiple categories (matching generation_one)
            categories = ['fundamental', 'analyst', 'model', 'news', 'alternative']
            all_dataset_ids = []
            
            logger.info(f"[{region}] Fetching datasets from {len(categories)} categories...")
            
            for category in categories:
                datasets_params = {
                    'category': category,
                    'delay': delay,
                    'instrumentType': 'EQUITY',
                    'region': region,
                    'universe': universe,
                    'limit': 20
                }
                
                logger.info(f"[{region}] Getting {category} datasets...")
                try:
                    response = self.session.get('https://api.worldquantbrain.com/data-sets', params=datasets_params)
                    logger.debug(f"[{region}] {category} datasets response status: {response.status_code}")
                    
                    if response.status_code == 200:
                        datasets_data = response.json()
                        available_datasets = datasets_data.get('results', [])
                        category_dataset_ids = [ds.get('id') for ds in available_datasets if ds.get('id')]
                        all_dataset_ids.extend(category_dataset_ids)
                        logger.info(f"[{region}] ✓ Found {len(category_dataset_ids)} {category} datasets")
                    else:
                        logger.warning(f"[{region}] ✗ Failed to get {category} datasets: {response.status_code} - {response.text[:200]}")
                except Exception as e:
                    logger.error(f"[{region}] ✗ Error fetching {category} datasets: {e}", exc_info=True)
            
            # Remove duplicates and use the combined list
            dataset_ids = list(set(all_dataset_ids))
            logger.info(f"[{region}] Total unique datasets found: {len(dataset_ids)}")
            
            if not dataset_ids:
                logger.warning(f"[{region}] No datasets found, using fallback datasets")
                dataset_ids = ['fundamental6', 'fundamental2', 'analyst4', 'model16', 'model51', 'news12']
                logger.info(f"[{region}] Using {len(dataset_ids)} fallback datasets")
            
            logger.info(f"[{region}] Will fetch fields from up to 10 datasets")
            
            # Get fields from datasets with pagination (matching generation_one)
            all_fields = []
            max_datasets = min(10, len(dataset_ids))  # Use up to 10 datasets
            
            logger.info(f"[{region}] Fetching fields from {max_datasets} datasets...")
            
            for idx, dataset in enumerate(dataset_ids[:max_datasets], 1):
                logger.info(f"[{region}] [{idx}/{max_datasets}] Processing dataset: {dataset}")
                dataset_fields = []
                page = 1
                max_pages = 5  # Get up to 5 pages per dataset
                
                while page <= max_pages:
                    try:
                        params = {
                            'dataset.id': dataset,
                            'delay': delay,
                            'instrumentType': 'EQUITY',
                            'region': region,
                            'universe': universe,
                            'limit': 50,  # 50 per page
                            'page': page
                        }
                        
                        logger.debug(f"[{region}] Fetching {dataset} page {page} with params: {params}")
                        response = self.session.get('https://api.worldquantbrain.com/data-fields', params=params)
                        logger.debug(f"[{region}] {dataset} page {page} response status: {response.status_code}")
                        
                        if response.status_code == 200:
                            data = response.json()
                            fields = data.get('results', [])
                            if not fields:  # No more fields on this page
                                logger.debug(f"[{region}] No more fields in {dataset} page {page}, stopping")
                                break
                            dataset_fields.extend(fields)
                            logger.info(f"[{region}] ✓ Found {len(fields)} fields in {dataset} page {page} (total from dataset: {len(dataset_fields)})")
                            page += 1
                        else:
                            logger.warning(f"[{region}] ✗ Failed to get fields from {dataset} page {page}: {response.status_code} - {response.text[:200]}")
                            break
                    except Exception as e:
                        logger.error(f"[{region}] ✗ Error fetching {dataset} page {page}: {e}", exc_info=True)
                        break
                
                all_fields.extend(dataset_fields)
                logger.info(f"[{region}] ✓ Total fields from {dataset}: {len(dataset_fields)}")
            
            # Remove duplicates
            logger.info(f"[{region}] Removing duplicates from {len(all_fields)} total fields...")
            unique_fields = {field['id']: field for field in all_fields}.values()
            field_list = list(unique_fields)
            logger.info(f"[{region}] ✓ {len(field_list)} unique fields after deduplication")
            
            # Filter fields to ensure they match the exact parameters
            logger.info(f"[{region}] Filtering fields to match: region={region}, universe={universe}, delay={delay}")
            filtered_fields = []
            mismatch_count = 0
            
            for field in field_list:
                field_region = field.get('region', '')
                field_universe = field.get('universe', '')
                field_delay = field.get('delay', -1)
                
                # Only include fields that match ALL parameters exactly
                if (field_region == region and 
                    field_universe == universe and 
                    field_delay == delay):
                    filtered_fields.append(field)
                else:
                    mismatch_count += 1
                    if mismatch_count <= 3:  # Log first 3 mismatches for debugging
                        logger.debug(f"[{region}] Field mismatch: {field.get('id', 'unknown')} - "
                                   f"region={field_region} (expected {region}), "
                                   f"universe={field_universe} (expected {universe}), "
                                   f"delay={field_delay} (expected {delay})")
            
            logger.info(f"[{region}] 🔍 Filtered: {len(filtered_fields)} match, {mismatch_count} mismatch")
            
            if len(filtered_fields) == 0:
                logger.warning(f"[{region}] ⚠️ No fields found matching exact parameters!")
                logger.warning(f"[{region}]    Expected: region={region}, universe={universe}, delay={delay}")
                logger.warning(f"[{region}] ⚠️ Using unfiltered fields as fallback (may cause simulation issues)")
                field_list = field_list
            else:
                field_list = filtered_fields
                logger.info(f"[{region}] ✅ Using {len(field_list)} fields that match exact parameters")
            
            # Cache the fetched data
            logger.info(f"[{region}] Caching {len(field_list)} fields...")
            self.data_fields[region] = field_list
            self._save_cache(region, cache_file)
            logger.info(f"[{region}] ✅ Successfully fetched and cached {len(field_list)} data fields")
            
            return field_list
                
        except Exception as e:
            logger.error(f"[{region}] ✗ Error fetching data fields: {e}", exc_info=True)
            logger.error(f"[{region}] Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"[{region}] Traceback:\n{traceback.format_exc()}")
            return []
    
    def _save_cache(self, region: str, cache_file: Path):
        """Save data fields to cache file"""
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.data_fields[region], f, indent=2, ensure_ascii=False)
            logger.info(f"Cached {len(self.data_fields[region])} fields to {cache_file}")
        except Exception as e:
            logger.warning(f"Failed to cache data fields: {e}")
    
    def clear_data_fields_cache(self, region: str = None, delay: int = None):
        """Clear cached data fields for a specific region/delay or all caches"""
        import glob
        
        if region and delay is not None:
            # Clear specific cache
            cache_file = self.cache_dir / f"data_fields_cache_{region}_{delay}.json"
            if cache_file.exists():
                cache_file.unlink()
                logger.info(f"Cleared cache file: {cache_file}")
            else:
                logger.info(f"Cache file not found: {cache_file}")
        else:
            # Clear all cache files
            cache_files = list(self.cache_dir.glob("data_fields_cache_*.json"))
            for cache_file in cache_files:
                cache_file.unlink()
                logger.info(f"Cleared cache file: {cache_file}")
            logger.info(f"Cleared {len(cache_files)} cache files")
    
    def get_fields_by_category(self, region: str, category: str) -> List[Dict]:
        """Get data fields filtered by category"""
        fields = self.data_fields.get(region, [])
        return [f for f in fields if f.get('category', {}).get('id') == category]
    
    def get_fields_by_dataset(self, region: str, dataset: str) -> List[Dict]:
        """Get data fields filtered by dataset"""
        fields = self.data_fields.get(region, [])
        return [f for f in fields if f.get('dataset', {}).get('id') == dataset]
    
    def get_field_by_id(self, region: str, field_id: str) -> Optional[Dict]:
        """Get data field by ID"""
        fields = self.data_fields.get(region, [])
        for field in fields:
            if field.get('id') == field_id:
                return field
        return None
    
    def get_all_categories(self, region: str) -> List[str]:
        """Get all categories for a region"""
        fields = self.data_fields.get(region, [])
        categories = set()
        for field in fields:
            cat = field.get('category', {}).get('id')
            if cat:
                categories.add(cat)
        return sorted(list(categories))
