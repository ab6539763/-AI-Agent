"""智枢企业级智能体平台 (ZhiShu-Agent) — Day 65 毕业答辩评分引擎与问答模拟包。"""

from .defense_scorer import (
    DefenseEvaluationResult,
    DefenseRubric,
    JudgeQuestion,
    JudgeQuestionBank,
    JudgeScorecard,
    RubricDimension,
    assign_grade,
    evaluate_defense,
    export_markdown_scorecard,
)

__version__ = "1.0.0-day65"

__all__ = [
    "__version__",
    "RubricDimension",
    "DefenseRubric",
    "JudgeQuestion",
    "JudgeQuestionBank",
    "JudgeScorecard",
    "DefenseEvaluationResult",
    "assign_grade",
    "evaluate_defense",
    "export_markdown_scorecard",
]
