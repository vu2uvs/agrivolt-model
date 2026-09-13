"""Upstream data sources.

One module per provider. Every module exposes plain functions that return
pandas objects and caches raw responses under `data/cache`, so a repeated run
is offline and byte-identical.
"""
