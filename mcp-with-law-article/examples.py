"""
Example client usage patterns for legal article MCP service.

This file demonstrates common usage patterns you can copy and adapt.
"""

import asyncio
from client import LegalMCPClient


async def example_1_list_tools():
    """Example 1: List all available tools."""
    print("\n【Example 1】List Tools")
    print("-" * 60)

    client = LegalMCPClient()
    tools = await client.list_tools()

    print(f"Available {len(tools)} tools:")
    for tool in tools:
        print(f"  • {tool['name']}: {tool['description']}")


async def example_2_get_specific_article():
    """Example 2: Get a specific article by section and law."""
    print("\n【Example 2】Get Specific Article")
    print("-" * 60)

    client = LegalMCPClient()

    # Get article
    article = await client.get_article("第264条", "刑法")

    if article:
        print(f"✓ Found: {article['title']} {article['section_number']}")
        print(f"  Content: {article['content'][:100]}...")
        print(f"  URL: {article['url']}")
    else:
        print("✗ Article not found")


async def example_3_basic_search():
    """Example 3: Basic keyword search."""
    print("\n【Example 3】Basic Keyword Search")
    print("-" * 60)

    client = LegalMCPClient()

    # Simple search without pagination
    results = await client.search_article("盗窃罪")

    print(f"Found {len(results)} results for '盗窃罪':")
    for i, article in enumerate(results[:5], 1):
        print(f"  {i}. {article['title']} {article['section_number']}")


async def example_4_search_with_pagination():
    """Example 4: Search with pagination."""
    print("\n【Example 4】Search with Pagination")
    print("-" * 60)

    client = LegalMCPClient()

    # Get first page (10 items)
    page1 = await client.search_article(
        "犯罪",
        page=1,
        page_size=10,
    )
    print(f"Page 1: {len(page1)} results")

    # Get second page
    page2 = await client.search_article(
        "犯罪",
        page=2,
        page_size=10,
    )
    print(f"Page 2: {len(page2)} results")

    if page1 and page2:
        print(
            f"\nFirst item of Page 1: {page1[0]['title']} "
            f"{page1[0]['section_number']}"
        )
        print(
            f"First item of Page 2: {page2[0]['title']} "
            f"{page2[0]['section_number']}"
        )


async def example_5_search_sorted_by_date():
    """Example 5: Search and sort by update date."""
    print("\n【Example 5】Search Sorted by Date")
    print("-" * 60)

    client = LegalMCPClient()

    results = await client.search_article(
        "刑法",
        page=1,
        page_size=5,
        sort_by="updated_at",
        order="desc",
    )

    print("Latest 5 articles about '刑法':")
    for i, article in enumerate(results, 1):
        print(f"  {i}. {article['title']} - Updated: {article['updated_at']}")


async def example_6_search_sorted_by_relevance():
    """Example 6: Search and sort by relevance."""
    print("\n【Example 6】Search Sorted by Relevance")
    print("-" * 60)

    client = LegalMCPClient()

    results = await client.search_article(
        "诈骗",
        page=1,
        page_size=5,
        sort_by="relevance",
        order="desc",
    )

    print("Top 5 most relevant articles for '诈骗':")
    for i, article in enumerate(results, 1):
        relevance = article.get("relevance", "N/A")
        print(
            f"  {i}. {article['title']} {article['section_number']} "
            f"(relevance: {relevance})"
        )


async def example_7_compare_sort_orders():
    """Example 7: Compare different sort orders."""
    print("\n【Example 7】Compare Sort Orders")
    print("-" * 60)

    client = LegalMCPClient()
    keyword = "犯罪"

    # By relevance descending
    by_relevance_desc = await client.search_article(
        keyword,
        page=1,
        page_size=3,
        sort_by="relevance",
        order="desc",
    )

    # By ID ascending
    by_id_asc = await client.search_article(
        keyword,
        page=1,
        page_size=3,
        sort_by="id",
        order="asc",
    )

    print(f"Top 3 for '{keyword}' sorted by relevance DESC:")
    for article in by_relevance_desc:
        print(f"  • {article['id']}: {article['title']}")

    print(f"\nTop 3 for '{keyword}' sorted by ID ASC:")
    for article in by_id_asc:
        print(f"  • {article['id']}: {article['title']}")


async def example_8_batch_search():
    """Example 8: Batch search multiple keywords."""
    print("\n【Example 8】Batch Search")
    print("-" * 60)

    client = LegalMCPClient()
    keywords = ["盗窃", "杀人", "诈骗", "贪污"]

    results = {}
    for keyword in keywords:
        items = await client.search_article(keyword, page=1, page_size=1)
        results[keyword] = items

    print("Top result for each keyword:")
    for keyword, items in results.items():
        if items:
            article = items[0]
            print(
                f"  {keyword:6s} → {article['title']} {article['section_number']}"
            )
        else:
            print(f"  {keyword:6s} → No results")


async def example_9_large_page_size():
    """Example 9: Fetch large batch in single page."""
    print("\n【Example 9】Large Page Size")
    print("-" * 60)

    client = LegalMCPClient()

    # Fetch 50 results in one page
    results = await client.search_article(
        "法",
        page=1,
        page_size=50,  # Max 100
        sort_by="id",
        order="asc",
    )

    print(f"Fetched {len(results)} results in single page (page_size=50)")
    if results:
        print(f"  First: {results[0]['title']} (ID: {results[0]['id']})")
        print(f"  Last:  {results[-1]['title']} (ID: {results[-1]['id']})")


async def example_10_error_handling():
    """Example 10: Proper error handling."""
    print("\n【Example 10】Error Handling")
    print("-" * 60)

    client = LegalMCPClient()

    try:
        # This search should work
        results = await client.search_article("刑法")
        print(f"✓ Search succeeded: {len(results)} results")

    except ConnectionError as e:
        print(f"✗ Connection error: {e}")
        print("  Make sure the MCP server is running on http://127.0.0.1:8000/sse")

    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Legal Article MCP Client - Usage Examples")
    print("=" * 60)

    examples = [
        example_1_list_tools,
        example_2_get_specific_article,
        example_3_basic_search,
        example_4_search_with_pagination,
        example_5_search_sorted_by_date,
        example_6_search_sorted_by_relevance,
        example_7_compare_sort_orders,
        example_8_batch_search,
        example_9_large_page_size,
        example_10_error_handling,
    ]

    for example in examples:
        try:
            await example()
        except Exception as e:
            print(f"\n⚠ Example failed: {e}")

    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    print("\n💡 Make sure the MCP server is running:")
    print("   python mcp/run_server.py\n")

    asyncio.run(main())
