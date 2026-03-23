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
    _pool_config: Optional[Tuple[Any, ...]] = None

    def __init__(self, config_file: str = "config.ini") -> None:
        self.config: Dict[str, Any] = {}
        self.tables: Dict[str, str] = {}
        self.search_config: Dict[str, Any] = {}
        self.score_config: Dict[str, Any] = {}
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
        self.config["pool_minconn"] = config.getint("database", "pool_minconn", fallback=1)
        self.config["pool_maxconn"] = config.getint("database", "pool_maxconn", fallback=5)
        self.config["statement_timeout_ms"] = config.getint("database", "statement_timeout_ms", fallback=0)

        if self.config["pool_minconn"] < 1:
            self.config["pool_minconn"] = 1
        if self.config["pool_maxconn"] < self.config["pool_minconn"]:
            self.config["pool_maxconn"] = self.config["pool_minconn"]

        self.tables["law_article"] = config.get("tables", "law_article", fallback="law_article")

        whitelist_raw = config.get("search", "single_char_whitelist", fallback="税,罪")
        self.search_config = {
            "token_limit": config.getint("search", "token_limit", fallback=10),
            "token_min_length": config.getint("search", "token_min_length", fallback=2),
            "single_char_whitelist": {
                item.strip()
                for item in whitelist_raw.replace("，", ",").split(",")
                if item.strip()
            },
            "phrase_title_weight": config.getfloat("search", "phrase_title_weight", fallback=4.0),
            "phrase_section_weight": config.getfloat("search", "phrase_section_weight", fallback=3.0),
            "phrase_content_weight": config.getfloat("search", "phrase_content_weight", fallback=2.0),
            "token_title_weight": config.getfloat("search", "token_title_weight", fallback=3.0),
            "token_section_weight": config.getfloat("search", "token_section_weight", fallback=2.0),
            "token_content_weight": config.getfloat("search", "token_content_weight", fallback=1.0),
        }
        if self.search_config["token_limit"] < 1:
            self.search_config["token_limit"] = 1
        if self.search_config["token_min_length"] < 1:
            self.search_config["token_min_length"] = 1

        self.score_config = {
            "get_article_section_exact_weight": config.getfloat(
                "scoring", "get_article_section_exact_weight", fallback=300.0
            ),
            "get_article_section_like_weight": config.getfloat(
                "scoring", "get_article_section_like_weight", fallback=220.0
            ),
            "get_article_content_weight": config.getfloat(
                "scoring", "get_article_content_weight", fallback=140.0
            ),
            "get_article_title_exact_weight": config.getfloat(
                "scoring", "get_article_title_exact_weight", fallback=80.0
            ),
            "get_article_title_like_weight": config.getfloat(
                "scoring", "get_article_title_like_weight", fallback=40.0
            ),
        }

    def connect(self) -> None:
        if not PG_AVAILABLE:
            raise RuntimeError("psycopg2 is not installed")

        config_key = (
            self.config["host"],
            self.config["port"],
            self.config["user"],
            self.config["password"],
            self.config["database"],
            self.config["pool_minconn"],
            self.config["pool_maxconn"],
            self.config["statement_timeout_ms"],
        )

        if self._pool and self._pool_config == config_key:
            return

        if self._pool:
            self._pool.closeall()

        pool_kwargs = {
            "minconn": self.config["pool_minconn"],
            "maxconn": self.config["pool_maxconn"],
            "host": self.config["host"],
            "port": self.config["port"],
            "user": self.config["user"],
            "password": self.config["password"],
            "database": self.config["database"],
        }
        if self.config["statement_timeout_ms"] > 0:
            pool_kwargs["options"] = f"-c statement_timeout={self.config['statement_timeout_ms']}"

        self._pool = SimpleConnectionPool(**pool_kwargs)
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
        if not number_candidates:
            return None

        section_exact: List[str] = []
        section_like: List[str] = []
        content_like: List[str] = []
        exact_seen = set()
        like_seen = set()
        content_seen = set()

        for candidate in number_candidates:
            compact_candidate = re.sub(r"\s+", "", str(candidate or "")).strip()
            if not compact_candidate:
                continue

            if compact_candidate not in exact_seen:
                exact_seen.add(compact_candidate)
                section_exact.append(compact_candidate)

            like_value = f"%{compact_candidate}%"
            if like_value not in like_seen:
                like_seen.add(like_value)
                section_like.append(like_value)

            if re.fullmatch(r"\d+", compact_candidate):
                content_value = f"%第{compact_candidate}条%"
            elif re.fullmatch(r"[零〇一二两三四五六七八九十百千]+", compact_candidate):
                content_value = f"%第{compact_candidate}条%"
            elif compact_candidate.startswith("第") and compact_candidate.endswith("条"):
                content_value = f"%{compact_candidate}%"
            else:
                content_value = f"%{compact_candidate}%"

            if content_value not in content_seen:
                content_seen.add(content_value)
                content_like.append(content_value)

        if not section_exact and not section_like and not content_like:
            return None

        query = f"""
            SELECT id, title, section_number, content, url, created_at, updated_at
            FROM {self.tables['law_article']}
            WHERE title ILIKE %s
              AND (
                    section_number = ANY(%s)
                 OR section_number ILIKE ANY(%s)
                 OR content ILIKE ANY(%s)
              )
            ORDER BY
                (
                    CASE
                        WHEN section_number = ANY(%s) THEN %s
                        WHEN section_number ILIKE ANY(%s) THEN %s
                        WHEN content ILIKE ANY(%s) THEN %s
                        ELSE 0
                    END
                    +
                    CASE
                        WHEN title = %s THEN %s
                        WHEN title ILIKE %s THEN %s
                        ELSE 0
                    END
                ) DESC,
                updated_at DESC NULLS LAST,
                id DESC
            LIMIT 1
        """
        connection = self._get_connection()
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    query,
                    (
                        f"%{title}%",
                        section_exact,
                        section_like,
                        content_like,
                        section_exact,
                        self.score_config["get_article_section_exact_weight"],
                        section_like,
                        self.score_config["get_article_section_like_weight"],
                        content_like,
                        self.score_config["get_article_content_weight"],
                        title,
                        self.score_config["get_article_title_exact_weight"],
                        f"%{title}%",
                        self.score_config["get_article_title_like_weight"],
                    ),
                )
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

    @staticmethod
    def _chinese_to_arabic_number(text: str) -> Optional[int]:
        """Convert Chinese numerals (0-9999) to Arabic integer."""
        raw = (text or "").strip()
        if not raw:
            return None

        normalized = raw.replace("兩", "二").replace("两", "二").replace("〇", "零")
        if normalized.isdigit():
            return int(normalized)

        digits = {
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }
        units = {"十": 10, "百": 100, "千": 1000}

        if any(char not in set(digits) | set(units) for char in normalized):
            return None

        total = 0
        pending_digit = 0
        for char in normalized:
            if char in digits:
                pending_digit = digits[char]
                continue

            unit_value = units[char]
            if pending_digit == 0:
                pending_digit = 1
            total += pending_digit * unit_value
            pending_digit = 0

        total += pending_digit
        return total if total >= 0 else None

    def _build_article_number_candidates(self, number: str) -> List[str]:
        """Build robust article number variants (Arabic and Chinese forms)."""
        text = (number or "").strip()
        if not text:
            return []

        candidates: List[str] = [text]
        compact = re.sub(r"\s+", "", text)
        if compact not in candidates:
            candidates.append(compact)

        normalized_number_text = re.sub(r"[第条]", "", compact)

        arabic_value: Optional[int] = None
        match = re.search(r"(\d+)", normalized_number_text)
        if match:
            arabic_value = int(match.group(1))
        else:
            maybe_zh = re.sub(r"[^零〇一二两三四五六七八九十百千]", "", normalized_number_text)
            arabic_value = self._chinese_to_arabic_number(maybe_zh)

        if arabic_value is not None:
            zh_num = self._arabic_to_chinese_number(arabic_value)
            simple_article = f"第{arabic_value}条"
            zh_article = f"第{zh_num}条"
            bare_num = str(arabic_value)

            for item in [bare_num, simple_article, zh_num, zh_article]:
                if item and item not in candidates:
                    candidates.append(item)

        return candidates

    def _tokenize_search_text(self, text: str) -> List[str]:
        """Split multi-keyword query into meaningful tokens."""
        raw = (text or "").strip()
        if not raw:
            return []

        chunks = [piece.strip() for piece in re.split(r"[\s,，;；、|/]+", raw) if piece.strip()]
        deduped: List[str] = []
        seen = set()
        single_char_whitelist = set(self.search_config.get("single_char_whitelist", {"税", "罪"}))
        token_min_length = int(self.search_config.get("token_min_length", 2))
        token_limit = int(self.search_config.get("token_limit", 10))
        for chunk in chunks:
            if len(chunk) < token_min_length and chunk not in single_char_whitelist:
                continue
            if chunk in seen:
                continue
            seen.add(chunk)
            deduped.append(chunk)
            if len(deduped) >= token_limit:
                break
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
        phrase_title_weight = self.search_config["phrase_title_weight"]
        phrase_section_weight = self.search_config["phrase_section_weight"]
        phrase_content_weight = self.search_config["phrase_content_weight"]
        token_title_weight = self.search_config["token_title_weight"]
        token_section_weight = self.search_config["token_section_weight"]
        token_content_weight = self.search_config["token_content_weight"]

        relevance_parts = [
            "(CASE WHEN title ILIKE %s THEN 1 ELSE 0 END) * %s",
            "(CASE WHEN section_number ILIKE %s THEN 1 ELSE 0 END) * %s",
            "(CASE WHEN content ILIKE %s THEN 1 ELSE 0 END) * %s",
        ]
        relevance_params: List[Any] = [
            phrase_like,
            phrase_title_weight,
            phrase_like,
            phrase_section_weight,
            phrase_like,
            phrase_content_weight,
        ]

        where_clauses: List[str] = []
        where_params: List[Any] = []

        # 多关键词语义：任一关键词命中任一字段（OR across terms）。
        for token in tokens:
            token_like = f"%{token}%"
            where_clauses.append("(title ILIKE %s OR content ILIKE %s OR section_number ILIKE %s)")
            where_params.extend([token_like, token_like, token_like])
            relevance_parts.append("(CASE WHEN title ILIKE %s THEN 1 ELSE 0 END) * %s")
            relevance_parts.append("(CASE WHEN section_number ILIKE %s THEN 1 ELSE 0 END) * %s")
            relevance_parts.append("(CASE WHEN content ILIKE %s THEN 1 ELSE 0 END) * %s")
            relevance_params.extend(
                [
                    token_like,
                    token_title_weight,
                    token_like,
                    token_section_weight,
                    token_like,
                    token_content_weight,
                ]
            )

        relevance_expr = " + ".join(relevance_parts)
        where_expr = " OR ".join(where_clauses) if where_clauses else "(title ILIKE %s OR content ILIKE %s OR section_number ILIKE %s)"
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
