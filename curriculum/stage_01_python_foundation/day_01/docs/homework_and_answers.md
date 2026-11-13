# Day 01 课后作业与参考答案

## 作业一：基础巩固题（变量与数据类型）
**题目**：请定义 4 个变量，分别代表大模型应用中的 4 个核心配置项：
1. 模型名称 `model_name`（字符串，如 `"deepseek-chat"`）
2. 最大输出 Token 数 `max_tokens`（整数，如 `2048`）
3. 采样温度 `temperature`（浮点数，如 `0.7`）
4. 是否开启流式输出 `is_stream`（布尔值，如 `True`）
并使用 `type()` 函数打印出每个变量的值和类型。

### 参考答案：
```python
model_name = "deepseek-chat"
max_tokens = 2048
temperature = 0.7
is_stream = True

print(model_name, type(model_name))      # deepseek-chat <class 'str'>
print(max_tokens, type(max_tokens))      # 2048 <class 'int'>
print(temperature, type(temperature))    # 0.7 <class 'float'>
print(is_stream, type(is_stream))        # True <class 'bool'>
```

---

## 作业二：实战编程题（API 成本估算小工具）
**题目**：某大模型 API 定价为：输入每百万 Token `1.0` 元，输出每百万 Token `2.0` 元。请编写程序，让用户输入今日预估的输入 Token 数（整数）和输出 Token 数（整数），计算并打印今日预估总费用（保留 4 位小数）。

### 参考答案：
```python
input_tokens = int(input("请输入今日输入 Token 数（例如 50000）："))
output_tokens = int(input("请输入今日输出 Token 数（例如 20000）："))

input_cost = (input_tokens / 1_000_000) * 1.0
output_cost = (output_tokens / 1_000_000) * 2.0
total_cost = input_cost + output_cost

print(f"今日预估输入费用：¥{input_cost:.4f}")
print(f"今日预估输出费用：¥{output_cost:.4f}")
print(f"今日预估总费用：¥{total_cost:.4f}")
```

---

## 作业三：思考与 Git 实操题
**题目**：在终端中执行以下 Git 命令，将今天的作业提交到你的个人 GitHub/GitLab 仓库，并解释每一条命令的作用：
1. `git status`
2. `git add .`
3. `git commit -m "feat(day-01): 完成个人信息卡片与 API 费用估算练习"`
4. `git push origin main`

### 参考解析：
- `git status`：查看工作区与暂存区当前有哪些文件被修改或新增。
- `git add .`：将当前目录下的所有改动添加到 Git 暂存区（准备提交）。
- `git commit -m "..."`：将暂存区的内容正式生成一条本地版本记录，`-m` 后紧跟符合规范的中文提交说明。
- `git push origin main`：将本地 `main` 分支的提交推送到远程仓库 `origin`。
