#!/usr/bin/env python
"""
Quick reference and interactive guide for MCP service.

Run this to see a menu-driven interface for exploring the service.
"""

import asyncio
import sys

from client import LegalMCPClient


class MCPGuide:
    def __init__(self):
        self.client = LegalMCPClient()

    async def menu_main(self):
        """Main menu."""
        while True:
            print("\n" + "=" * 70)
            print("Legal Article MCP Service - Interactive Guide")
            print("=" * 70)
            print("""
1. List available tools
2. Get specific article (by section number & law title)
3. Search articles (by keyword)
4. Advanced search (with pagination & sorting)
5. Run example batch searches
6. Exit
            """)

            choice = input("Choose option (1-6): ").strip()

            if choice == "1":
                await self.show_tools()
            elif choice == "2":
                await self.menu_get_article()
            elif choice == "3":
                await self.menu_search_basic()
            elif choice == "4":
                await self.menu_search_advanced()
            elif choice == "5":
                await self.menu_batch()
            elif choice == "6":
                print("\nGoodbye!\n")
                break
            else:
                print("\n✗ Invalid choice")

    async def show_tools(self):
        """Show available tools."""
        print("\n" + "-" * 70)
        print("Available Tools")
        print("-" * 70)

        try:
            tools = await self.client.list_tools()
            for i, tool in enumerate(tools, 1):
                print(f"\n{i}. {tool['name']}")
                print(f"   {tool['description']}")
        except Exception as e:
            print(f"✗ Error: {e}")

    async def menu_get_article(self):
        """Menu for getting specific article."""
        print("\n" + "-" * 70)
        print("Get Specific Article")
        print("-" * 70)

        number = input("Section number (e.g., '第264条'): ").strip()
        if not number:
            print("✗ Section number is required")
            return

        title = input("Law title (e.g., '刑法'): ").strip()
        if not title:
            print("✗ Law title is required")
            return

        try:
            article = await self.client.get_article(number, title)
            if article:
                self._print_article(article)
            else:
                print(f"\n⚠ No article found for {title} {number}")
        except Exception as e:
            print(f"\n✗ Error: {e}")

    async def menu_search_basic(self):
        """Menu for basic search."""
        print("\n" + "-" * 70)
        print("Search Articles")
        print("-" * 70)

        text = input("Search keyword (e.g., '盗窃罪'): ").strip()
        if not text:
            print("✗ Keyword is required")
            return

        try:
            results = await self.client.search_article(text, page=1, page_size=10)
            self._print_search_results(results, text)
        except Exception as e:
            print(f"\n✗ Error: {e}")

    async def menu_search_advanced(self):
        """Menu for advanced search."""
        print("\n" + "-" * 70)
        print("Advanced Search")
        print("-" * 70)

        text = input("Search keyword: ").strip()
        if not text:
            print("✗ Keyword is required")
            return

        try:
            page = int(input("Page (default 1): ") or "1")
        except ValueError:
            page = 1

        try:
            page_size = int(input("Page size 1-100 (default 10): ") or "10")
            page_size = max(1, min(page_size, 100))
        except ValueError:
            page_size = 10

        print("\nSort by: (1) relevance  (2) updated_at  (3) created_at  (4) id")
        sort_choice = input("Choose sort option (default 1): ").strip() or "1"
        sort_map = {
            "1": "relevance",
            "2": "updated_at",
            "3": "created_at",
            "4": "id",
        }
        sort_by = sort_map.get(sort_choice, "relevance")

        print("Order: (1) descending  (2) ascending")
        order_choice = input("Choose order (default 1): ").strip() or "1"
        order = "desc" if order_choice == "1" else "asc"

        try:
            results = await self.client.search_article(
                text,
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                order=order,
            )
            self._print_search_results(results, text)
            print(f"\nParameters: page={page}, page_size={page_size}, sort_by={sort_by}, order={order}")
        except Exception as e:
            print(f"\n✗ Error: {e}")

    async def menu_batch(self):
        """Menu for batch search."""
        print("\n" + "-" * 70)
        print("Batch Search Examples")
        print("-" * 70)

        keywords = ["盗窃罪", "诈骗罪", "杀人罪", "贿赂罪", "贪污罪"]

        print(f"\nSearching {len(keywords)} keywords...\n")

        results = {}
        for keyword in keywords:
            try:
                items = await self.client.search_article(keyword, page=1, page_size=1)
                results[keyword] = items
                status = "✓" if items else "✗"
                print(f"  {status} {keyword:8s} → Found {len(items)} result(s)")
            except Exception as e:
                print(f"  ✗ {keyword:8s} → Error: {e}")

        print("\n" + "-" * 70)
        print("Results Summary:")
        print("-" * 70)
        for keyword, items in results.items():
            if items:
                article = items[0]
                print(f"\n{keyword}:")
                print(f"  Title: {article['title']}")
                print(f"  Section: {article['section_number']}")
                print(f"  Preview: {article['content'][:80]}...")
            else:
                print(f"\n{keyword}: No results")

    def _print_article(self, article):
        """Print a single article nicely."""
        print("\n" + "-" * 70)
        print(f"Title: {article.get('title', 'N/A')}")
        print(f"Section: {article.get('section_number', 'N/A')}")
        print("-" * 70)
        print(f"Content:\n{article.get('content', 'N/A')}")
        print("-" * 70)
        print(f"URL: {article.get('url', 'N/A')}")
        print(f"Created: {article.get('created_at', 'N/A')}")
        print(f"Updated: {article.get('updated_at', 'N/A')}")

    def _print_search_results(self, results, keyword):
        """Print search results nicely."""
        print(
            f"\n✓ Found {len(results)} results for '{keyword}':\n"
        )

        if not results:
            print("  (No results)")
            return

        for i, article in enumerate(results[:10], 1):
            rel = article.get("relevance", "")
            rel_str = f" [relevance: {rel}]" if rel else ""
            print(f"  {i}. {article['title']} {article['section_number']}{rel_str}")
            print(f"     {article['content'][:70]}...")

        if len(results) > 10:
            print(f"\n  ... and {len(results) - 10} more results")


async def main():
    """Run interactive guide."""
    try:
        guide = MCPGuide()
        await guide.menu_main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("\n💡 Before running, make sure the MCP server is running:")
    print("   python mcp/run_server.py\n")

    asyncio.run(main())
