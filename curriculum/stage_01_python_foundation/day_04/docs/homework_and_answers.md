# Day 04 课后作业与参考答案

## 作业一：列表推导式（筛选高优先级待办任务）
**题目**：在智枢平台任务队列中，每个任务是一个字典，例如 `{"title": "部署模型", "priority": "high", "done": False}`。已知任务列表 `tasks` 如下：
```python
tasks = [
    {"title": "配置向量库", "priority": "high", "done": False},
    {"title": "更新 README", "priority": "low", "done": True},
    {"title": "修复脱敏正则", "priority": "high", "done": False},
    {"title": "清理日志", "priority": "normal", "done": False},
]
```
请使用**一行列表推导式**，筛选出所有**未完成（`done == False`）且优先级为 `"high"`** 的任务标题列表。

### 参考答案：
```python
high_priority_titles = [
    t["title"] for t in tasks if not t["done"] and t["priority"] == "high"
]
print(high_priority_titles)  # ['配置向量库', '修复脱敏正则']
```

---

## 作业二：元组解包（大模型网关路由配置解析）
**题目**：平台将某个大模型节点的配置打包成了一个不可变元组：
`model_endpoint = ("deepseek-chat", "https://api.deepseek.com/v1", 4096, 0.7)`
分别代表：模型名称、API 地址、最大上下文 Token、默认采样温度。
1. 请使用**元组解包（Tuple Unpacking）**将这 4 个值一次性赋值给 `name, base_url, max_tokens, temperature`。
2. 尝试用星号表达式 `*rest` 只提取第一个模型名称和最后一个温度参数（提示：`name, *_, temperature = model_endpoint`）。

### 参考答案：
```python
model_endpoint = ("deepseek-chat", "https://api.deepseek.com/v1", 4096, 0.7)

# 1. 完整解包
name, base_url, max_tokens, temperature = model_endpoint
print(f"模型: {name} | 地址: {base_url} | 上限: {max_tokens} | 温度: {temperature}")

# 2. 星号占位解包（忽略中间字段）
model_name, *_, temp = model_endpoint
print(f"快速提取 -> {model_name}, temperature={temp}")
```

---

## 作业三：集合去重与交集（RAG 多路检索标签融合）
**题目**：在企业知识库检索时，向量检索返回了文档标签列表 `vector_tags = ["合同", "报销", "差旅", "报销", "财务制度"]`，关键词检索返回了 `bm25_tags = ["差旅", "审批流", "财务制度", "HR"]`。
请使用集合（`set`）完成以下任务：
1. 计算两路检索融合后的全部不重复标签（并集 `|`）。
2. 找出两路检索都命中的高置信度共同标签（交集 `&`）。
3. 找出仅由向量检索发现、关键词检索漏掉的标签（差集 `-`）。

### 参考答案：
```python
vector_tags = ["合同", "报销", "差旅", "报销", "财务制度"]
bm25_tags = ["差旅", "审批流", "财务制度", "HR"]

set_vec = set(vector_tags)
set_bm25 = set(bm25_tags)

all_tags = set_vec | set_bm25
common_tags = set_vec & set_bm25
vector_only_tags = set_vec - set_bm25

print("全部去重标签（并集）:", sorted(all_tags))
print("高置信度共同标签（交集）:", sorted(common_tags))
print("仅向量检索命中（差集）:", sorted(vector_only_tags))
```
