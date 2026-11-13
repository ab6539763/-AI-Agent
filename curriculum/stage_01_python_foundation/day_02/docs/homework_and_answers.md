# Day 02 课后作业与参考答案

## 作业一：运算符实战（算术、比较与逻辑运算符）
**题目**：某企业内部大模型网关规定单次请求的放行条件如下：
1. 字符数 `char_count` 必须大于 `0` 且不超过 `4000`；
2. 预估费用 `estimated_cost = (char_count * 1.5 / 1000) * 0.002` 必须小于或等于当前预算 `budget`；
3. 若用户是 VIP 员工（`is_vip = True`），则预算上限放宽为 `budget * 2`。

请编写一段 Python 代码，给定 `char_count = 2500`、`budget = 0.005`、`is_vip = True`，计算最终实际可用预算 `effective_budget`、预估费用 `estimated_cost`，并输出布尔值 `can_pass`（是否允许放行）。

### 参考答案：
```python
char_count = 2500
budget = 0.005
is_vip = True

# 1. 算术运算符计算预估费用
estimated_cost = (char_count * 1.5 / 1000) * 0.002

# 2. 根据 VIP 状态计算实际可用预算（三元表达式 + 算术乘法）
effective_budget = budget * 2 if is_vip else budget

# 3. 比较运算符 + 逻辑运算符判断是否放行
can_pass = (0 < char_count <= 4000) and (estimated_cost <= effective_budget)

print(f"预估费用: ¥{estimated_cost:.6f}")      # ¥0.007500
print(f"实际预算: ¥{effective_budget:.6f}")    # ¥0.010000
print(f"是否放行: {can_pass}")                  # True
```

---

## 作业二：字符串切片与常用方法（日志与密钥脱敏）
**题目**：假设从接口日志中拿到一条原始密钥字符串：
`raw_key = "  SK-prod-9823417788-deepseek  "`
请使用字符串方法与切片语法完成以下操作：
1. 去除首尾空格，并将其全部转为小写；
2. 提取出前缀（前 7 个字符，即 `"sk-prod"`）与尾部后 4 位（`"seek"`）；
3. 拼接生成标准脱敏展示格式：`"sk-prod-****-seek"`。

### 参考答案：
```python
raw_key = "  SK-prod-9823417788-deepseek  "

# 1. strip() 去除首尾空白，lower() 转小写
cleaned_key = raw_key.strip().lower()

# 2. 使用字符串切片提取前缀与后缀
prefix = cleaned_key[:7]     # "sk-prod"
suffix = cleaned_key[-4:]    # "seek"

# 3. 拼接脱敏展示字符串
masked_key = f"{prefix}-****-{suffix}"
print(f"清洗后: {cleaned_key}")
print(f"脱敏后: {masked_key}")  # sk-prod-****-seek
```

---

## 作业三：f-string Prompt 模板工程（多字段结构化组装）
**题目**：在客服 Agent 开发中，我们需要把工单信息动态填入标准 Prompt。请定义以下变量：
- `agent_role = "星辰数科高级售后工程师"`
- `ticket_id = "TK-2026-089"`
- `customer_msg = "   我的 API 调用返回 429 限流错误，请问怎么解决？   "`
- `max_words = 120`

请先用 `strip()` 清洗 `customer_msg`，再用 **f-string 多行字符串** 渲染出包含工单号、角色、客户原话与字数限制的 Prompt，并打印该 Prompt 的总字符数。

### 参考答案：
```python
agent_role = "星辰数科高级售后工程师"
ticket_id = "TK-2026-089"
customer_msg = "   我的 API 调用返回 429 限流错误，请问怎么解决？   "
max_words = 120

clean_msg = customer_msg.strip()

prompt = f"""[工单编号] {ticket_id}
[系统角色] 你是一名{agent_role}，请以专业、耐心的语气回复客户。
[客户问题] {clean_msg}
[回复约束] 请在 {max_words} 字以内给出排查步骤。"""

print(prompt)
print(f"\nPrompt 总字符数: {len(prompt)}")
```
