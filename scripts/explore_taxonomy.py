"""Discover Etsy taxonomy IDs for product categories.

Run with:
    python -m scripts.explore_taxonomy

Fetches the full Etsy seller taxonomy tree and searches for nodes
matching "Planner", "Calendar", or a custom search term.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

# Ensure project root is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.monitoring.logger import setup_logging
from src.publisher.auth import EtsyAuth, EtsyAuthError
from src.publisher.listing import EtsyListingManager, ETSY_API_BASE
from src.storage.database import get_session_factory, init_db
from src.utils.rate_limiter import TokenBucketRateLimiter


def _search_nodes(
    nodes: list[dict],
    search_terms: list[str],
    parent_path: str = "",
) -> list[dict]:
    """Recursively search taxonomy nodes for matching names.

    Args:
        nodes: List of taxonomy node dicts from the Etsy API.
        search_terms: Lowercased terms to match against node names.
        parent_path: Breadcrumb path for display purposes.

    Returns:
        List of matching node dicts with an added 'path' key.
    """
    matches: list[dict] = []
    for node in nodes:
        name = node.get("name", "")
        node_id = node.get("id")
        full_path = f"{parent_path} > {name}" if parent_path else name

        # Check if any search term appears in the node name
        name_lower = name.lower()
        if any(term in name_lower for term in search_terms):
            matches.append({
                "id": node_id,
                "name": name,
                "path": full_path,
                "level": node.get("level"),
                "parent_id": node.get("parent_id"),
            })

        # Recurse into children
        children = node.get("children", [])
        if children:
            matches.extend(_search_nodes(children, search_terms, full_path))

    return matches


def main():
    load_dotenv()
    logger = setup_logging()

    api_key = os.getenv("ETSY_API_KEY", "").strip()
    shared_secret = os.getenv("ETSY_SHARED_SECRET", "").strip()

    if not api_key:
        print("ERROR: ETSY_API_KEY not found in .env file.")
        sys.exit(1)

    # Initialise DB and session
    init_db()
    session_factory = get_session_factory()
    session = session_factory()

    auth = EtsyAuth(api_key=api_key, shared_secret=shared_secret, session=session)
    rate_limiter = TokenBucketRateLimiter(requests_per_second=5.0, requests_per_day=10_000)
    listing_mgr = EtsyListingManager(auth=auth, rate_limiter=rate_limiter)

    # Allow a custom search term via command-line argument
    if len(sys.argv) > 1:
        search_terms = [term.lower() for term in sys.argv[1:]]
    else:
        search_terms = ["planner", "calendar"]

    print()
    print("=" * 60)
    print("  Etsy Taxonomy Explorer")
    print("=" * 60)
    print(f"  Searching for: {', '.join(search_terms)}")
    print()

    # Fetch the full taxonomy tree
    try:
        resp = listing_mgr._api_request("GET", "/v3/application/seller-taxonomy/nodes")
    except (EtsyAuthError, Exception) as exc:
        print(f"Failed to fetch taxonomy: {exc}")
        session.close()
        sys.exit(1)

    # The API returns {"count": N, "results": [...]}
    nodes = resp.get("results", [])
    if not nodes:
        print("No taxonomy nodes returned. Check your API credentials.")
        session.close()
        sys.exit(1)

    matches = _search_nodes(nodes, search_terms)

    if not matches:
        print(f"No categories found matching: {', '.join(search_terms)}")
        print("Try different search terms, e.g.:")
        print("  python -m scripts.explore_taxonomy planner organizer")
    else:
        print(f"Found {len(matches)} matching categories:\n")
        for m in matches:
            print(f"  ID: {m['id']}")
            print(f"  Name: {m['name']}")
            print(f"  Path: {m['path']}")
            if m.get("level") is not None:
                print(f"  Level: {m['level']}")
            print()

        # Suggest the most specific match
        deepest = max(matches, key=lambda x: (x.get("level") or 0))
        print("-" * 60)
        print(f"  Suggested taxonomy_id: {deepest['id']}")
        print(f"  Category: {deepest['path']}")
        print()
        print("  Set this in your .env file:")
        print(f"    ETSY_TAXONOMY_ID={deepest['id']}")
        print()
        print("  Or in config/config.yaml:")
        print(f"    taxonomy_id: {deepest['id']}")

    print()
    session.close()


if __name__ == "__main__":
    main()
