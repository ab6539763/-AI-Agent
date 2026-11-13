"""Day 47 核心实现：Text-to-SQL 数据分析智能体与只读 SQL 安全护栏 (v0.4.0-day47)."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class SQLSecurityError(ValueError):
    """当 SQL 语句违反只读安全策略或存在注入风险时抛出。"""


_FORBIDDEN_KEYWORDS = (
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "ALTER",
    "PRAGMA",
    "ATTACH",
    "DETACH",
    "CREATE",
    "REPLACE",
    "TRUNCATE",
    "VACUUM",
    "REINDEX",
)

_FORBIDDEN_PATTERN = re.compile(
    r"\b(" + "|".join(_FORBIDDEN_KEYWORDS) + r")\b",
    flags=re.IGNORECASE,
)


def validate_readonly_sql(sql: str) -> str:
    """严格校验 SQL 仅允许单条只读 SELECT 查询，拦截写操作与注入载荷。

    规则：
    1. 禁止空字符串。
    2. 禁止分号 `;`（阻断多语句堆叠注入，如 `SELECT 1; DROP TABLE orders`）。
    3. 禁止 SQL 注释符 `--` 与 `/*`（防止注释绕过）。
    4. 去除首尾空白后必须以 `SELECT` 开头（忽略大小写）。
    5. 禁止包含 `DROP/DELETE/UPDATE/INSERT/ALTER/PRAGMA/ATTACH/DETACH/CREATE/REPLACE/TRUNCATE/VACUUM/REINDEX` 等危险关键字。
    """
    if not isinstance(sql, str):
        raise SQLSecurityError("SQL 必须为字符串类型")

    cleaned = sql.strip()
    if not cleaned:
        raise SQLSecurityError("SQL 语句不能为空")

    if ";" in cleaned:
        raise SQLSecurityError("检测到非法分号 ';'，禁止多语句执行或堆叠注入")

    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        raise SQLSecurityError("检测到 SQL 注释符（-- 或 /* */），出于安全策略已拦截")

    if not re.match(r"^SELECT\b", cleaned, flags=re.IGNORECASE):
        raise SQLSecurityError("仅允许以 SELECT 开头的只读查询语句")

    match = _FORBIDDEN_PATTERN.search(cleaned)
    if match:
        raise SQLSecurityError(f"检测到禁止的写操作或系统指令关键字: {match.group(1).upper()}")

    return cleaned


class SalesDatabase:
    """企业销售分析 SQLite 数据库（含 regions、products、orders 三张核心业务表）。"""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")

    def initialize_and_seed(self) -> None:
        """创建表结构并写入示例销售业务数据（幂等操作）。"""
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS regions (
                region_id INTEGER PRIMARY KEY,
                region_name TEXT NOT NULL UNIQUE,
                manager TEXT NOT NULL,
                target_revenue REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                product_id INTEGER PRIMARY KEY,
                product_name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                unit_price REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                product_id INTEGER NOT NULL,
                region_id INTEGER NOT NULL,
                customer_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                total_amount REAL NOT NULL,
                order_date TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(product_id),
                FOREIGN KEY (region_id) REFERENCES regions(region_id)
            );
            """
        )

        existing = cur.execute("SELECT COUNT(*) FROM regions").fetchone()[0]
        if existing == 0:
            regions = [
                (1, "华东", "陈敏", 200000.0),
                (2, "华南", "林峰", 160000.0),
                (3, "华北", "张伟", 150000.0),
                (4, "西南", "赵琳", 100000.0),
            ]
            cur.executemany(
                "INSERT INTO regions (region_id, region_name, manager, target_revenue) VALUES (?, ?, ?, ?)",
                regions,
            )

            products = [
                (1, "智枢企业版 SaaS", "SaaS订阅", 12000.0),
                (2, "星辰知识库引擎", "SaaS订阅", 8500.0),
                (3, "边缘推理一体机", "智能硬件", 28000.0),
                (4, "智能客服网关", "企业服务", 6000.0),
                (5, "私有化部署实施包", "企业服务", 15000.0),
            ]
            cur.executemany(
                "INSERT INTO products (product_id, product_name, category, unit_price) VALUES (?, ?, ?, ?)",
                products,
            )

            orders = [
                (1001, 1, 1, "沪上科技", 5, 60000.0, "2026-01-10", "completed"),
                (1002, 3, 1, "金陵制造", 3, 84000.0, "2026-01-18", "completed"),
                (1003, 2, 2, "鹏城金融", 6, 51000.0, "2026-01-22", "completed"),
                (1004, 4, 3, "京华物流", 8, 48000.0, "2026-02-05", "completed"),
                (1005, 5, 1, "苏杭电商", 4, 60000.0, "2026-02-14", "completed"),
                (1006, 3, 2, "羊城医药", 2, 56000.0, "2026-02-20", "completed"),
                (1007, 1, 3, "津门重工", 4, 48000.0, "2026-03-03", "completed"),
                (1008, 2, 4, "锦官城文旅", 5, 42500.0, "2026-03-11", "completed"),
                (1009, 5, 2, "湾区生物", 3, 45000.0, "2026-03-19", "completed"),
                (1010, 4, 4, "山城零售", 6, 36000.0, "2026-03-25", "completed"),
                (1011, 1, 1, "甬城外贸", 3, 36000.0, "2026-04-02", "completed"),
                (1012, 3, 3, "燕赵能源", 2, 56000.0, "2026-04-09", "pending"),
            ]
            cur.executemany(
                """
                INSERT INTO orders (
                    order_id, product_id, region_id, customer_name,
                    quantity, total_amount, order_date, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                orders,
            )
            self._conn.commit()

    def introspect_schema(self) -> str:
        """自省数据库表结构与外键关系，生成供 LLM 使用的 Schema 上下文描述。"""
        cur = self._conn.cursor()
        tables = cur.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        lines: list[str] = ["数据库表结构（SQLite）："]
        for row in tables:
            table_name = row["name"]
            ddl = " ".join(str(row["sql"]).split())
            count = cur.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            lines.append(f"- 表 `{table_name}`（{count} 行）: {ddl}")
        return "\n".join(lines)

    def get_table_names(self) -> list[str]:
        """返回数据库中所有用户表名。"""
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [str(r["name"]) for r in rows]

    def execute_readonly(self, sql: str) -> list[dict[str, Any]]:
        """经过只读安全校验后执行 SQL 并返回字典列表。"""
        safe_sql = validate_readonly_sql(sql)
        cur = self._conn.execute(safe_sql)
        return [dict(row) for row in cur.fetchall()]

    def close(self) -> None:
        """关闭数据库连接。"""
        self._conn.close()

    def __enter__(self) -> SalesDatabase:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()


@dataclass
class SQLAnalysisResult:
    """Text-to-SQL 智能体单次分析结果。"""

    question: str
    schema_context: str
    generated_sql: str
    status: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    insight: str = ""
    error: str | None = None


class TextToSQLAgent:
    """Text-to-SQL 数据分析智能体：Schema 自省 -> NL 转 SQL -> 安全校验 -> 执行 -> 中文商业洞察。"""

    def __init__(
        self,
        db: SalesDatabase,
        llm_fn: Callable[[str, str], str] | None = None,
    ) -> None:
        self.db = db
        self.llm_fn = llm_fn

    def generate_sql(self, question: str, schema_context: str) -> str:
        """将自然语言问题转换为 SQL（支持注入外部 LLM，默认使用内置规则引擎）。"""
        if self.llm_fn is not None:
            return self.llm_fn(question, schema_context)

        q = question.strip()
        if any(k in q for k in ("大区", "区域", "地区")) and any(k in q for k in ("目标", "完成率", "达成")):
            return (
                "SELECT r.region_name AS 大区, r.manager AS 负责人, "
                "ROUND(SUM(o.total_amount), 2) AS 实际销售额, "
                "r.target_revenue AS 目标销售额, "
                "ROUND(SUM(o.total_amount) * 100.0 / r.target_revenue, 1) AS 达成率百分比 "
                "FROM orders o "
                "JOIN regions r ON o.region_id = r.region_id "
                "WHERE o.status = 'completed' "
                "GROUP BY r.region_id, r.region_name, r.manager, r.target_revenue "
                "ORDER BY 实际销售额 DESC"
            )

        if any(k in q for k in ("大区", "区域", "地区")):
            return (
                "SELECT r.region_name AS 大区, COUNT(o.order_id) AS 订单数, "
                "SUM(o.quantity) AS 总销量, ROUND(SUM(o.total_amount), 2) AS 销售额 "
                "FROM orders o "
                "JOIN regions r ON o.region_id = r.region_id "
                "GROUP BY r.region_id, r.region_name "
                "ORDER BY 销售额 DESC"
            )

        if any(k in q for k in ("类别", "品类", "分类")):
            return (
                "SELECT p.category AS 产品类别, COUNT(o.order_id) AS 订单数, "
                "SUM(o.quantity) AS 总销量, ROUND(SUM(o.total_amount), 2) AS 销售额 "
                "FROM orders o "
                "JOIN products p ON o.product_id = p.product_id "
                "GROUP BY p.category "
                "ORDER BY 销售额 DESC"
            )

        if any(k in q for k in ("产品", "商品", "畅销", "Top", "TOP", "排行", "排名")):
            return (
                "SELECT p.product_name AS 产品名称, p.category AS 类别, "
                "SUM(o.quantity) AS 销量, ROUND(SUM(o.total_amount), 2) AS 销售额 "
                "FROM orders o "
                "JOIN products p ON o.product_id = p.product_id "
                "GROUP BY p.product_id, p.product_name, p.category "
                "ORDER BY 销售额 DESC "
                "LIMIT 5"
            )

        if any(k in q for k in ("客户", "大单", "最高")):
            return (
                "SELECT o.order_id AS 订单号, o.customer_name AS 客户名称, "
                "r.region_name AS 大区, p.product_name AS 产品名称, "
                "o.total_amount AS 订单金额, o.order_date AS 下单日期 "
                "FROM orders o "
                "JOIN regions r ON o.region_id = r.region_id "
                "JOIN products p ON o.product_id = p.product_id "
                "ORDER BY o.total_amount DESC "
                "LIMIT 5"
            )

        return (
            "SELECT COUNT(order_id) AS 订单总数, SUM(quantity) AS 总销量, "
            "ROUND(SUM(total_amount), 2) AS 总销售额 "
            "FROM orders"
        )

    def summarize_insight(self, question: str, rows: list[dict[str, Any]]) -> str:
        """根据查询结果生成简洁的中文商业洞察摘要。"""
        if not rows:
            return f"针对问题“{question}”，数据库未检索到符合条件的记录。"

        first = rows[0]
        if "大区" in first and "达成率百分比" in first:
            top = max(rows, key=lambda r: float(r["达成率百分比"]))
            bottom = min(rows, key=lambda r: float(r["达成率百分比"]))
            return (
                f"商业洞察：共统计 {len(rows)} 个大区已完成订单。"
                f"表现最佳为【{top['大区']}】（负责人：{top['负责人']}），实际销售额 {top['实际销售额']:,.0f} 元，"
                f"目标达成率 {top['达成率百分比']}%；"
                f"相对滞后为【{bottom['大区']}】，达成率 {bottom['达成率百分比']}%，建议重点跟进大客户转化。"
            )

        if "大区" in first and "销售额" in first:
            total = sum(float(r["销售额"]) for r in rows)
            top = rows[0]
            share = (float(top["销售额"]) / total * 100.0) if total > 0 else 0.0
            return (
                f"商业洞察：全渠道合计销售额 {total:,.0f} 元。"
                f"【{top['大区']}】大区贡献最高，销售额 {top['销售额']:,.0f} 元（占比 {share:.1f}%），"
                f"共 {top['订单数']} 笔订单。"
            )

        if "产品名称" in first and "销售额" in first:
            top = rows[0]
            return (
                f"商业洞察：畅销榜首产品为【{top['产品名称']}】（{top['类别']}），"
                f"累计销售 {top['销量']} 件/套，贡献营收 {top['销售额']:,.0f} 元。"
            )

        if "产品类别" in first and "销售额" in first:
            top = rows[0]
            return (
                f"商业洞察：主力营收品类为【{top['产品类别']}】，"
                f"共产生 {top['订单数']} 笔订单，总销售额达 {top['销售额']:,.0f} 元。"
            )

        if "客户名称" in first and "订单金额" in first:
            top = rows[0]
            return (
                f"商业洞察：Top 1 标杆大单来自【{top['大区']}】大区客户“{top['客户名称']}”，"
                f"采购【{top['产品名称']}】，单笔金额 {top['订单金额']:,.0f} 元。"
            )

        summary_kv = "，".join(f"{k}={v}" for k, v in first.items())
        return f"商业洞察：共返回 {len(rows)} 条记录，核心指标：{summary_kv}。"

    def ask(self, question: str) -> SQLAnalysisResult:
        """执行完整 Text-to-SQL 闭环分析流程。"""
        schema_context = self.db.introspect_schema()
        generated_sql = self.generate_sql(question, schema_context)

        try:
            rows = self.db.execute_readonly(generated_sql)
        except SQLSecurityError as exc:
            return SQLAnalysisResult(
                question=question,
                schema_context=schema_context,
                generated_sql=generated_sql,
                status="blocked",
                rows=[],
                insight=f"安全护栏已拦截本次查询：{exc}",
                error=str(exc),
            )
        except sqlite3.Error as exc:
            return SQLAnalysisResult(
                question=question,
                schema_context=schema_context,
                generated_sql=generated_sql,
                status="error",
                rows=[],
                insight=f"SQL 执行失败：{exc}",
                error=str(exc),
            )

        insight = self.summarize_insight(question, rows)
        return SQLAnalysisResult(
            question=question,
            schema_context=schema_context,
            generated_sql=generated_sql,
            status="success",
            rows=rows,
            insight=insight,
        )
