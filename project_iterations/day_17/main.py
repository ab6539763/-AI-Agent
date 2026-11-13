"""Day 17 平台启动入口：企业级 Prompt 模板库与少样本工程演示 (v0.2.0-day17)"""

from __future__ import annotations

import sys
from pathlib import Path

# 支持直接 python project_iterations/day_17/main.py 启动
DAY_DIR = Path(__file__).resolve().parent
if str(DAY_DIR) not in sys.path:
    sys.path.insert(0, str(DAY_DIR))

from zhishu_agent.prompt_templates import (
    FewShotPromptBuilder,
    PromptTemplate,
    extract_json_payload,
    get_preset_template,
)


def demo_prompt_engineering() -> None:
    """演示四要素 Prompt、分隔符对比、Zero/One/Few-shot、JSON 约束与四大企业预设模板。"""
    print("=" * 64)
    print("智枢企业级智能体平台 v0.2.0-day17 · Prompt 工程基础实验室")
    print("=" * 64)

    # 1. 四要素结构化 Prompt + XML vs 三反引号分隔符
    template_backtick = PromptTemplate(
        instruction="请判断员工报销单是否符合差旅标准。",
        context="制度规定：一线城市住宿上限 600 元/晚，超标需总监特批。",
        user_input="{text}",
        output_format='输出 JSON: {"approved": bool, "reason": str}',
        delimiter_style="backtick",
        require_json=True,
    )
    print("\n[1] 三反引号分隔符 + JSON 约束渲染结果:")
    print(template_backtick.render(text="北京出差 2 晚，酒店合计 1500 元，无特批单。"))

    # 2. FewShotPromptBuilder (Zero-shot -> One-shot -> Few-shot)
    builder = FewShotPromptBuilder(
        instruction="将客户反馈归类为：Bug反馈 / 功能建议 / 资费咨询。",
        output_format='输出 JSON: {"category": str}',
        require_json=True,
    )
    print(f"\n[2] 当前模式: {builder.shot_mode}")
    builder.add_example("导出报表时页面直接白屏了", '{"category": "Bug反馈"}')
    print(f"    追加 1 条示例后模式: {builder.shot_mode}")
    builder.add_example("希望支持按部门导出月度账单", '{"category": "功能建议"}')
    print(f"    追加 2 条示例后模式: {builder.shot_mode}")
    print(builder.build("企业版续费有没有年付折扣？"))

    # 3. 企业预设模板（翻译 / 摘要 / 改写 / 分类）
    print("\n[3] 企业预设模板 - 分类 (classification):")
    cls_prompt = get_preset_template("classification").render(
        labels="产品故障, 账单发票, 账号权限, 其他",
        text="主账号无法给新入职同事分配知识库只读权限。",
    )
    print(cls_prompt)

    # 4. JSON 载荷提取演示
    mock_llm_output = '```json\n{"label": "账号权限", "confidence": 0.96, "reason": "涉及主账号分配只读权限"}\n```'
    parsed = extract_json_payload(mock_llm_output)
    print("\n[4] JSON 约束输出解析结果:", parsed)


if __name__ == "__main__":
    demo_prompt_engineering()
