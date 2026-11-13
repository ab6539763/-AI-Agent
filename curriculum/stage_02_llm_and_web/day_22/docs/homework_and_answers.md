# Day 22 课后作业与参考答案

## 作业一：编写语义化 HTML5 聊天界面骨架
**题目**：请你为一个企业级智能体对话台编写最小化的语义化 HTML5 结构，要求：
1. 声明 `UTF-8` 字符集与移动端 `viewport` 适配，页面标题为 `智枢企业级智能体对话台`。
2. 包含对话消息容器（`id="chat-messages"`）、提交表单（`id="chat-form"`）、文本输入框（`id="user-input"`）与发送按钮（`id="send-btn"`）。

### 参考答案：
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>智枢企业级智能体对话台</title>
</head>
<body>
  <main class="chat-app">
    <header class="chat-header">智枢企业级智能体对话台</header>
    <section id="chat-messages" class="chat-messages" aria-live="polite"></section>
    <form id="chat-form" class="chat-form">
      <textarea id="user-input" rows="1" placeholder="请输入您的问题..." required></textarea>
      <button id="send-btn" type="submit">发送</button>
    </form>
  </main>
</body>
</html>
```

---

## 作业二：使用 CSS Flexbox 实现左右对齐聊天气泡
**题目**：在现代 Web Chat UI 中，消息列表容器 `.chat-messages` 通常是一个纵向滚动的 Flex 容器。请你编写 CSS 规则，实现以下视觉效果：
1. `.chat-messages` 纵向排列所有消息并自动占据剩余高度（`flex: 1`）且支持垂直滚动。
2. 用户消息 `.message.user` 靠右对齐（蓝色背景 `#2563eb`、白色文字），助手消息 `.message.assistant` 靠左对齐（白色背景、浅灰边框）。
3. 气泡最大宽度不超过容器的 `78%`，防止长文本撑满整行。

### 参考答案：
```css
.chat-messages {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  overflow-y: auto;
  background: #f8fafc;
}

.message {
  display: flex;
  flex-direction: column;
  max-width: 78%;
}

.message.user {
  align-self: flex-end;
  align-items: flex-end;
}

.message.assistant {
  align-self: flex-start;
  align-items: flex-start;
}

.message.user .bubble {
  background: #2563eb;
  color: #ffffff;
  border-radius: 14px 14px 4px 14px;
  padding: 12px 16px;
}

.message.assistant .bubble {
  background: #ffffff;
  color: #0f172a;
  border: 1px solid #e2e8f0;
  border-radius: 14px 14px 14px 4px;
  padding: 12px 16px;
}
```

---

## 作业三：使用原生 JS `fetch()` 发送 POST JSON 请求并处理异常
**题目**：请编写一个异步函数 `sendChatMessage(message)`，完成以下逻辑：
1. 使用 `fetch("/api/v1/chat", ...)` 发送 `POST` 请求，请求头包含 `"Content-Type": "application/json"`，请求体为 `JSON.stringify({ message })`。
2. 校验 `response.ok`：若状态码非 2xx，主动抛出 `Error`；若成功则解析 `await response.json()` 并返回 `data.reply`。
3. 使用 `try / catch / finally` 捕获网络或服务异常，并在 `finally` 中恢复发送按钮 `sendBtn.disabled = false`。

### 参考答案：
```javascript
async function sendChatMessage(message) {
  const sendBtn = document.getElementById("send-btn");
  sendBtn.disabled = true;

  try {
    const response = await fetch("/api/v1/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ message })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    return data.reply;
  } catch (error) {
    console.error("请求智能体接口失败:", error);
    return `请求失败（${error.message}），请确认后端 API 已启动。`;
  } finally {
    sendBtn.disabled = false;
  }
}
```
