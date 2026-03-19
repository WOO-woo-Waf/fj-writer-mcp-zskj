"""
Legal article database connector.
"""

from __future__ import annotations

import configparser
import os
import re
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
        number_candidates = self._build_article_number_candidates(number)
        query = f"""
            SELECT id, title, section_number, content, url, created_at, updated_at
            FROM {self.tables['law_article']}
            WHERE title ILIKE %s
              AND (section_number ILIKE %s OR content ILIKE %s)
            ORDER BY id
            LIMIT 1
        """
        connection = self._get_connection()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                for candidate in number_candidates:
                    like_candidate = f"%{candidate}%"
                    cursor.execute(query, (f"%{title}%", like_candidate, like_candidate))
                    row = cursor.fetchone()
                    if row:
                        return self._normalize_record(dict(row))
                return None
        finally:
            self._release_connection(connection)

    @staticmethod
    def _arabic_to_chinese_number(value: int) -> str:
        """Convert 0-9999 integer to Chinese numerals used in article numbers."""
        if value == 0:
            return "零"

        digits = "零一二三四五六七八九"
        units = [(1000, "千"), (100, "百"), (10, "十")]

        parts: List[str] = []
        remainder = value
        need_zero = False

        for unit_value, unit_name in units:
            digit = remainder // unit_value
            remainder %= unit_value
            if digit > 0:
                if need_zero:
                    parts.append("零")
                    need_zero = False
                if not (unit_value == 10 and digit == 1 and not parts):
                    parts.append(digits[digit])
                parts.append(unit_name)
            elif parts and remainder > 0:
                need_zero = True

        if remainder > 0:
            if need_zero:
                parts.append("零")
            parts.append(digits[remainder])

        return "".join(parts)

    def _build_article_number_candidates(self, number: str) -> List[str]:
        """Build robust article number variants (Arabic and Chinese forms)."""
        text = (number or "").strip()
        if not text:
            return []

        candidates: List[str] = [text]
        compact = re.sub(r"\s+", "", text)
        if compact not in candidates:
            candidates.append(compact)

        match = re.search(r"(\d+)", compact)
        if match:
            arabic = int(match.group(1))
            zh_num = self._arabic_to_chinese_number(arabic)
            zh_article = f"第{zh_num}条"
            simple_article = f"第{arabic}条"
            bare_num = str(arabic)

            for item in [simple_article, zh_article, bare_num, zh_num]:
                if item and item not in candidates:
                    candidates.append(item)

        return candidates

    @staticmethod
    def _tokenize_search_text(text: str) -> List[str]:
        """Split multi-keyword query into meaningful tokens."""
        raw = (text or "").strip()
        if not raw:
            return []

        chunks = [piece.strip() for piece in re.split(r"[\s,，;；、|/]+", raw) if piece.strip()]
        deduped: List[str] = []
        seen = set()
        for chunk in chunks:
            if len(chunk) <= 1:
                continue
            if chunk in seen:
                continue
            seen.add(chunk)
            deduped.append(chunk)
        return deduped or [raw]

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

        tokens = self._tokenize_search_text(text)
        phrase_like = f"%{text}%"

        relevance_parts = [
            "(CASE WHEN title ILIKE %s THEN 1 ELSE 0 END) * 4",
            "(CASE WHEN section_number ILIKE %s THEN 1 ELSE 0 END) * 3",
            "(CASE WHEN content ILIKE %s THEN 1 ELSE 0 END) * 2",
        ]
        relevance_params: List[Any] = [phrase_like, phrase_like, phrase_like]

        where_clauses: List[str] = []
        where_params: List[Any] = []

        # 多关键词语义：每个关键词至少命中一个字段（AND across terms）。
        for token in tokens:
            token_like = f"%{token}%"
            where_clauses.append("(title ILIKE %s OR content ILIKE %s OR section_number ILIKE %s)")
            where_params.extend([token_like, token_like, token_like])
            relevance_parts.append("(CASE WHEN title ILIKE %s THEN 1 ELSE 0 END) * 3")
            relevance_parts.append("(CASE WHEN section_number ILIKE %s THEN 1 ELSE 0 END) * 2")
            relevance_parts.append("(CASE WHEN content ILIKE %s THEN 1 ELSE 0 END)")
            relevance_params.extend([token_like, token_like, token_like])

        relevance_expr = " + ".join(relevance_parts)
        where_expr = " AND ".join(where_clauses) if where_clauses else "(title ILIKE %s OR content ILIKE %s OR section_number ILIKE %s)"
        if not where_clauses:
            where_params.extend([phrase_like, phrase_like, phrase_like])

        order_by = "relevance DESC, updated_at DESC NULLS LAST, id DESC"
        if sort_key != "relevance":
            order_by = f"{sort_key} {order_dir} NULLS LAST, id DESC"

        query = f"""
            SELECT id, title, section_number, content, url, created_at, updated_at,
                   {relevance_expr} AS relevance
            FROM {self.tables['law_article']}
            WHERE {where_expr}
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
        """
        params = tuple(relevance_params + where_params + [page_size, offset])
        connection = self._get_connection()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [self._normalize_record(dict(row)) for row in rows]
        finally:
            self._release_connection(connection)
