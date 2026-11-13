# Day 10 课后作业与参考答案

## 作业一：扩展自定义异常类 `RateLimitError`（异常继承体系）
**题目**：在智枢平台接入生产环境大模型 API 时，最常遇到的错误之一是“触发速率限制（HTTP 429）”。请你继承 Day 10 的 `APIResponseError`：
1. 定义 `RateLimitError(APIResponseError)`，在 `__init__` 中接收 `retry_after: int = 60`（建议重试等待秒数）和可选的 `message: str = "请求过于频繁，已触发平台限流"`。
2. 调用父类 `super().__init__(message=f"{message}，请 {retry_after}s 后重试", status_code=429)`，并保存 `self.retry_after = retry_after`。
3. 验证 `isinstance(err, APIResponseError)` 和 `isinstance(err, ZhiShuError)` 均为 `True`。

### 参考答案：
```python
from zhishu_agent.exceptions import APIResponseError, ZhiShuError


class RateLimitError(APIResponseError):
    """上游大模型触发 429 速率限制时抛出的细粒度异常。"""

    def __init__(
        self,
        retry_after: int = 60,
        message: str = "请求过于频繁，已触发平台限流",
    ) -> None:
        self.retry_after = retry_after
        full_msg = f"{message}，建议 {retry_after}s 后重试"
        super().__init__(message=full_msg, status_code=429)


try:
    raise RateLimitError(retry_after=15)
except APIResponseError as exc:
    print("捕获成功:", exc)
    print("HTTP 状态码:", exc.status_code)
    print("是否为 ZhiShuError 子类:", isinstance(exc, ZhiShuError))
```

---

## 作业二：`try / except / else / finally` 实战（安全 JSON 配置读取）
**题目**：智枢平台启动时需要从字符串中解析模型 JSON 配置（如 `'{"model": "gpt-4o-mini", "temperature": 0.5}'`）。请你编写函数 `load_model_config(raw_json: str) -> dict`：
1. 在 `try` 块中使用 `json.loads(raw_json)` 解析 JSON。
2. 用 `except json.JSONDecodeError` 捕获格式错误，打印告警并返回默认配置 `{"model": "gpt-4o-mini", "temperature": 0.7}`。
3. 在 `else` 块中打印 `"JSON 配置解析成功！"` 并返回解析结果。
4. 在 `finally` 块中打印 `"配置加载流程结束（清理临时状态）"`，确保无论是否出错都会执行。

### 参考答案：
```python
import json


def load_model_config(raw_json: str) -> dict:
    """使用 try/except/else/finally 安全加载模型配置。"""
    default_cfg = {"model": "gpt-4o-mini", "temperature": 0.7}
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        print(f"[告警] JSON 解析失败 ({exc.msg})，将降级使用默认配置")
        return default_cfg
    else:
        print("[成功] JSON 配置解析成功！")
        return parsed
    finally:
        print("[收尾] 配置加载流程结束（清理临时状态）")


print("测试1（合法JSON）:", load_model_config('{"model": "qwen-plus", "temperature": 0.3}'))
print("---")
print("测试2（非法JSON）:", load_model_config("{bad json"))
```

---

## 作业三：`requirements.txt` 与虚拟环境 (`venv`) 工程化实践
**题目**：星辰数科新入职的同事拉取了 `project_iterations/day_10` 代码，需要从零搭建隔离的 Python 运行环境并安装依赖。请写出以下完整操作命令（Linux/macOS 与 Windows 均可）：
1. 在项目目录下创建名为 `.venv` 的虚拟环境。
2. 激活虚拟环境。
3. 使用国内清华镜像源安装 `requirements.txt` 中的全部依赖。
4. 将当前虚拟环境中已安装的精确包版本导出到 `requirements.lock.txt`。

### 参考答案：
```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境
# Linux / macOS:
source .venv/bin/activate
# Windows (PowerShell):
# .venv\Scripts\Activate.ps1

# 3. 使用清华镜像源批量安装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4. 导出当前环境的精确依赖版本快照
pip freeze > requirements.lock.txt
```
