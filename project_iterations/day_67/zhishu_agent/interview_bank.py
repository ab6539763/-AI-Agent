"""智枢企业级智能体平台 Day 67：技术八股题库与模拟笔试自动评分引擎 (v1.0.0-day67)。"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable, Literal, Sequence

CategoryType = Literal["Transformer", "RAG", "Agent", "Python", "Engineering"]
DifficultyType = Literal["Easy", "Medium", "Hard"]

VALID_CATEGORIES: tuple[CategoryType, ...] = (
    "Transformer",
    "RAG",
    "Agent",
    "Python",
    "Engineering",
)
VALID_DIFFICULTIES: tuple[DifficultyType, ...] = ("Easy", "Medium", "Hard")


@dataclass(frozen=True)
class KeyPoint:
    """单个评分要点，支持主描述与多个等价关键词/同义表达匹配。"""

    label: str
    keywords: tuple[str, ...]
    weight: float = 1.0


@dataclass(frozen=True)
class InterviewQuestion:
    """高频技术面试题数据模型。"""

    id: str
    category: CategoryType
    difficulty: DifficultyType
    question: str
    key_points: tuple[KeyPoint, ...]
    model_answer: str
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "difficulty": self.difficulty,
            "question": self.question,
            "key_points": [kp.label for kp in self.key_points],
            "model_answer": self.model_answer,
            "tags": list(self.tags),
        }


@dataclass
class AnswerGradeResult:
    """单题自动评分结果。"""

    question_id: str
    category: CategoryType
    difficulty: DifficultyType
    question: str
    score: float
    coverage_ratio: float
    matched_points: list[str]
    missing_points: list[str]
    feedback: str
    is_empty: bool = False
    model_answer: str = ""


@dataclass
class StudyPlanItem:
    """薄弱维度学习建议项。"""

    category: CategoryType
    average_score: float
    priority: Literal["High", "Medium", "Low"]
    focus_topics: list[str]
    action_plan: str


@dataclass
class ExamReport:
    """模拟笔试综合诊断报告。"""

    session_id: str
    candidate_name: str
    total_questions: int
    answered_count: int
    average_score: float
    grade_level: str
    category_scores: dict[str, float]
    weak_categories: list[CategoryType]
    study_plan: list[StudyPlanItem]
    results: list[AnswerGradeResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "candidate_name": self.candidate_name,
            "total_questions": self.total_questions,
            "answered_count": self.answered_count,
            "average_score": self.average_score,
            "grade_level": self.grade_level,
            "category_scores": dict(self.category_scores),
            "weak_categories": list(self.weak_categories),
            "study_plan": [asdict(item) for item in self.study_plan],
            "results": [asdict(r) for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_markdown(self) -> str:
        lines = [
            f"# 智枢模拟笔试诊断报告 ({self.session_id})",
            "",
            f"- **候选人**: {self.candidate_name}",
            f"- **作答进度**: {self.answered_count}/{self.total_questions}",
            f"- **综合均分**: {self.average_score:.1f} / 100（评级: **{self.grade_level}**）",
            f"- **薄弱维度**: {', '.join(self.weak_categories) if self.weak_categories else '无明显短板'}",
            "",
            "## 各维度得分",
            "",
            "| 技术维度 | 平均分 | 状态 |",
            "| :--- | :---: | :---: |",
        ]
        for cat, score in self.category_scores.items():
            status = "⚠️ 薄弱需加强" if cat in self.weak_categories else "✅ 达标"
            lines.append(f"| {cat} | {score:.1f} | {status} |")

        lines.extend(["", "## 逐题评分详情", ""])
        for idx, r in enumerate(self.results, start=1):
            lines.append(
                f"### {idx}. [{r.category} | {r.difficulty}] {r.question}（得分：{r.score:.1f}/100）"
            )
            lines.append(f"- **命中要点**: {', '.join(r.matched_points) if r.matched_points else '无'}")
            lines.append(f"- **缺失要点**: {', '.join(r.missing_points) if r.missing_points else '无'}")
            lines.append(f"- **评语**: {r.feedback}")
            lines.append("")

        if self.study_plan:
            lines.extend(["## 针对性复习计划", ""])
            for item in self.study_plan:
                lines.append(
                    f"- **[{item.priority}] {item.category}**（当前均分 {item.average_score:.1f}）："
                    f"重点突破 {', '.join(item.focus_topics)}。行动建议：{item.action_plan}"
                )
        return "\n".join(lines)


# ==============================================================================
# 内置 20 道高频技术八股题库（覆盖 5 大维度 × 4 题/维度）
# ==============================================================================

BUILTIN_QUESTION_BANK: tuple[InterviewQuestion, ...] = (
    # ---------------- 1. Transformer / LLM 原理 ----------------
    InterviewQuestion(
        id="TF-001",
        category="Transformer",
        difficulty="Medium",
        question="为什么 Self-Attention 在计算点积后要除以 sqrt(d_k)？",
        key_points=(
            KeyPoint("点积方差随维度 d_k 线性增大", ("方差", "d_k", "variance", "线性增大", "变大"), 1.2),
            KeyPoint("防止点积结果过大导致 Softmax 进入梯度饱和区", ("softmax", "饱和", "梯度消失", "梯度很小"), 1.5),
            KeyPoint("缩放后维持方差为 1，稳定反向传播训练", ("方差为1", "稳定", "反向传播", "尺度"), 1.0),
        ),
        model_answer=(
            "假设 Q 和 K 的各分量独立同分布且均值为 0、方差为 1，则点积 Q·K^T 的均值为 0、方差为 d_k。"
            "当 d_k 较大时，点积绝对值会变大，使 Softmax 函数被推向梯度极小的饱和区，引发梯度消失。"
            "除以 sqrt(d_k) 可将点积方差重新拉回 1，从而保证训练初期梯度稳定。"
        ),
        tags=("Attention", "Softmax", "梯度稳定性"),
    ),
    InterviewQuestion(
        id="TF-002",
        category="Transformer",
        difficulty="Medium",
        question="什么是 KV Cache？它解决了大模型推理中的什么瓶颈，又带来了什么代价？",
        key_points=(
            KeyPoint("缓存历史 Token 的 Key 和 Value 矩阵避免重复计算", ("缓存", "key", "value", "重复计算", "自回归"), 1.4),
            KeyPoint("将 Decode 阶段单步注意力计算复杂度从 O(n^2) 降为 O(n)", ("decode", "o(n)", "复杂度", "prefill", "加速"), 1.2),
            KeyPoint("显存占用随序列长度和 Batch Size 线性增长，成为 Memory-Bound 瓶颈", ("显存", "memory", "o(n)", "pagedattention", "带宽"), 1.2),
        ),
        model_answer=(
            "在自回归 Decode 阶段，新 Token 只需与历史所有 Token 的 K、V 计算注意力，而历史 K、V 不变。"
            "KV Cache 将历史 K、V 缓存在显存中，避免每步重算，显著降低计算量；但代价是显存占用随上下文长度、"
            "层数与 Batch Size 线性增长，使推理从 Compute-Bound 转向 Memory-Bound，工程上常用 PagedAttention 与 GQA 优化。"
        ),
        tags=("推理优化", "KV Cache", "PagedAttention"),
    ),
    InterviewQuestion(
        id="TF-003",
        category="Transformer",
        difficulty="Hard",
        question="RoPE（旋转位置编码）相比绝对位置编码有哪些核心优势？",
        key_points=(
            KeyPoint("通过复数/旋转矩阵将绝对位置编码转化为相对位置依赖", ("相对位置", "旋转矩阵", "内积", "绝对位置"), 1.4),
            KeyPoint("具备良好的外推性与远程衰减特性", ("外推", "长文本", "远程衰减", "extrapolation"), 1.2),
            KeyPoint("可直接作用于 Q 和 K 向量，无需修改 Attention 结构且与线性注意力兼容", ("q", "k", "无需修改", "兼容性"), 1.0),
        ),
        model_answer=(
            "RoPE 对 Q、K 向量按位置索引施加正交旋转矩阵，使得 Q_m 与 K_n 的内积仅依赖词向量本身与相对距离 (m-n)，"
            "以绝对位置的形式实现了相对位置编码；同时具备距离越远注意力权重自然衰减的特性，配合 YaRN/NTK 缩放可实现优异的长上下文外推。"
        ),
        tags=("RoPE", "位置编码", "长上下文"),
    ),
    InterviewQuestion(
        id="TF-004",
        category="Transformer",
        difficulty="Easy",
        question="Pre-LN 与 Post-LN 在 Transformer 训练稳定性上有何区别？",
        key_points=(
            KeyPoint("Post-LN 将 LayerNorm 放在残差相加之后，深层网络梯度易不稳定", ("post-ln", "残差", "之后", "梯度"), 1.2),
            KeyPoint("Pre-LN 将 LayerNorm 放在子层输入前，保留了一条直通的恒等残差路径", ("pre-ln", "输入前", "恒等", "残差路径", "直通"), 1.4),
            KeyPoint("Pre-LN 无需复杂 Warmup 即可稳定收敛，主流 LLM 如 LLaMA 均采用 Pre-LN", ("warmup", "收敛", "llama", "稳定"), 1.0),
        ),
        model_answer=(
            "Post-LN 把 LayerNorm 置于残差连接之后，导致梯度在深层反向传播时容易放大或衰减，通常需要精细的 Learning Rate Warmup；"
            "Pre-LN 把 LayerNorm 放在 Attention/FFN 子层之前，残差主干保持恒等映射，梯度可无损回传，训练显著更稳定，成为现代大模型标配。"
        ),
        tags=("LayerNorm", "残差连接", "训练稳定性"),
    ),

    # ---------------- 2. RAG 检索与评估 ----------------
    InterviewQuestion(
        id="RAG-001",
        category="RAG",
        difficulty="Medium",
        question="为什么企业级 RAG 常采用 BM25 + Dense Vector 混合检索，并用 RRF 进行融合？",
        key_points=(
            KeyPoint("Dense 向量擅长语义匹配但对专有名词、型号、代码等精确词弱", ("语义", "专有名词", "精确", "dense", "向量"), 1.3),
            KeyPoint("BM25 基于词频与逆文档频率擅长精确关键词匹配", ("bm25", "关键词", "精确匹配", "词频", "idf"), 1.3),
            KeyPoint("RRF 基于排名倒数融合，无需对异构分数做归一化", ("rrf", "倒数", "排名", "归一化", "量纲"), 1.4),
        ),
        model_answer=(
            "纯向量检索面对股票代码、报错码、专有名词时容易召回漂移；BM25 擅长字面精确匹配但缺乏语义泛化能力。"
            "两者互补后，由于 BM25 得分无界而 Cosine 相似度在 [-1,1]，直接加权需复杂归一化；"
            "RRF（Reciprocal Rank Fusion）仅依赖各路排序名次 1/(k+rank) 融合，对异常分值鲁棒且无需调参对齐量纲。"
        ),
        tags=("Hybrid Search", "BM25", "RRF"),
    ),
    InterviewQuestion(
        id="RAG-002",
        category="RAG",
        difficulty="Medium",
        question="两阶段检索（Bi-Encoder 粗排 + Cross-Encoder 精排）的原理与取舍是什么？",
        key_points=(
            KeyPoint("Bi-Encoder 独立编码 Query 和 Doc，可离线建索引实现毫秒级向量召回", ("bi-encoder", "离线", "索引", "粗排", "快"), 1.3),
            KeyPoint("Cross-Encoder 将 Query 和 Doc 拼接联合编码，保留全交叉注意力精度更高", ("cross-encoder", "拼接", "交叉注意力", "精排", "精度"), 1.4),
            KeyPoint("精排计算开销大，只能对粗排 Top-K（如 Top-50）做重排以平衡延迟与召回率", ("top-k", "延迟", "开销", "重排", "rerank"), 1.2),
        ),
        model_answer=(
            "Bi-Encoder 分别生成 Query 与文档向量，支持提前离线索引和 ANN 毫秒级检索，但丢失了词级细粒度交互；"
            "Cross-Encoder 将 [CLS] Query [SEP] Doc 一起送入 Transformer 做全注意力交互，相关性判断极准但无法预计算。"
            "工程上先用 Bi-Encoder 召回 Top-50，再用 Cross-Encoder 精排出 Top-5，兼顾高精度与低延迟。"
        ),
        tags=("Rerank", "Bi-Encoder", "Cross-Encoder"),
    ),
    InterviewQuestion(
        id="RAG-003",
        category="RAG",
        difficulty="Hard",
        question="如何使用 RAGAS 框架对 RAG 系统进行自动化定量评估？核心指标有哪些？",
        key_points=(
            KeyPoint("Faithfulness（忠实度）：衡量生成答案是否完全基于检索上下文、有无幻觉", ("faithfulness", "忠实度", "幻觉", "上下文"), 1.3),
            KeyPoint("Answer Relevance（答案相关性）：衡量回答是否切中用户问题", ("relevance", "相关性", "切题"), 1.2),
            KeyPoint("Context Precision / Context Recall：衡量检索排序质量与参考答案覆盖率", ("context precision", "context recall", "精确率", "召回率"), 1.4),
        ),
        model_answer=(
            "RAGAS 从检索与生成两个维度进行无参考或弱参考自动化评估："
            "检索侧看 Context Precision（相关片段是否排在前面）与 Context Recall（是否召回了支撑标准答案的关键片段）；"
            "生成侧看 Faithfulness（答案中的陈述能否被检索上下文逐条推出，防幻觉）与 Answer Relevance（是否正面回答问题）。"
        ),
        tags=("RAGAS", "评估", "Faithfulness"),
    ),
    InterviewQuestion(
        id="RAG-004",
        category="RAG",
        difficulty="Easy",
        question="文档切分（Chunking）时 chunk_size 和 chunk_overlap 设置不当会引发什么问题？",
        key_points=(
            KeyPoint("chunk_size 过小会丢失上下文语义完整度，过大则引入噪声稀释向量表征", ("过小", "过大", "语义完整", "噪声", "稀释"), 1.4),
            KeyPoint("chunk_overlap 过小会导致跨块边界的句子或实体被截断", ("overlap", "边界", "截断", "跨块"), 1.3),
            KeyPoint("需结合文档结构（标题/段落/Markdown）或 Parent-Child 分块策略优化", ("结构", "parent", "child", "父子", "markdown"), 1.0),
        ),
        model_answer=(
            "chunk_size 过小会使单个切片缺乏完整上下文，过大则会让无关信息稀释 Embedding 语义并浪费 LLM Context；"
            "缺乏 overlap 会把关键因果句或实体关系生硬切断。工程上建议按语义边界切分并保留 10%~20% 重叠，"
            "或采用“小块检索、大块召回”（Parent-Child）策略。"
        ),
        tags=("Chunking", "Embedding", "检索优化"),
    ),

    # ---------------- 3. Agent 架构与 Tool Use ----------------
    InterviewQuestion(
        id="AGT-001",
        category="Agent",
        difficulty="Medium",
        question="ReAct 架构的核心工作流是什么？与 Plan-and-Execute 相比有何优缺点？",
        key_points=(
            KeyPoint("ReAct 交替执行 Thought -> Action -> Observation 循环，动态调整决策", ("thought", "action", "observation", "交替", "循环"), 1.4),
            KeyPoint("Plan-and-Execute 先生成全局子任务计划再逐步执行，减少高频 LLM 调用", ("plan", "execute", "全局计划", "子任务", "成本"), 1.3),
            KeyPoint("ReAct 灵活适应环境变化但长链路易偏航，Plan-and-Execute 适合结构化长任务但重规划成本高", ("长链路", "偏航", "重规划", "灵活"), 1.2),
        ),
        model_answer=(
            "ReAct 通过 Thought（推理）-> Action（调用工具）-> Observation（观察结果）的闭环迭代推进，"
            "对动态反馈极其敏感，但在多跳复杂任务中每步都要调用大模型，延迟高且容易跑偏；"
            "Plan-and-Execute 先由 Planner 拆解 DAG/步骤清单再交给 Executor 执行，全局一致性强、成本更低，但遇到意外报错时需触发 Re-plan。"
        ),
        tags=("ReAct", "Plan-and-Execute", "Agent 范式"),
    ),
    InterviewQuestion(
        id="AGT-002",
        category="Agent",
        difficulty="Medium",
        question="如何设计高可靠的 Function Calling / Tool Use 机制以防止参数幻觉与死循环？",
        key_points=(
            KeyPoint("使用严格的 JSON Schema（如 Pydantic）校验工具入参并在失败时返回可读错误提示", ("json schema", "pydantic", "校验", "参数"), 1.3),
            KeyPoint("设置 max_iterations、工具调用预算与重复调用检测防止死循环", ("max_iterations", "死循环", "预算", "上限", "重复"), 1.4),
            KeyPoint("对写操作/高风险动作引入幂等键与人类审批（HITL）确认", ("幂等", "hitl", "人工审批", "高风险"), 1.2),
        ),
        model_answer=(
            "高可靠 Tool Use 需三层防护：1）契约层用 Pydantic/JSON Schema 强校验参数类型与枚举值，校验失败将错误信息作为 Observation 喂回模型自纠；"
            "2）控制层设置 max_iterations、Token 预算与相同参数重复调用熔断，杜绝死循环；"
            "3）安全层对不可逆写操作强制走 HITL 人工审批与幂等性校验。"
        ),
        tags=("Function Calling", "Pydantic", "HITL"),
    ),
    InterviewQuestion(
        id="AGT-003",
        category="Agent",
        difficulty="Hard",
        question="企业级 Agent 如何实现 Human-in-the-Loop（HITL）的挂起与断点恢复？",
        key_points=(
            KeyPoint("在敏感工具调用前拦截执行，将上下文与待审批动作持久化为 pending 状态", ("拦截", "持久化", "pending", "状态机"), 1.4),
            KeyPoint("释放当前请求线程/协程，通过审批回调或幂等接口触发后续恢复执行", ("释放", "异步", "回调", "恢复", "幂等"), 1.3),
            KeyPoint("校验审批人权限与审批状态流转（pending -> approved/rejected），防止越权或重放", ("权限", "approved", "rejected", "越权", "重放"), 1.2),
        ),
        model_answer=(
            "HITL 不能在服务端长阻塞等待人工点击，而应采用状态机 + 异步检查点设计："
            "当 Agent 触发高风险工具时，拦截并把会话状态、工具名、脱敏参数持久化到数据库（如 SQLite/Postgres）置为 pending，"
            "向前端推送审批卡片后立即释放资源；人工点击批准/驳回后，通过带幂等校验的审批接口推动状态流转并唤醒 Agent 继续执行。"
        ),
        tags=("HITL", "状态机", "持久化"),
    ),
    InterviewQuestion(
        id="AGT-004",
        category="Agent",
        difficulty="Easy",
        question="MCP（Model Context Protocol）解决了 Agent 开发中的什么核心痛点？",
        key_points=(
            KeyPoint("统一了大模型应用（Host/Client）与外部数据源/工具（Server）的通信协议", ("统一", "协议", "client", "server", "标准化"), 1.4),
            KeyPoint("避免为不同模型和工具重复编写 M×N 定制胶水适配代码", ("m×n", "胶水代码", "复用", "生态"), 1.3),
            KeyPoint("规范了 Tools、Resources、Prompts 三类核心原语的暴露与发现方式", ("tools", "resources", "prompts", "发现"), 1.1),
        ),
        model_answer=(
            "过去每个 Agent 框架都要为每个数据源单独写适配插件，形成 M×N 集成爆炸。"
            "MCP 像 AI 时代的 USB-C 接口，标准化了 Client 与 Server 之间暴露 Tools、Resources 和 Prompts 的协议，"
            "使工具只需实现一次 MCP Server 即可被多种智能体无缝复用。"
        ),
        tags=("MCP", "协议标准", "工具生态"),
    ),

    # ---------------- 4. Python 异步与 FastAPI ----------------
    InterviewQuestion(
        id="PY-001",
        category="Python",
        difficulty="Medium",
        question="在 FastAPI 异步接口中调用同步阻塞库（如 requests 或阻塞型数据库驱动）会有什么后果？如何解决？",
        key_points=(
            KeyPoint("阻塞当前进程的事件循环（Event Loop），导致整个 Worker 无法并发处理其他请求", ("事件循环", "event loop", "阻塞", "并发"), 1.5),
            KeyPoint("替换为原生异步库（如 httpx、asyncpg）", ("httpx", "asyncpg", "异步库"), 1.2),
            KeyPoint("若必须调用同步代码，应使用 asyncio.to_thread / run_in_executor 或将路由定义为普通 def", ("to_thread", "run_in_executor", "线程池", "def"), 1.3),
        ),
        model_answer=(
            "async def 路由运行在单线程 asyncio 事件循环上，内部一旦执行同步阻塞 I/O，整个事件循环会被卡死，吞吐量退化为 1。"
            "首选方案是换成 httpx/aiohttp 等原生异步库；若底层 SDK 无异步版本，应使用 await asyncio.to_thread(fn) 放到线程池执行，"
            "或直接将该接口定义为普通同步 def（FastAPI 会自动将其调度到 AnyIO 线程池）。"
        ),
        tags=("asyncio", "FastAPI", "事件循环"),
    ),
    InterviewQuestion(
        id="PY-002",
        category="Python",
        difficulty="Medium",
        question="为什么大模型流式输出（Streaming）通常采用 SSE（Server-Sent Events）而不是 WebSocket？",
        key_points=(
            KeyPoint("SSE 基于标准 HTTP 协议，天然兼容反向代理、网关与鉴权机制", ("http", "网关", "代理", "兼容"), 1.3),
            KeyPoint("大模型对话主要是服务端向客户端单向推送 Token，SSE 更轻量且内置断线重连", ("单向", "轻量", "断线重连", "token"), 1.4),
            KeyPoint("WebSocket 适合高频双向实时通信，但连接状态维护和水平扩展成本更高", ("websocket", "双向", "状态", "扩展"), 1.1),
        ),
        model_answer=(
            "LLM 流式生成本质上是“客户端发一次请求 -> 服务端持续单向吐出 Token”，与 SSE 的单向文本流模型高度契合。"
            "SSE 复用普通 HTTP/1.1 或 HTTP/2 连接，无需协议升级，对 Nginx、负载均衡、Header 鉴权更友好；"
            "相比 WebSocket 省去了双向心跳与全双工状态维护成本。"
        ),
        tags=("SSE", "WebSocket", "流式输出"),
    ),
    InterviewQuestion(
        id="PY-003",
        category="Python",
        difficulty="Easy",
        question="Pydantic v2 在 FastAPI 与 Agent 工程中主要承担什么角色？相比手写 dict 有何优势？",
        key_points=(
            KeyPoint("运行时类型校验与自动数据解析/转换", ("类型校验", "解析", "运行时", "转换"), 1.4),
            KeyPoint("自动生成 JSON Schema，可直接用于 OpenAPI 文档与 LLM Function Calling 契约", ("json schema", "openapi", "function calling"), 1.3),
            KeyPoint("v2 底层基于 Rust（pydantic-core），序列化与校验性能大幅提升", ("rust", "pydantic-core", "性能"), 1.1),
        ),
        model_answer=(
            "Pydantic v2 提供了声明式的强类型数据契约：在接口边界自动完成校验、默认值填充与报错提示；"
            "同时可一键导出 JSON Schema，既支撑 FastAPI 自动生成 Swagger 文档，也直接作为大模型 Structured Output / Tool Call 的结构约束，"
            "Rust 内核使其吞吐比 v1 提升数倍。"
        ),
        tags=("Pydantic", "类型安全", "JSON Schema"),
    ),
    InterviewQuestion(
        id="PY-004",
        category="Python",
        difficulty="Hard",
        question="Python GIL（全局解释器锁）对多线程并发有什么影响？AI 后端如何绕过 GIL 提升 CPU 密集型吞吐？",
        key_points=(
            KeyPoint("GIL 保证同一时刻只有一个线程执行 Python 字节码，限制 CPU 密集型多线程扩展", ("字节码", "同一时刻", "cpu密集", "多线程"), 1.4),
            KeyPoint("I/O 密集型任务（网络/磁盘）在等待时会释放 GIL，因此多线程/asyncio 依然高效", ("i/o密集", "释放", "asyncio"), 1.2),
            KeyPoint("CPU 密集型可通过多进程（multiprocessing/Uvicorn workers）或 C/Rust 扩展（NumPy/PyTorch）绕过", ("多进程", "multiprocessing", "workers", "c扩展", "numpy"), 1.3),
        ),
        model_answer=(
            "GIL 使得纯 Python 多线程无法利用多核并行执行 CPU 密集任务，但在等待网络/LLM API 响应等 I/O 阶段会释放 GIL。"
            "对于嵌入计算、文档解析等 CPU 密集型任务，AI 后端通常采用多进程 Worker（如 Gunicorn/Uvicorn --workers）、"
            "异步任务队列（Celery/ARQ）或将计算下沉至释放 GIL 的 C/C++/Rust 扩展库。"
        ),
        tags=("GIL", "多进程", "并发模型"),
    ),

    # ---------------- 5. 大模型工程与安全 ----------------
    InterviewQuestion(
        id="ENG-001",
        category="Engineering",
        difficulty="Medium",
        question="如何系统性地防范 Prompt 注入（Prompt Injection）与敏感信息（PII）泄露？",
        key_points=(
            KeyPoint("输入输出边界分离与指令隔离（System Prompt 与不可信用户输入隔离）", ("隔离", "system", "用户输入", "边界"), 1.3),
            KeyPoint("在网关/护栏层对输入输出进行 PII 脱敏（正则/NER 识别手机号、身份证、密钥）", ("pii", "脱敏", "护栏", "guardrail", "正则"), 1.4),
            KeyPoint("遵循最小权限原则，工具执行前做策略校验与高风险 HITL 审批", ("最小权限", "策略", "hitl", "审批"), 1.2),
        ),
        model_answer=(
            "防御 Prompt 注入与 PII 泄露需要纵深防御：1）提示词层明确角色边界，对外部检索内容加定界符标记为不可信数据；"
            "2）护栏层在请求进 LLM 前和响应出 LLM 后执行 PII 脱敏与敏感词/越狱模式拦截；"
            "3）执行层坚持最小权限，工具调用参数不完全信任模型输出，敏感操作强制走权限校验与人工审批。"
        ),
        tags=("Prompt Injection", "PII 脱敏", "AI 安全"),
    ),
    InterviewQuestion(
        id="ENG-002",
        category="Engineering",
        difficulty="Medium",
        question="企业级 Agent 上线后，如何建设可观测性（Observability）与成本控制体系？",
        key_points=(
            KeyPoint("全链路 Trace 追踪（Request -> Retrieval -> LLM -> Tool），记录延迟与状态", ("trace", "全链路", "延迟", "opentelemetry"), 1.4),
            KeyPoint("统计 Token 消耗、TTFT（首字延迟）、TPOT 与分租户成本归因", ("token", "ttft", "成本", "租户"), 1.3),
            KeyPoint("通过语义缓存（Semantic Cache）、模型路由（大小模型分级）与上下文裁剪降本", ("语义缓存", "路由", "大小模型", "降本"), 1.2),
        ),
        model_answer=(
            "可观测性核心是把黑盒调用拆成结构化 Trace，精确记录检索耗时、TTFT、工具失败率及每次调用的 Prompt/Completion Token 成本。"
            "成本优化则依靠三板斧：高频相似问句走语义缓存、简单意图路由到轻量小模型、长对话做摘要压缩与 Context 裁剪。"
        ),
        tags=("Observability", "TTFT", "FinOps"),
    ),
    InterviewQuestion(
        id="ENG-003",
        category="Engineering",
        difficulty="Easy",
        question="在无外部真实 LLM API 的 CI/CD 环境中，如何为 Agent 编写可稳定回归的自动化测试？",
        key_points=(
            KeyPoint("对 LLM 客户端进行依赖注入与 Fake/Mock 替换，保证确定性输出", ("mock", "fake", "依赖注入", "确定性"), 1.4),
            KeyPoint("覆盖核心状态机、工具契约校验、异常边界与端到端冒烟测试", ("状态机", "契约", "边界", "pytest"), 1.3),
            KeyPoint("配合离线评测集（Golden Dataset）在发布前验证召回率与格式合规率", ("golden", "评测集", "回归", "ci"), 1.1),
        ),
        model_answer=(
            "CI 流水线不应依赖昂贵且非确定性的外部 LLM API。应通过抽象 LLMProvider 接口，"
            "在 pytest 中注入确定性的 FakeLLM/MockClient，重点测试路由逻辑、Tool Schema 校验、HITL 状态流转及异常兜底；"
            "同时在夜间或发版前用固定 Golden Dataset 跑端到端质量基线。"
        ),
        tags=("pytest", "Mock", "CI/CD"),
    ),
    InterviewQuestion(
        id="ENG-004",
        category="Engineering",
        difficulty="Hard",
        question="企业私有知识库场景下，如果发现 RAG 幻觉率依然偏高，你会按什么优先级排查与治理？",
        key_points=(
            KeyPoint("先排查检索侧：是否漏召回或排序靠后（优化切分、混合检索、Rerank）", ("检索", "漏召回", "rerank", "切分"), 1.4),
            KeyPoint("再排查上下文与提示词侧：强制引用溯源（Citation）与拒答策略（不知道即拒答）", ("引用", "溯源", "citation", "拒答"), 1.3),
            KeyPoint("最后引入后置忠实度校验（Faithfulness Check / NLI）或微调领域模型", ("忠实度", "校验", "nli", "微调"), 1.2),
        ),
        model_answer=(
            "治理幻觉应遵循“先检索、再生成、后校验”的顺序：首先用 Context Recall 排查是否根本没召回正确证据，通过混合检索与 Rerank 修复；"
            "其次在 Prompt 中要求严格基于参考片段作答并附带 [doc_id] 引用编号，无证据时明确拒答；"
            "最后对高风险回答增加轻量忠实度核验，检测陈述与原文是否冲突。"
        ),
        tags=("幻觉治理", "Citation", "全链路排查"),
    ),
)


def get_question_bank() -> list[InterviewQuestion]:
    """返回内置全部面试题列表。"""
    return list(BUILTIN_QUESTION_BANK)


def list_questions(
    category: CategoryType | None = None,
    difficulty: DifficultyType | None = None,
) -> list[InterviewQuestion]:
    """按技术维度或难度筛选面试题。"""
    if category is not None and category not in VALID_CATEGORIES:
        raise ValueError(f"不支持的题目分类: {category!r}，可选值: {VALID_CATEGORIES}")
    if difficulty is not None and difficulty not in VALID_DIFFICULTIES:
        raise ValueError(f"不支持的题目难度: {difficulty!r}，可选值: {VALID_DIFFICULTIES}")

    results: list[InterviewQuestion] = []
    for q in BUILTIN_QUESTION_BANK:
        if category is not None and q.category != category:
            continue
        if difficulty is not None and q.difficulty != difficulty:
            continue
        results.append(q)
    return results


def _normalize_text(text: str) -> str:
    """规范化文本用于中英文关键词匹配（小写 + 空白折叠）。"""
    lowered = text.lower().strip()
    return re.sub(r"\s+", " ", lowered)


def grade_answer(question: InterviewQuestion, answer: str) -> AnswerGradeResult:
    """基于要点覆盖率与权重对单道面试题作答进行自动评分。"""
    cleaned = answer.strip()
    if not cleaned:
        missing = [kp.label for kp in question.key_points]
        return AnswerGradeResult(
            question_id=question.id,
            category=question.category,
            difficulty=question.difficulty,
            question=question.question,
            score=0.0,
            coverage_ratio=0.0,
            matched_points=[],
            missing_points=missing,
            feedback="未检测到有效作答内容。建议先梳理核心概念，再逐条补充关键机制与工程取舍。",
            is_empty=True,
            model_answer=question.model_answer,
        )

    norm_answer = _normalize_text(cleaned)
    matched_points: list[str] = []
    missing_points: list[str] = []
    total_weight = sum(kp.weight for kp in question.key_points)
    matched_weight = 0.0

    for kp in question.key_points:
        hit = any(kw.lower() in norm_answer for kw in kp.keywords)
        if hit:
            matched_points.append(kp.label)
            matched_weight += kp.weight
        else:
            missing_points.append(kp.label)

    coverage_ratio = (len(matched_points) / len(question.key_points)) if question.key_points else 1.0
    raw_score = (matched_weight / total_weight * 100.0) if total_weight > 0 else 0.0
    score = round(min(100.0, max(0.0, raw_score)), 1)

    if score >= 85.0:
        feedback = "回答全面且要点精准，已具备大厂技术面标准表达水准。"
    elif score >= 60.0:
        feedback = (
            f"命中了核心方向，但仍缺少 {len(missing_points)} 个关键得分点："
            f"{'；'.join(missing_points)}。"
        )
    else:
        feedback = (
            "核心得分点覆盖不足，建议对照参考答案重点补齐："
            f"{'；'.join(missing_points)}。"
        )

    return AnswerGradeResult(
        question_id=question.id,
        category=question.category,
        difficulty=question.difficulty,
        question=question.question,
        score=score,
        coverage_ratio=round(coverage_ratio, 3),
        matched_points=matched_points,
        missing_points=missing_points,
        feedback=feedback,
        is_empty=False,
        model_answer=question.model_answer,
    )


_STUDY_ACTION_MAP: dict[CategoryType, str] = {
    "Transformer": "手推 Scaled Dot-Product Attention 梯度与 KV Cache 显存公式，梳理 RoPE 与 Pre-LN 原理。",
    "RAG": "对比 BM25+Vector+RRF 与 Cross-Encoder Rerank 链路，结合 RAGAS 四大指标做一次量化消融。",
    "Agent": "复盘 ReAct vs Plan-and-Execute 差异，重点打通 Pydantic 校验、防死循环与 HITL 状态机。",
    "Python": "排查 async def 中的同步阻塞陷阱，掌握 asyncio.to_thread、SSE 流式响应与 Pydantic v2。",
    "Engineering": "强化 Prompt 注入防线、PII 脱敏、OpenTelemetry Trace 可观测性与 Mock 确定性单测。",
}


class ExamSession:
    """模拟笔试会话管理器：支持抽题、交卷评分、薄弱维度诊断与学习计划生成。"""

    def __init__(
        self,
        questions: Sequence[InterviewQuestion] | None = None,
        candidate_name: str = "候选人",
        session_id: str = "EXAM-DAY67-001",
    ) -> None:
        self.session_id = session_id
        self.candidate_name = candidate_name
        self.questions: list[InterviewQuestion] = (
            list(questions) if questions is not None else self.select_questions(n=5, seed=67)
        )
        self._question_map: dict[str, InterviewQuestion] = {q.id: q for q in self.questions}
        self._results: dict[str, AnswerGradeResult] = {}

    @staticmethod
    def select_questions(
        n: int = 5,
        categories: Iterable[CategoryType] | None = None,
        difficulty: DifficultyType | None = None,
        seed: int | None = None,
    ) -> list[InterviewQuestion]:
        """从题库中抽题；默认覆盖 5 大技术维度，保证分布均衡。"""
        if n <= 0:
            raise ValueError("抽题数量 n 必须大于 0")

        rng = random.Random(seed)
        target_cats = list(categories) if categories is not None else list(VALID_CATEGORIES)
        pool: list[InterviewQuestion] = []
        for cat in target_cats:
            pool.extend(list_questions(category=cat, difficulty=difficulty))

        if not pool:
            raise ValueError("当前筛选条件下题库为空，无法组卷")

        if n >= len(pool):
            selected = list(pool)
            rng.shuffle(selected)
            return selected

        # 优先每个指定维度至少抽 1 题，其余随机补齐
        selected: list[InterviewQuestion] = []
        selected_ids: set[str] = set()
        shuffled_cats = list(target_cats)
        rng.shuffle(shuffled_cats)

        for cat in shuffled_cats:
            if len(selected) >= n:
                break
            cat_candidates = [q for q in pool if q.category == cat and q.id not in selected_ids]
            if cat_candidates:
                pick = rng.choice(cat_candidates)
                selected.append(pick)
                selected_ids.add(pick.id)

        remaining = [q for q in pool if q.id not in selected_ids]
        rng.shuffle(remaining)
        while len(selected) < n and remaining:
            selected.append(remaining.pop())

        return selected

    def submit_answer(self, question_id: str, answer: str) -> AnswerGradeResult:
        """提交单题作答并立即返回评分结果。"""
        if question_id not in self._question_map:
            raise KeyError(f"题目 {question_id!r} 不在本次笔试套卷中")
        question = self._question_map[question_id]
        result = grade_answer(question, answer)
        self._results[question_id] = result
        return result

    def finish_exam(self, weak_threshold: float = 70.0) -> ExamReport:
        """结束笔试并生成包含薄弱维度诊断与复习计划的综合报告。"""
        ordered_results: list[AnswerGradeResult] = []
        for q in self.questions:
            if q.id in self._results:
                ordered_results.append(self._results[q.id])
            else:
                ordered_results.append(grade_answer(q, ""))

        answered_count = sum(1 for r in ordered_results if not r.is_empty)
        average_score = (
            round(sum(r.score for r in ordered_results) / len(ordered_results), 1)
            if ordered_results
            else 0.0
        )

        # 按维度聚合得分
        cat_buckets: dict[CategoryType, list[AnswerGradeResult]] = {}
        for r in ordered_results:
            cat_buckets.setdefault(r.category, []).append(r)

        category_scores: dict[str, float] = {
            cat: round(sum(item.score for item in items) / len(items), 1)
            for cat, items in cat_buckets.items()
        }

        weak_categories: list[CategoryType] = [
            cat for cat, avg in category_scores.items() if avg < weak_threshold
        ]
        # 按得分从低到高排序，便于优先攻克最薄弱模块
        weak_categories.sort(key=lambda c: category_scores[c])

        study_plan: list[StudyPlanItem] = []
        for cat in weak_categories:
            avg = category_scores[cat]
            priority: Literal["High", "Medium", "Low"] = "High" if avg < 50.0 else "Medium"
            focus_topics: list[str] = []
            for item in cat_buckets[cat]:
                focus_topics.extend(item.missing_points[:2])
            if not focus_topics:
                focus_topics = [f"{cat} 核心原理与工程实践"]
            study_plan.append(
                StudyPlanItem(
                    category=cat,
                    average_score=avg,
                    priority=priority,
                    focus_topics=list(dict.fromkeys(focus_topics))[:4],
                    action_plan=_STUDY_ACTION_MAP[cat],
                )
            )

        if average_score >= 85.0:
            grade_level = "A（优秀 · 建议直接投递一线大厂）"
        elif average_score >= 70.0:
            grade_level = "B（良好 · 补齐局部短板即可冲刺）"
        elif average_score >= 50.0:
            grade_level = "C（及格边缘 · 需重点强化高频八股）"
        else:
            grade_level = "D（待提升 · 建议系统性重构核心知识体系）"

        return ExamReport(
            session_id=self.session_id,
            candidate_name=self.candidate_name,
            total_questions=len(self.questions),
            answered_count=answered_count,
            average_score=average_score,
            grade_level=grade_level,
            category_scores=category_scores,
            weak_categories=weak_categories,
            study_plan=study_plan,
            results=ordered_results,
        )
