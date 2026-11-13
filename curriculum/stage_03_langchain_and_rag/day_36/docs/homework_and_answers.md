# Day 36 课后作业与参考答案

## 作业一：多格式企业知识库构建与 `delete_document` 热更新实战
**题目**：星辰数科新上线了一份《2026 办公设备领用指南.md》和一份《IT 资产清单.csv》。请你使用 `EnterpriseKBService`：
1. 将两份文档写入临时目录并调用 `ingest_file` 入库，打印每份文档的切片数量。
2. 提问 `"MacBook Pro 申请需要谁审批？"`，验证回答包含内联引用 `[1]` 且 `grounded=True`。
3. 随后假设《IT 资产清单.csv》已下线，调用 `delete_document(doc_id)` 删除该文档，并再次提问同一问题，验证系统能够正确触发安全拒答（或不再引用已删除文档）。

### 参考答案：
```python
import tempfile
from pathlib import Path
from zhishu_agent import EnterpriseKBService

with tempfile.TemporaryDirectory() as tmp:
    tmp_dir = Path(tmp)
    md_path = tmp_dir / "device_guide.md"
    md_path.write_text("# 办公设备领用\n入职领取电脑需先在资产系统提交申请。", encoding="utf-8")

    csv_path = tmp_dir / "it_assets.csv"
    csv_path.write_text(
        "设备型号,审批人,发放周期\nMacBook Pro,部门总监与IT负责人,3个工作日\n",
        encoding="utf-8",
    )

    kb = EnterpriseKBService(db_path=tmp_dir / "hw1.db")
    try:
        r_md = kb.ingest_file(md_path)
        r_csv = kb.ingest_file(csv_path)
        print("MD 切片数:", r_md.num_chunks, "| CSV 切片数:", r_csv.num_chunks)

        resp1 = kb.ask("MacBook Pro 申请需要谁审批？", session_id="hw-s1")
        print("删除前:", resp1.grounded, resp1.answer)

        kb.delete_document(r_csv.doc_id)
        resp2 = kb.ask("MacBook Pro 申请需要谁审批？", session_id="hw-s1")
        print("删除后:", resp2.grounded, resp2.answer)
    finally:
        kb.close()
```
**原理解析**：`delete_document` 会同步清理 `_chunks`、`_vectors` 与 `BM25Index` 中的对应切片，确保知识库下线旧制度后，检索层不会残留“幽灵文档”。

---

## 作业二：对比开启 vs 关闭 Rerank 对长尾错误码检索排序的影响
**题目**：在运维知识库中同时存在以下 3 条文本：
1. `"日常巡检：每天上午 10 点检查系统日志与网关状态。"`
2. `"网关常见故障排查：出现错误时请先查看监控面板。"`
3. `"紧急故障码 ERR_502 处理手册：上游服务无响应，请检查 Pod 健康检查并执行滚动重启。"`

请分别调用 `kb.retrieve("ERR_502 网关故障怎么处理", top_k=3, use_rerank=False)` 与 `use_rerank=True`，打印各候选切片的 `bm25_score`、`vector_score`、`rrf_score` 与 `rerank_score`，并说明为什么开启 Rerank 后第 3 条能稳定排在第一位。

### 参考答案：
```python
from zhishu_agent import EnterpriseKBService

kb = EnterpriseKBService()
try:
    kb.ingest_text("日常巡检：每天上午 10 点检查系统日志与网关状态。", source="daily.txt")
    kb.ingest_text("网关常见故障排查：出现错误时请先查看监控面板。", source="general.txt")
    kb.ingest_text(
        "紧急故障码 ERR_502 处理手册：上游服务无响应，请检查 Pod 健康检查并执行滚动重启。",
        source="err502.md",
        file_type=".md",
    )

    query = "ERR_502 网关故障怎么处理"
    print("--- use_rerank=False (仅 RRF) ---")
    for hit in kb.retrieve(query, top_k=3, use_rerank=False):
        print(hit.chunk.source, f"rrf={hit.rrf_score:.4f} bm25={hit.bm25_score:.4f} vec={hit.vector_score:.4f}")

    print("--- use_rerank=True (RRF + 精排) ---")
    for hit in kb.retrieve(query, top_k=3, use_rerank=True):
        print(hit.chunk.source, f"rerank={hit.rerank_score:.4f} bm25={hit.bm25_score:.4f} vec={hit.vector_score:.4f}")
finally:
    kb.close()
```
**原理解析**：`use_rerank=False` 仅依据双路排名位置计算 RRF 分数，无法区分“第 1 名比第 2 名到底强多少”；开启 `use_rerank=True` 后，精排函数会综合评估 `ERR_502`、`网关`、`故障` 等多字词元与双字词的精确覆盖率以及向量相似度，从而将包含完整故障码解决方案的 `err502.md` 稳定置顶。

---

## 作业三：SQLite 会话历史审计与前端引用卡片数据导出
**题目**：某企业客户要求对所有 AI 问答进行合规审计，需支持按 `session_id` 导出完整对话记录及每条回答对应的引用来源（`source` 与 `snippet`）。请编写脚本模拟 2 轮问答后，关闭服务实例并重新打开同一个 SQLite 数据库文件，读取并格式化打印审计日志。

### 参考答案：
```python
import tempfile
from pathlib import Path
from zhishu_agent import EnterpriseKBService

with tempfile.TemporaryDirectory() as tmp:
    db_path = Path(tmp) / "audit.db"

    kb1 = EnterpriseKBService(db_path=db_path)
    kb1.ingest_text("差旅报销须在归来后7个工作日内提交电子发票。", source="finance.txt")
    kb1.ingest_text("员工每年享有5天带薪病假，需附三甲医院证明。", source="hr.txt")
    kb1.ask("差旅报销要在几天内提交？", session_id="audit-2026-01")
    kb1.ask("带薪病假有几天？", session_id="audit-2026-01")
    kb1.close()

    # 模拟服务重启后从 SQLite 恢复审计日志
    kb2 = EnterpriseKBService(db_path=db_path)
    try:
        print("会话列表:", kb2.list_sessions())
        for msg in kb2.get_session_history("audit-2026-01"):
            print(f"[{msg.created_at}] {msg.role}: {msg.content}")
            for cite in msg.citations:
                print(f"   -> 引用[{cite['index']}] {cite['source']}: {cite['snippet']}")
    finally:
        kb2.close()
```
**工程价值**：将 `citations_json` 与消息正文一同持久化在 SQLite 中，使得后端重启、容器重建或前端刷新页面后，依然可以无损还原“回答 + 可点击引用卡片”的完整交互体验。
