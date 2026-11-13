"""Day 47 平台启动入口：Text-to-SQL 数据分析智能体演示 (v0.4.0-day47)."""

import json
import sys
from pathlib import Path

DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent import (
    SQLSecurityError,
    SalesDatabase,
    TextToSQLAgent,
    validate_readonly_sql,
)


def main() -> None:
    """运行 Day 47 Text-to-SQL 端到端演示。"""
    print("=" * 72)
    print("📊 智枢企业级智能体平台 v0.4.0-day47 · Text-to-SQL 数据分析智能体")
    print("=" * 72)

    with SalesDatabase(":memory:") as db:
        db.initialize_and_seed()
        print("\n[1] 数据库 Schema 自省结果:")
        print(db.introspect_schema())

        agent = TextToSQLAgent(db=db)
        questions = [
            "各大区已完成订单的实际销售额与目标达成率是多少？",
            "销售额排名前 5 的产品有哪些？",
            "按产品类别统计销售额和订单数",
        ]

        print("\n[2] 自然语言问数演示:")
        for idx, q in enumerate(questions, start=1):
            res = agent.ask(q)
            print(f"\n--- 问题 {idx}: {q}")
            print(f"生成 SQL: {res.generated_sql}")
            print(f"查询结果 ({len(res.rows)} 行): {json.dumps(res.rows[:3], ensure_ascii=False)}")
            print(f"商业洞察: {res.insight}")

        print("\n[3] 只读 SQL 安全护栏拦截演示:")
        malicious_queries = [
            "DROP TABLE orders",
            "SELECT * FROM orders; DELETE FROM orders",
            "PRAGMA table_info(orders)",
        ]
        for sql in malicious_queries:
            try:
                validate_readonly_sql(sql)
            except SQLSecurityError as exc:
                print(f"  已拦截 [{sql}] -> {exc}")


if __name__ == "__main__":
    main()
