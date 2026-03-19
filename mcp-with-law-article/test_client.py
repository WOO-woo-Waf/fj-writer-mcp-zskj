"""
Test suite for legal article MCP service.
Run tests with: python -m pytest test_client.py -v
Or run directly: python test_client.py
"""

import asyncio
from typing import Any, Dict, List

from client import LegalMCPClient


class TestLegalMCP:
    """Test cases for legal article MCP client."""

    @staticmethod
    async def test_list_tools():
        """Test listing available tools."""
        print("\n" + "=" * 80)
        print("TEST: List Available Tools")
        print("=" * 80)

        client = LegalMCPClient()
        try:
            tools = await client.list_tools()
            print(f"✓ Found {len(tools)} tools:")
            for tool in tools:
                print(f"  - {tool['name']}: {tool['description']}")
            return True
        except Exception as e:
            print(f"✗ Error: {e}")
            return False

    @staticmethod
    async def test_get_article():
        """Test getting a specific article."""
        print("\n" + "=" * 80)
        print("TEST: Get Specific Article")
        print("=" * 80)

        client = LegalMCPClient()
        try:
            result = await client.get_article("第264条", "刑法")
            print(f"Query: section=第264条, law=刑法")
            if result:
                print(f"✓ Found article:")
                print(f"  ID: {result.get('id')}")
                print(f"  Title: {result.get('title')}")
                print(f"  Section: {result.get('section_number')}")
                print(f"  Content (first 100 chars): {str(result.get('content', ''))[:100]}...")
                print(f"  URL: {result.get('url')}")
                print(f"  Updated: {result.get('updated_at')}")
                return True
            else:
                print(f"⚠ No article found")
                return True  # Not necessarily an error
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    async def test_search_basic():
        """Test basic keyword search."""
        print("\n" + "=" * 80)
        print("TEST: Basic Keyword Search")
        print("=" * 80)

        client = LegalMCPClient()
        try:
            results = await client.search_article("盗窃罪", page=1, page_size=5)
            print(f"Query: text='盗窃罪', page=1, page_size=5")
            print(f"✓ Found {len(results)} results:")
            for i, article in enumerate(results[:3], 1):
                print(f"\n  [{i}] {article.get('title')} - {article.get('section_number')}")
                print(f"      Content: {str(article.get('content', ''))[:80]}...")
            return len(results) > 0
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    async def test_search_with_sort():
        """Test search with sorting options."""
        print("\n" + "=" * 80)
        print("TEST: Search with Sorting")
        print("=" * 80)

        client = LegalMCPClient()
        results_by_relevance = []
        results_by_date = []

        try:
            print("\n--- Sort by Relevance (DESC) ---")
            results_by_relevance = await client.search_article(
                "刑法", page=1, page_size=5, sort_by="relevance", order="desc"
            )
            print(f"✓ Found {len(results_by_relevance)} results")
            for i, article in enumerate(results_by_relevance[:3], 1):
                print(f"  [{i}] {article.get('title')} - Relevance: {article.get('relevance', 'N/A')}")

            print("\n--- Sort by Updated Time (DESC) ---")
            results_by_date = await client.search_article(
                "刑法", page=1, page_size=5, sort_by="updated_at", order="desc"
            )
            print(f"✓ Found {len(results_by_date)} results")
            for i, article in enumerate(results_by_date[:3], 1):
                print(f"  [{i}] {article.get('title')} - Updated: {article.get('updated_at')}")

            return True
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    async def test_search_pagination():
        """Test search pagination."""
        print("\n" + "=" * 80)
        print("TEST: Pagination")
        print("=" * 80)

        client = LegalMCPClient()
        try:
            print("\n--- Page 1 (page_size=5) ---")
            page1 = await client.search_article(
                "罪", page=1, page_size=5, sort_by="id", order="asc"
            )
            print(f"✓ Page 1: {len(page1)} results")
            if page1:
                print(f"  First ID: {page1[0].get('id')}")
                print(f"  Last ID: {page1[-1].get('id')}")

            print("\n--- Page 2 (page_size=5) ---")
            page2 = await client.search_article(
                "罪", page=2, page_size=5, sort_by="id", order="asc"
            )
            print(f"✓ Page 2: {len(page2)} results")
            if page2:
                print(f"  First ID: {page2[0].get('id')}")
                print(f"  Last ID: {page2[-1].get('id')}")

            print("\n--- Page '2' (string), page_size '5' (string) ---")
            page2_str = await client.search_article(
                "罪", page="2", page_size="5", sort_by="id", order="asc"
            )
            print(f"✓ Page '2': {len(page2_str)} results")

            # Verify no overlap
            if page1 and page2:
                page1_ids = {article.get("id") for article in page1}
                page2_ids = {article.get("id") for article in page2}
                overlap = page1_ids & page2_ids
                if not overlap:
                    print("\n✓ No overlap between pages")
                else:
                    print(f"\n⚠ Found {len(overlap)} overlapping IDs")

            if page2 and page2_str:
                same_page = [a.get("id") for a in page2] == [a.get("id") for a in page2_str]
                print("✓ String pagination matches numeric pagination" if same_page else "⚠ String pagination differs")

            return True
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    async def test_search_multiple_keywords():
        """Test search with different keywords."""
        print("\n" + "=" * 80)
        print("TEST: Multiple Keywords")
        print("=" * 80)

        client = LegalMCPClient()
        keywords = ["盗窃罪", "诈骗罪", "贿赂罪", "杀人罪"]

        try:
            for keyword in keywords:
                results = await client.search_article(keyword, page=1, page_size=3)
                print(f"  '{keyword}': {len(results)} results")
                if results:
                    print(f"    Top match: {results[0].get('title')}")
            return True
        except Exception as e:
            print(f"✗ Error: {e}")
            return False


async def run_all_tests():
    """Run all tests."""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "Legal Article MCP Test Suite" + " " * 30 + "║")
    print("╚" + "=" * 78 + "╝")

    results = {}

    # Run tests
    results["list_tools"] = await TestLegalMCP.test_list_tools()
    results["get_article"] = await TestLegalMCP.test_get_article()
    results["search_basic"] = await TestLegalMCP.test_search_basic()
    results["search_sort"] = await TestLegalMCP.test_search_with_sort()
    results["pagination"] = await TestLegalMCP.test_search_pagination()
    results["keywords"] = await TestLegalMCP.test_search_multiple_keywords()

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"✓ Passed: {passed}/{total}")
    for name, result in results.items():
        status = "✓" if result else "✗"
        print(f"  {status} {name}")

    print("=" * 80 + "\n")
    return passed == total


if __name__ == "__main__":
    print("\n💡 Make sure the MCP server is running on http://127.0.0.1:8000/sse")
    print("   Start with: python .\\start_server.py")
    print("\nStarting tests...\n")

    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
