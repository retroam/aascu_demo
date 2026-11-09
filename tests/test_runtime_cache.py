import unittest
from unittest.mock import patch
from runtime_cache import TTLCache, key

class CacheTests(unittest.TestCase):
    def test_expiry_and_copy_isolation(self):
        cache = TTLCache(ttl=5)
        with patch('runtime_cache.time.monotonic', return_value=10):
            cache.put('a', {'rows': [1]})
            hit = cache.get('a')
            hit['rows'].append(2)
            self.assertEqual(cache.get('a'), {'rows': [1]})
        with patch('runtime_cache.time.monotonic', return_value=15):
            self.assertIsNone(cache.get('a'))

    def test_capacity_and_memory_budget(self):
        cache = TTLCache(capacity=2, max_bytes=30)
        cache.put('a', 1); cache.put('b', 2)
        cache.get('a'); cache.put('c', 3)
        self.assertIsNone(cache.get('b'))
        cache.put('huge', 'x' * 40)
        self.assertIsNone(cache.get('huge'))
        self.assertLessEqual(cache.size, 30)
        self.assertEqual(key({'a':1,'b':2}), key({'b':2,'a':1}))
