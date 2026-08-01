"""Inventaire des URLs par namespace (outil d'audit, exécuter depuis la racine)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.urls import get_resolver
from django.urls.resolvers import URLPattern, URLResolver


def count(resolver):
    n = 0
    for p in resolver.url_patterns:
        if isinstance(p, URLPattern):
            n += 1
        else:
            n += count(p)
    return n


def main():
    res = get_resolver()
    total_root = 0
    grand_total = 0
    for p in res.url_patterns:
        if isinstance(p, URLResolver):
            c = count(p)
            grand_total += c
            print(f"{p.namespace or str(p.pattern):40s} {c}")
        else:
            total_root += 1
    grand_total += total_root
    print(f"{'(patterns racine)':40s} {total_root}")
    print(f"{'TOTAL':40s} {grand_total}")


if __name__ == "__main__":
    main()
