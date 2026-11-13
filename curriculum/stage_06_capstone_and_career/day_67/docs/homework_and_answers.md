# Day 67 课后作业与参考答案

## 作业 1：模拟笔试诊断与弱项补齐实战
**要求**：
1. 调用 `ExamSession.select_questions(n=5, seed=100)` 生成一套覆盖五大技术维度的模拟笔试卷；
2. 编写一段脚本，针对其中 3 道题用自己的话作答，故意将另外 2 道题留空或简答；
3. 调用 `finish_exam(weak_threshold=70.0)` 生成 `ExamReport`，打印 `weak_categories` 与 `study_plan`，并导出 Markdown 报告。

**参考答案要点**：
```python
from zhishu_agent.interview_bank import ExamSession

questions = ExamSession.select_questions(n=5, seed=100)
session = ExamSession(questions=questions, candidate_name="实战学员")
for i, q in enumerate(questions):
    ans = q.model_answer if i < 3 else ""
    session.submit_answer(q.id, ans)

report = session.finish_exam(weak_threshold=70.0)
print("薄弱维度:", report.weak_categories)
print(report.to_markdown())
```

---

## 作业 2：扩展自定义公司高频题库
**要求**：
为 `InterviewQuestion` 新增一道关于「大模型推理加速：Continuous Batching（连续批处理）与 Static Batching 的区别」的题目（分类为 `Transformer`，难度 `Hard`），设计至少 3 个带同义关键词的 `KeyPoint`，并用 `grade_answer()` 验证高分答案与空答案的评分输出。

**参考答案**：
```python
from zhishu_agent.interview_bank import InterviewQuestion, KeyPoint, grade_answer

q_batch = InterviewQuestion(
    id="TF-CUSTOM-01",
    category="Transformer",
    difficulty="Hard",
    question="Continuous Batching（连续批处理）相比 Static Batching 如何提升大模型推理吞吐？",
    key_points=(
        KeyPoint("Static Batching 需等待同批次最长序列完成，造成 GPU 空转气泡", ("static", "最长", "等待", "气泡", "空转"), 1.3),
        KeyPoint("Continuous Batching 按 Iteration（Token 步）粒度调度，先结束的请求立即释放槽位并插入新请求", ("iteration", "步", "槽位", "立即", "插入"), 1.5),
        KeyPoint("显著提升 GPU 利用率与系统吞吐量，降低尾延迟", ("吞吐", "利用率", "尾延迟"), 1.0),
    ),
    model_answer=(
        "Static Batching 必须等 batch 内最长的请求生成 EOS 后才能整体释放，短请求会产生大量 padding 与算力气泡；"
        "Continuous Batching 在每个 Decode Iteration 结束时即可剔除已完成序列并动态塞入队列中的新请求，大幅提升 GPU 利用率与吞吐。"
    ),
)

res = grade_answer(q_batch, "Static Batching 要等最长请求造成空转，Continuous Batching 按 iteration 调度，完成后立即释放槽位插入新请求，提升吞吐。")
assert res.score >= 95.0
```

---

## 作业 3：口述训练（Star + 八股联动）
**要求**：
结合你在《智枢企业级智能体平台》中开发的 **Hybrid Search + Rerank** 或 **HITL 审批状态机**，在 90 秒内口述回答：“*你在项目中遇到过什么线上瓶颈？底层原理是什么？你是怎么选型和量化验证的？*”

**参考答题结构**：
- **现象与瓶颈**：纯向量检索对财务代码与专有名词召回率仅 71%（对应 `RAG-001`）。
- **原理与选型**：引入 BM25 补齐字面精确匹配，并用 RRF `1/(k+rank)` 融合规避量纲对齐问题，再用 Cross-Encoder 对 Top-50 做精排（对应 `RAG-002`）。
- **量化结果**：Top-5 召回率提升至 92%，P95 延迟控制在 165ms 以内。
