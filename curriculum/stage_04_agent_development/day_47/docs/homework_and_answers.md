# Day 47 课后作业与参考答案

## 作业一：只读 SQL 安全护栏（`validate_readonly_sql`）攻防验证
**题目**：在 Text-to-SQL 场景中，任何写操作或堆叠注入都可能造成生产数据灾难。请你编写一段验证代码，使用 `validate_readonly_sql` 完成以下检查：
1. 验证合法的 `JOIN` 查询 `SELECT r.region_name, SUM(o.total_amount) FROM orders o JOIN regions r ON o.region_id = r.region_id GROUP BY r.region_name` 能够顺利通过校验。
2. 验证以下 5 类高危语句均会触发 `SQLSecurityError`：`DROP TABLE orders`、`DELETE FROM orders`、`UPDATE orders SET status='x'`、`PRAGMA table_info(orders)`、`SELECT * FROM orders; DROP TABLE orders`。

### 参考答案：
```python
from zhishu_agent import SQLSecurityError, validate_readonly_sql

# 1. 合法只读查询应放行
valid_sql = (
    "SELECT r.region_name, SUM(o.total_amount) "
    "FROM orders o JOIN regions r ON o.region_id = r.region_id "
    "GROUP BY r.region_name"
)
assert validate_readonly_sql(valid_sql).startswith("SELECT")

# 2. 高危写操作、PRAGMA 与分号堆叠注入均应被拦截
dangerous_sqls = [
    "DROP TABLE orders",
    "DELETE FROM orders",
    "UPDATE orders SET status='x'",
    "PRAGMA table_info(orders)",
    "SELECT * FROM orders; DROP TABLE orders",
]

for bad_sql in dangerous_sqls:
    try:
        validate_readonly_sql(bad_sql)
        raise AssertionError(f"预期应拦截: {bad_sql}")
    except SQLSecurityError as exc:
        print(f"成功拦截 [{bad_sql}] -> {exc}")

print("作业一校验通过！")
```

---

## 作业二：Schema Prompt Injection 防御测试
**题目**：假设上游大模型受到用户 Prompt Injection 诱导，在 `generate_sql` 阶段输出了一条包含 `INSERT` 或 `; DROP TABLE` 的恶意 SQL。请你通过向 `TextToSQLAgent` 注入自定义 `llm_fn` 的方式模拟该攻击，并验证：
1. `agent.ask("请帮我统计销售数据")` 返回的 `result.status == "blocked"`，且 `result.rows == []`。
2. 数据库中的 `orders` 表数据完好无损（总行数仍为 `12`）。

### 参考答案：
```python
from zhishu_agent import SalesDatabase, TextToSQLAgent

def hacked_llm_fn(question: str, schema_context: str) -> str:
    # 模拟模型被 Prompt Injection 劫持后输出堆叠注入 SQL
    return "SELECT * FROM orders; DROP TABLE orders"

with SalesDatabase(":memory:") as db:
    db.initialize_and_seed()
    agent = TextToSQLAgent(db=db, llm_fn=hacked_llm_fn)

    result = agent.ask("请帮我统计销售数据")
    assert result.status == "blocked"
    assert result.rows == []
    assert "安全护栏已拦截" in result.insight

    # 验证 orders 表依然完整
    count_rows = db.execute_readonly("SELECT COUNT(*) AS cnt FROM orders")
    assert count_rows[0]["cnt"] == 12
    print("作业二校验通过！拦截详情:", result.insight)
```

---

## 作业三：多表 `JOIN` 查询与商业洞察生成
**题目**：利用 `SalesDatabase` 与 `TextToSQLAgent`，完成以下多表关联分析验证：
1. 初始化 `SalesDatabase(":memory:")` 并调用 `initialize_and_seed()`。
2. 使用 `agent.ask("各大区已完成订单的实际销售额与目标达成率是多少？")` 触发 `orders` 与 `regions` 的多表 `JOIN` 查询。
3. 断言返回的 `result.status == "success"`、查询结果包含 4 个大区，且 `华东` 大区的 `达成率百分比` 大于 `100.0`，同时打印中文商业洞察摘要。

### 参考答案：
```python
from zhishu_agent import SalesDatabase, TextToSQLAgent

with SalesDatabase(":memory:") as db:
    db.initialize_and_seed()
    agent = TextToSQLAgent(db=db)

    result = agent.ask("各大区已完成订单的实际销售额与目标达成率是多少？")
    assert result.status == "success"
    assert "JOIN regions" in result.generated_sql
    assert len(result.rows) == 4

    east_china = next(r for r in result.rows if r["大区"] == "华东")
    assert east_china["达成率百分比"] > 100.0

    print("生成 SQL:", result.generated_sql)
    print("商业洞察:", result.insight)
    print("作业三校验通过！")
```
