"""
Category Metadata Caching System
Implements efficient caching for frequently accessed category metadata and tax calculation results.
"""

from functools import lru_cache
from typing import Dict, Any, Optional, List
import hashlib
import json
import time
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CategoryCache:
    """
    Caching system for category metadata and tax calculation results.
    Uses both in-memory caching and LRU cache for optimal performance.
    """
    
    def __init__(self, cache_ttl: int = 300):  # 5 minutes default TTL
        self.cache_ttl = cache_ttl
        self.memory_cache = {}
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_requests': 0
        }
    
    def _create_cache_key(self, prefix: str, *args) -> str:
        """Create a consistent cache key from prefix and arguments."""
        key_data = f"{prefix}:{':'.join(map(str, args))}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _is_cache_valid(self, cache_entry: Dict) -> bool:
        """Check if a cache entry is still valid based on TTL."""
        if 'timestamp' not in cache_entry:
            return False
        
        age = time.time() - cache_entry['timestamp']
        return age < self.cache_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if valid."""
        self.cache_stats['total_requests'] += 1
        
        if key in self.memory_cache:
            cache_entry = self.memory_cache[key]
            if self._is_cache_valid(cache_entry):
                self.cache_stats['hits'] += 1
                return cache_entry['data']
            else:
                # Remove expired entry
                del self.memory_cache[key]
                self.cache_stats['evictions'] += 1
        
        self.cache_stats['misses'] += 1
        return None
    
    def set(self, key: str, data: Any) -> None:
        """Set value in cache with timestamp."""
        self.memory_cache[key] = {
            'data': data,
            'timestamp': time.time()
        }
        
        # Clean up old entries if cache gets too large
        if len(self.memory_cache) > 1000:
            self._cleanup_expired_entries()
    
    def _cleanup_expired_entries(self) -> None:
        """Remove expired cache entries."""
        current_time = time.time()
        expired_keys = []
        
        for key, entry in self.memory_cache.items():
            if current_time - entry['timestamp'] > self.cache_ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.memory_cache[key]
            self.cache_stats['evictions'] += 1
        
        logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def clear(self) -> None:
        """Clear all cached data."""
        self.memory_cache.clear()
        logger.info("Category cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.cache_stats['total_requests']
        hit_rate = (self.cache_stats['hits'] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            'cache_size': len(self.memory_cache),
            'cache_ttl': self.cache_ttl,
            'hit_rate': round(hit_rate, 2),
            'stats': self.cache_stats.copy(),
            'timestamp': datetime.now().isoformat()
        }

# Global cache instance
_category_cache = CategoryCache()

@lru_cache(maxsize=128)
def get_expense_categories_cached() -> Dict[str, Dict[str, Any]]:
    """
    Cached version of expense categories metadata.
    Uses LRU cache for static data that rarely changes.
    """
    return {
        'office_admin': {
            'name': 'Office & Admin',
            'tax_deductible': True,
            'is_personal': False,
            'is_statutory': False,
            'description': 'Office supplies, stationery, internet/data, utility bills',
            'examples': ['Office supplies', 'Stationery', 'Internet/Data', 'Electricity'],
            'step': 1
        },
        'staff_wages': {
            'name': 'Staff & Wages',
            'tax_deductible': True,
            'is_personal': False,
            'is_statutory': False,
            'description': 'Employee salaries, wages, and related costs',
            'examples': ['Salaries', 'Wages', 'Staff benefits', 'Payroll costs'],
            'step': 1
        },
        'business_travel': {
            'name': 'Business Travel & Transport',
            'tax_deductible': True,
            'is_personal': False,
            'is_statutory': False,
            'description': 'Fuel, vehicle maintenance, and travel expenses for business',
            'examples': ['Fuel', 'Vehicle maintenance', 'Business travel', 'Transport costs'],
            'step': 1
        },
        'rent_utilities': {
            'name': 'Rent & Utilities',
            'tax_deductible': True,
            'is_personal': False,
            'is_statutory': False,
            'description': 'Rent for shop or business office',
            'examples': ['Shop rent', 'Office rent', 'Business premises rent'],
            'step': 1
        },
        'marketing_sales': {
            'name': 'Marketing & Sales',
            'tax_deductible': True,
            'is_personal': False,
            'is_statutory': False,
            'description': 'Advertising, social media promotion, business cards',
            'examples': ['Advertising', 'Social media promotion', 'Business cards'],
            'step': 1
        },
        'cogs': {
            'name': 'Cost of Goods Sold (COGS)',
            'tax_deductible': True,
            'is_personal': False,
            'is_statutory': False,
            'description': 'Direct costs of producing goods or services',
            'examples': ['Raw materials', 'Manufacturing costs', 'Direct labor'],
            'step': 1
        },
        'personal_expenses': {
            'name': 'Personal Expenses',
            'tax_deductible': False,
            'is_personal': True,
            'is_statutory': False,
            'description': 'Personal expenses not related to business',
            'examples': ['Personal meals', 'Personal shopping', 'Family expenses'],
            'step': None
        },
        'statutory_legal': {
            'name': 'Statutory & Legal Contributions',
            'tax_deductible': True,
            'is_personal': False,
            'is_statutory': True,
            'description': 'Accounting, legal, and consulting fees directly related to business',
            'examples': ['Accounting fees', 'Legal fees', 'Consulting fees'],
            'step': 2
        }
    }

@lru_cache(maxsize=32)
def get_tax_deductible_categories() -> List[str]:
    """Get list of tax-deductible category keys (cached)."""
    categories = get_expense_categories_cached()
    return [key for key, data in categories.items() if data['tax_deductible']]

@lru_cache(maxsize=32)
def get_step1_categories() -> List[str]:
    """Get list of Step 1 (main business) category keys (cached)."""
    categories = get_expense_categories_cached()
    return [key for key, data in categories.items() if data.get('step') == 1]

@lru_cache(maxsize=32)
def get_step2_categories() -> List[str]:
    """Get list of Step 2 (statutory) category keys (cached)."""
    categories = get_expense_categories_cached()
    return [key for key, data in categories.items() if data.get('step') == 2]

def get_cached_category_metadata(category_key: str) -> Optional[Dict[str, Any]]:
    """
    Get category metadata with caching.
    
    Args:
        category_key: Category key to look up
        
    Returns:
        Category metadata dictionary or None if not found
    """
    cache_key = _category_cache._create_cache_key('category_metadata', category_key)
    
    # Try cache first
    cached_data = _category_cache.get(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Get from source and cache
    categories = get_expense_categories_cached()
    metadata = categories.get(category_key)
    
    if metadata:
        _category_cache.set(cache_key, metadata)
    
    return metadata

def get_cached_tax_calculation_summary(user_id: str, tax_year: int) -> Optional[Dict[str, Any]]:
    """
    Get cached tax calculation summary if available.
    
    Args:
        user_id: User ID
        tax_year: Tax year
        
    Returns:
        Cached tax calculation summary or None
    """
    cache_key = _category_cache._create_cache_key('tax_summary', user_id, tax_year)
    return _category_cache.get(cache_key)

def cache_tax_calculation_summary(user_id: str, tax_year: int, summary: Dict[str, Any]) -> None:
    """
    Cache tax calculation summary.
    
    Args:
        user_id: User ID
        tax_year: Tax year
        summary: Tax calculation summary to cache
    """
    cache_key = _category_cache._create_cache_key('tax_summary', user_id, tax_year)
    _category_cache.set(cache_key, summary)

def get_cached_expense_totals(user_id: str, tax_year: int, categories: List[str]) -> Optional[Dict[str, float]]:
    """
    Get cached expense totals by categories.
    
    Args:
        user_id: User ID
        tax_year: Tax year
        categories: List of categories
        
    Returns:
        Cached expense totals or None
    """
    # Create consistent cache key from sorted categories
    sorted_categories = sorted(categories)
    cache_key = _category_cache._create_cache_key('expense_totals', user_id, tax_year, *sorted_categories)
    return _category_cache.get(cache_key)

def cache_expense_totals(user_id: str, tax_year: int, categories: List[str], totals: Dict[str, float]) -> None:
    """
    Cache expense totals by categories.
    
    Args:
        user_id: User ID
        tax_year: Tax year
        categories: List of categories
        totals: Expense totals to cache
    """
    sorted_categories = sorted(categories)
    cache_key = _category_cache._create_cache_key('expense_totals', user_id, tax_year, *sorted_categories)
    _category_cache.set(cache_key, totals)

def invalidate_user_cache(user_id: str) -> None:
    """
    Invalidate all cached data for a specific user.
    Should be called when user data changes.
    
    Args:
        user_id: User ID to invalidate cache for
    """
    keys_to_remove = []
    
    for key in _category_cache.memory_cache.keys():
        # Check if key contains user_id (simple heuristic)
        if user_id in key:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        if key in _category_cache.memory_cache:
            del _category_cache.memory_cache[key]
    
    logger.info(f"Invalidated {len(keys_to_remove)} cache entries for user {user_id}")

def get_cache_stats() -> Dict[str, Any]:
    """Get comprehensive cache statistics."""
    return _category_cache.get_stats()

def clear_all_caches() -> None:
    """Clear all caches including LRU caches."""
    _category_cache.clear()
    
    # Clear LRU caches
    get_expense_categories_cached.cache_clear()
    get_tax_deductible_categories.cache_clear()
    get_step1_categories.cache_clear()
    get_step2_categories.cache_clear()
    
    logger.info("All caches cleared")

# Utility functions for backward compatibility
def is_category_tax_deductible_cached(category_key: str) -> bool:
    """Check if category is tax deductible (cached version)."""
    metadata = get_cached_category_metadata(category_key)
    return metadata.get('tax_deductible', False) if metadata else False

def get_category_display_name_cached(category_key: str) -> str:
    """Get category display name (cached version)."""
    metadata = get_cached_category_metadata(category_key)
    return metadata.get('name', category_key) if metadata else category_key