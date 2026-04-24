"""
Region Configuration Module
Defines universes, neutralizations, and other region-specific settings
"""

from typing import List, Dict
from dataclasses import dataclass

logger = None  # Will be set by importing module

# Region-specific universe configurations
REGION_UNIVERSES: Dict[str, List[str]] = {
    'USA': ['TOP3000', 'TOP1000', 'TOP500', 'TOP200', 'ILLIQUID_MINVOL1M'],
    'GLB': ['TOP3000', 'MINVOL1M', 'TOPDIV3000'],
    'EUR': ['TOP2500', 'TOP1200', 'TOP800', 'TOP400', 'ILLIQUID_MINVOL1M'],
    'ASI': ['MINVOL1M', 'ILLIQUID_MINVOL1M'],
    'CHN': ['TOP2000U'],
    'IND': ['TOP500']
}

# Default universe per region (first in list)
REGION_DEFAULT_UNIVERSE: Dict[str, str] = {
    'USA': 'TOP3000',
    'GLB': 'TOP3000',
    'EUR': 'TOP2500',  # Fixed: was TOP3000
    'ASI': 'MINVOL1M',
    'CHN': 'TOP2000U',  # Fixed: was TOP3000
    'IND': 'TOP500'
}

# Region-specific neutralization options (all risk neutralizations, no NONE)
REGION_NEUTRALIZATIONS: Dict[str, List[str]] = {
    'USA': ['INDUSTRY', 'SUBINDUSTRY', 'SECTOR', 'COUNTRY', 'REVERSION_AND_MOMENTUM', 'STATISTICAL', 'CROWDING', 'FAST', 'SLOW', 'MARKET', 'SLOW_AND_FAST'],
    'GLB': ['INDUSTRY', 'SUBINDUSTRY', 'SECTOR', 'COUNTRY', 'REVERSION_AND_MOMENTUM', 'STATISTICAL', 'CROWDING', 'FAST', 'SLOW', 'MARKET', 'SLOW_AND_FAST'],
    'EUR': ['INDUSTRY', 'SUBINDUSTRY', 'SECTOR', 'COUNTRY', 'REVERSION_AND_MOMENTUM', 'STATISTICAL', 'CROWDING', 'FAST', 'SLOW', 'MARKET', 'SLOW_AND_FAST'],
    'ASI': ['INDUSTRY', 'SUBINDUSTRY', 'SECTOR', 'COUNTRY', 'REVERSION_AND_MOMENTUM', 'STATISTICAL', 'CROWDING', 'FAST', 'SLOW', 'MARKET', 'SLOW_AND_FAST'],
    'CHN': ['INDUSTRY', 'SUBINDUSTRY', 'SECTOR', 'REVERSION_AND_MOMENTUM', 'CROWDING', 'FAST', 'SLOW', 'MARKET', 'SLOW_AND_FAST'],
    'IND': ['INDUSTRY', 'SUBINDUSTRY', 'SECTOR', 'COUNTRY', 'REVERSION_AND_MOMENTUM', 'STATISTICAL', 'CROWDING', 'FAST', 'SLOW', 'MARKET', 'SLOW_AND_FAST']
}

# Default neutralization per region (first in list - always risk neutralized)
REGION_DEFAULT_NEUTRALIZATION: Dict[str, str] = {
    'USA': 'INDUSTRY',
    'GLB': 'INDUSTRY',
    'EUR': 'INDUSTRY',
    'ASI': 'INDUSTRY',
    'CHN': 'INDUSTRY',
    'IND': 'INDUSTRY'
}


@dataclass
class RegionConfig:
    """Configuration for a specific region"""
    region: str
    universes: List[str]
    default_universe: str
    neutralizations: List[str]
    default_neutralization: str
    delay: int = 1
    
    @classmethod
    def for_region(cls, region: str, delay: int = 1) -> 'RegionConfig':
        """Create region config for a specific region"""
        return cls(
            region=region,
            universes=REGION_UNIVERSES.get(region, ['TOP3000']),
            default_universe=REGION_DEFAULT_UNIVERSE.get(region, 'TOP3000'),
            neutralizations=REGION_NEUTRALIZATIONS.get(region, ['INDUSTRY']),
            default_neutralization=REGION_DEFAULT_NEUTRALIZATION.get(region, 'INDUSTRY'),
            delay=delay
        )
    
    def get_all_universes(self) -> List[str]:
        """Get all available universes for this region"""
        return self.universes
    
    def get_all_neutralizations(self) -> List[str]:
        """Get all available neutralizations for this region (all risk neutralized)"""
        return self.neutralizations


def get_region_config(region: str, delay: int = 1) -> RegionConfig:
    """Get region configuration"""
    return RegionConfig.for_region(region, delay)


def get_default_universe(region: str) -> str:
    """Get default universe for a region"""
    return REGION_DEFAULT_UNIVERSE.get(region, 'TOP3000')


def get_all_universes(region: str) -> List[str]:
    """Get all available universes for a region"""
    return REGION_UNIVERSES.get(region, ['TOP3000'])


def get_all_neutralizations(region: str) -> List[str]:
    """Get all available neutralizations for a region (all risk neutralized, no NONE)"""
    return REGION_NEUTRALIZATIONS.get(region, ['INDUSTRY'])


def get_default_neutralization(region: str) -> str:
    """Get default neutralization for a region (always risk neutralized)"""
    return REGION_DEFAULT_NEUTRALIZATION.get(region, 'INDUSTRY')
