"""
Legal article database connector.
"""

from __future__ import annotations

import configparser
import os
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2.pool import SimpleConnectionPool
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False


class LegalDatabaseConnector:
    """Database connection manager for legal articles."""

    _pool: Optional[SimpleConnectionPool] = None
    _pool_config: Optional[Tuple[str, int, str, str, str]] = None

    def __init__(self, config_file: str = "config.ini") -> None:
        self.config: Dict[str, Any] = {}
        self.tables: Dict[str, str] = {}
        self.load_config(config_file)

    def load_config(self, config_file: str) -> None:
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")

        config = configparser.ConfigParser()
        config.read(config_file, encoding="utf-8")

        self.config["host"] = config.get("database", "host", fallback="localhost")
        self.config["user"] = config.get("database", "user", fallback="root")
        self.config["password"] = config.get("database", "password", fallback="")
        self.config["database"] = config.get("database", "database", fallback="")
        self.config["port"] = config.getint("database", "port", fallback=5432)

        self.tables["law_article"] = config.get("tables", "law_article", fallback="law_article")

    def connect(self) -> None:
        if not PG_AVAILABLE:
            raise RuntimeError("psycopg2 is not installed")

        config_key = (
            self.config["host"],
            self.config["port"],
            self.config["user"],
            self.config["password"],
            self.config["database"],
        )

        if self._pool and self._pool_config == config_key:
            return

        if self._pool:
            self._pool.closeall()

        self._pool = SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            host=self.config["host"],
            port=self.config["port"],
            user=self.config["user"],
            password=self.config["password"],
            database=self.config["database"],
        )
        self._pool_config = config_key

    def disconnect(self) -> None:
        if not self._pool:
            return
        try:
            self._pool.closeall()
        finally:
            self._pool = None
            self._pool_config = None

    def _get_connection(self):
        if not self._pool:
            self.connect()
        return self._pool.getconn()

    def _release_connection(self, connection) -> None:
        if self._pool and connection:
            self._pool.putconn(connection)

    @staticmethod
    def _to_json_safe(value: Any) -> Any:
        """Convert DB values to JSON-safe primitives for MCP transport."""
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {k: LegalDatabaseConnector._to_json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [LegalDatabaseConnector._to_json_safe(v) for v in value]
        if isinstance(value, tuple):
            return [LegalDatabaseConnector._to_json_safe(v) for v in value]
        return value

    @classmethod
    def _normalize_record(cls, record: Dict[str, Any]) -> Dict[str, Any]:
        return {k: cls._to_json_safe(v) for k, v in record.items()}

    @staticmethod
    def _parse_int_value(
        value: int | str,
        default: int,
        min_value: int,
        max_value: int | None = None,
    ) -> int:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            parsed = default

        if parsed < min_value:
            parsed = min_value
        if max_value is not None and parsed > max_value:
            parsed = max_value
        return parsed

    def get_article(self, number: str, title: str) -> Optional[Dict[str, Any]]:
        query = f"""
            SELECT id, title, section_number, content, url, created_at, updated_at
            FROM {self.tables['law_article']}
            WHERE section_number = %s
              AND title ILIKE %s
            ORDER BY id
            LIMIT 1
        """
        connection = self._get_connection()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, (number, f"%{title}%"))
                row = cursor.fetchone()
                return self._normalize_record(dict(row)) if row else None
        finally:
            self._release_connection(connection)

    def search_articles(
        self,
        text: str,
        page: int | str = 1,
        page_size: int | str = 10,
        sort_by: str = "relevance",
        order: str = "desc",
    ) -> List[Dict[str, Any]]:
        sort_map = {
            "relevance": "relevance",
            "updated_at": "updated_at",
            "created_at": "created_at",
            "id": "id",
        }
        sort_key = sort_map.get(sort_by, "relevance")
        order_dir = "ASC" if order.lower() == "asc" else "DESC"

        page = self._parse_int_value(page, default=1, min_value=1)
        page_size = self._parse_int_value(page_size, default=10, min_value=1, max_value=100)
        offset = (page - 1) * page_size

        relevance_expr = (
            "(CASE WHEN title ILIKE %s THEN 1 ELSE 0 END) * 3 + "
            "(CASE WHEN section_number ILIKE %s THEN 1 ELSE 0 END) * 2 + "
            "(CASE WHEN content ILIKE %s THEN 1 ELSE 0 END)"
        )

        order_by = "relevance DESC, updated_at DESC NULLS LAST, id DESC"
        if sort_key != "relevance":
            order_by = f"{sort_key} {order_dir} NULLS LAST, id DESC"

        query = f"""
            SELECT id, title, section_number, content, url, created_at, updated_at,
                   {relevance_expr} AS relevance
            FROM {self.tables['law_article']}
            WHERE title ILIKE %s
               OR content ILIKE %s
               OR section_number ILIKE %s
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
        """
        like_text = f"%{text}%"
        params = (
            like_text,
            like_text,
            like_text,
            like_text,
            like_text,
            like_text,
            page_size,
            offset,
        )
        connection = self._get_connection()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._normalize_record(dict(row)) for row in rows]
        finally:
            self._release_connection(connection)
