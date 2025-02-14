"""
Test the in memory cache by executing the same query twice. The first time we 'miss'
the cache and load the files into the cache for the second time to 'hit'.
"""
import os
import sys

sys.path.insert(1, os.path.join(sys.path[0], "../.."))

import opteryx
from opteryx.managers.cache import MemoryCache
from opteryx.shared import BufferPool


def test_in_memory_cache():
    cache = MemoryCache(size=5)
    _buffer = BufferPool()
    _buffer.reset(True)

    # read the data once, this should populate the cache
    conn = opteryx.connect(cache=cache)
    cur = conn.cursor()
    cur.execute("SELECT * FROM testdata.flat.tweets WITH(NO_PARTITION);")
    cur.arrow()

    stats = cur.stats
    assert stats.get("cache_hits", 0) == 0
    assert stats["cache_misses"] == 2, stats["cache_misses"]
    conn.close()

    # read the data a second time, this should hit the cache
    conn = opteryx.connect(cache=cache)
    cur = conn.cursor()
    cur.execute("SELECT * FROM testdata.flat.tweets WITH(NO_PARTITION);")
    cur.arrow()

    stats = cur.stats
    assert stats["cache_hits"] == 2, stats["cache_hits"]
    assert stats.get("cache_misses", 0) == 0
    conn.close()

    # read the data with the no cache directive
    conn = opteryx.connect(cache=cache)
    cur = conn.cursor()
    cur.execute("SELECT * FROM testdata.flat.tweets WITH (NO_CACHE, NO_PARTITION);")
    cur.arrow()

    stats = cur.stats
    assert stats.get("cache_hits", 0) == 0, stats["cache_hits"]
    assert stats.get("cache_misses", 0) == 0, stats["cache_misses"]
    conn.close()


# @skip
def test_cache_in_subqueries():
    cache = MemoryCache(size=5)
    _buffer = BufferPool()
    _buffer.reset(True)

    # read the data once, this should populate the cache
    conn = opteryx.connect(cache=cache)
    cur = conn.cursor()
    cur.execute("SELECT * FROM (SELECT * FROM testdata.flat.tweets WITH(NO_PARTITION));")
    cur.arrow()

    stats = cur.stats
    assert stats.get("cache_hits", 0) == 0, stats["cache_hits"]
    assert stats["cache_misses"] == 2, stats["cache_misses"]
    conn.close()

    # read the data a second time, this should hit the cache
    conn = opteryx.connect(cache=cache)
    cur = conn.cursor()
    cur.execute("SELECT * FROM (SELECT * FROM testdata.flat.tweets WITH(NO_PARTITION));")
    cur.arrow()

    stats = cur.stats
    assert stats["cache_hits"] == 2, stats["cache_hits"]
    assert stats.get("cache_misses", 0) == 0
    conn.close()

    # read the data with the no cache directive
    conn = opteryx.connect(cache=cache)
    cur = conn.cursor()
    cur.execute("SELECT * FROM (SELECT * FROM testdata.flat.tweets WITH(NO_CACHE, NO_PARTITION));")
    cur.arrow()

    stats = cur.stats
    assert stats.get("cache_hits", 0) == 0
    assert stats.get("cache_misses", 0) == 0
    conn.close()


if __name__ == "__main__":  # pragma: no cover
    from tests.tools import run_tests

    run_tests()
