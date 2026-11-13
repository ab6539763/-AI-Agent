# 03. 执行：FDE 前线工程交付说明 (Executing: FDE Delivery)

## 1. 核心架构与数据流
`GovTechFDEPipeline` 将用户提问与申请人画像（`CitizenProfile`）串联至知识库与本体引擎，严格遵循以下确定性执行顺序：
1. **PII 脱敏层 (`mask_pii` / `mask_identifier`)**：对自由文本中的 18 位居民身份证、18 位统一社会信用代码（USCC）、11 位手机号、16-19 位银行卡号及邮箱执行掩码替换，并记录脱敏字段类型至审计事件。
2. **Wiki 检索层 (`GovTechLLMWiki.query`)**：采用支持中文二元组（Bigram）与英文/数字编号的确定性分词器，检索 `entities/*.md`，返回带有 `[[wiki_links]]` 与条款映射的命中结果。
3. **本体核验层 (`GovOntologyRegistry.evaluate_eligibility`)**：逐条评估 `EligibilityRule`（支持 `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `contains`），输出通过/未通过明细及精确条款编号。
4. **零幻觉拒答门控 (Refusal Gate)**：若 `wiki_hits` 均低于相关性阈值且本体无任何匹配项目，立即返回 `status="refused"`，不输出任何无依据补贴承诺。
5. **HITL 签批与审计 (`GovAction` + `AuditEvent`)**：对符合条件且触发人工复核阈值的项目创建 `pending_approval` 动作，经 `/api/v1/actions/approve` 由经办人（`officer_id`）签批后落盘审计记录。

## 2. API 接口契约
| 方法与路径 | 用途 | 关键返回 |
|---|---|---|
| `GET /health` / `GET /ready` | 存活与就绪探针 | `status`, 实体计数 |
| `GET /metrics` | 运行指标 | 请求数、拒答数、HITL 待批/已批数 |
| `POST /api/v1/wiki/ingest` | 写入政策 Markdown 实体 | `doc_id`, `path`, `total_entities` |
| `POST /api/v1/wiki/lint` | 知识库健康巡检 | `expired_policies`, `conflicting_thresholds`, `orphan_rules` |
| `POST /api/v1/ontology/eligibility` | 多规则资格评估 | `eligible`, `estimated_subsidy`, `exact_clauses` |
| `POST /api/v1/policy/ask` | 端到端政策问答与工单触发 | `status`, `clause_citations`, `pending_action` |
| `POST /api/v1/actions/approve` | 经办人 HITL 签批 | `status` (`approved` / `rejected`), `approved_by` |
