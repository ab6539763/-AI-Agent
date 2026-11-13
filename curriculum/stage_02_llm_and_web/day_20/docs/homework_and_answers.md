# Day 20 课后作业与参考答案

## 作业一：手算余弦相似度（Cosine Similarity Math）
**题目**：给定两个三维向量 $\vec{a} = [3, 4, 0]$ 和 $\vec{b} = [0, 4, 3]$：
1. 请写出余弦相似度的数学定义公式，并手算出 $\vec{a}$ 与 $\vec{b}$ 的余弦相似度。
2. 为什么在语义检索中通常优先使用**余弦相似度**，而不是**欧氏距离（Euclidean Distance）**？

### 参考答案：
1. **数学公式与计算过程**：
   $$\cos(\theta) = \frac{\vec{a} \cdot \vec{b}}{\|\vec{a}\| \, \|\vec{b}\|}$$
   - 点积：$\vec{a} \cdot \vec{b} = 3 \times 0 + 4 \times 4 + 0 \times 3 = 16$
   - 模长：$\|\vec{a}\| = \sqrt{3^2 + 4^2 + 0^2} = 5$，$\|\vec{b}\| = \sqrt{0^2 + 4^2 + 3^2} = 5$
   - 余弦相似度：$\cos(\theta) = \frac{16}{5 \times 5} = 0.64$
2. **原因分析**：
   - 余弦相似度衡量的是两个向量在空间中的**方向夹角**，对向量长度（文本字数长短、词频绝对大小）不敏感；而欧氏距离受向量绝对模长影响较大。在文本语义匹配中，短提问与长文档即使字数差异很大，只要语义方向一致，余弦相似度依然很高。

---

## 作业二：基于 `SemanticFAQMatcher` 构建自定义领域检索器
**题目**：智枢平台需要为 IT 运维部门新增一个专属 FAQ 检索器，包含以下 3 条知识：
- `"公司 Wi-Fi 密码是多少？"` -> `"访客请连 Xingchen-Guest，员工请使用域账号登录 Xingchen-Corp。"`
- `"电脑蓝屏怎么报修？"` -> `"请联系企业微信 IT 桌面支持机器人提交硬件故障单。"`
- `"如何申请开通 GitLab 仓库权限？"` -> `"在 OA 权限中心选择项目组并由 Tech Lead 审批。"`

请编写 Python 代码创建 `SemanticFAQMatcher` 实例、写入上述 3 条知识，并检索 `"Mac 连公司无线网密码是什么"` 的 Top-1 结果。

### 参考答案：
```python
from zhishu_agent.embeddings import FAQItem, LocalEmbeddingModel, SemanticFAQMatcher

matcher = SemanticFAQMatcher(model=LocalEmbeddingModel(dimensions=128))
matcher.add_faqs([
    FAQItem("公司 Wi-Fi 密码是多少？", "访客请连 Xingchen-Guest，员工请使用域账号登录 Xingchen-Corp。", "网络支持"),
    FAQItem("电脑蓝屏怎么报修？", "请联系企业微信 IT 桌面支持机器人提交硬件故障单。", "硬件维护"),
    FAQItem("如何申请开通 GitLab 仓库权限？", "在 OA 权限中心选择项目组并由 Tech Lead 审批。", "代码权限"),
])

results = matcher.search("Mac 连公司无线网密码是什么", top_k=1)
top = results[0]
print(f"匹配问题: {top.question} (score={top.score:.4f})")
print(f"标准答案: {top.answer}")
```

---

## 作业三：构造带高精度图像的多模态 Vision 请求载荷
**题目**：财务报销审核场景中，需要把一张 Base64 编码的发票图片和审核提示词一起发送给支持 Vision 的大模型。请使用 `build_multimodal_message` 构造一个 `detail="high"` 的消息，并将其嵌入标准 `/v1/chat/completions` 请求体字典中。

### 参考答案：
```python
from zhishu_agent.embeddings import build_multimodal_message

user_msg = build_multimodal_message(
    text="请提取图中发票的发票代码、开票日期与含税总金额，以 JSON 格式输出。",
    image_url="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
    detail="high",
)

payload = {
    "model": "gpt-4o-mini",
    "messages": [
        {"role": "system", "content": "你是星辰数科财务票据审核助手。"},
        user_msg,
    ],
    "temperature": 0.0,
}
print(payload)
```
