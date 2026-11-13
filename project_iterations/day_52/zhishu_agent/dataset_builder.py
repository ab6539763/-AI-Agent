"""智枢平台 Day 52 核心模块：微调指令数据集构建流水线 (v0.5.0-day52).

涵盖：
1. Alpaca / ShareGPT 双格式 Pydantic v2 数据模型与双向无损转换；
2. 文本空白规范化、最小长度过滤、SHA-256 精确去重与字符 N-gram Jaccard 近似去重；
3. Self-Instruct 风格垂直领域（企业级智能客服）合成数据集生成器；
4. UTF-8 JSONL 导入/导出与数据集统计分析。
"""

from __future__ import annotations

import hashlib
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# 1. Pydantic v2 数据模型定义：Alpaca & ShareGPT
# ---------------------------------------------------------------------------


class AlpacaSample(BaseModel):
    """Stanford Alpaca 格式单轮指令微调样本."""

    instruction: str = Field(..., min_length=1, description="任务指令或用户问题")
    input: str = Field(default="", description="可选的上下文或附加输入")
    output: str = Field(..., min_length=1, description="期望模型生成的标准回答")
    system: str | None = Field(default=None, description="可选的系统提示词")
    category: str = Field(default="general", description="业务场景分类标签")

    @field_validator("instruction", "output")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("instruction 与 output 不能为空白字符串")
        return value


class ShareGPTMessage(BaseModel):
    """ShareGPT 对话轮次消息（支持 `from` 别名序列化）."""

    model_config = ConfigDict(populate_by_name=True)

    from_: Literal["system", "human", "gpt"] = Field(
        ..., alias="from", description="消息角色: system / human / gpt"
    )
    value: str = Field(..., min_length=1, description="消息文本内容")

    @field_validator("value")
    @classmethod
    def _value_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("消息 value 不能为空白字符串")
        return v


class ShareGPTSample(BaseModel):
    """ShareGPT 多轮/单轮对话微调样本."""

    conversations: list[ShareGPTMessage] = Field(
        ..., min_length=2, description="按对话顺序排列的消息列表"
    )
    system: str | None = Field(default=None, description="可选的系统提示词")
    category: str = Field(default="general", description="业务场景分类标签")

    @field_validator("conversations")
    @classmethod
    def _must_have_human_and_gpt(
        cls, messages: list[ShareGPTMessage]
    ) -> list[ShareGPTMessage]:
        roles = {msg.from_ for msg in messages}
        if "human" not in roles or "gpt" not in roles:
            raise ValueError("ShareGPT conversations 至少需包含 human 与 gpt 各一条消息")
        return messages


# ---------------------------------------------------------------------------
# 2. Alpaca <-> ShareGPT 双向转换器
# ---------------------------------------------------------------------------

_INPUT_SEPARATOR = "\n\n输入："


def alpaca_to_sharegpt(
    sample: AlpacaSample, *, system_prompt: str | None = None
) -> ShareGPTSample:
    """将 AlpacaSample 转换为 ShareGPTSample，保留 system 与 category 元信息."""
    effective_system = system_prompt if system_prompt is not None else sample.system
    human_value = (
        f"{sample.instruction}{_INPUT_SEPARATOR}{sample.input}"
        if sample.input.strip()
        else sample.instruction
    )
    return ShareGPTSample(
        conversations=[
            ShareGPTMessage(from_="human", value=human_value),
            ShareGPTMessage(from_="gpt", value=sample.output),
        ],
        system=effective_system,
        category=sample.category,
    )


def sharegpt_to_alpaca(sample: ShareGPTSample) -> AlpacaSample:
    """将 ShareGPTSample 转换为 AlpacaSample（提取首个 human -> gpt 问答对）."""
    system_msg = sample.system
    human_text: str | None = None
    gpt_text: str | None = None

    for msg in sample.conversations:
        if msg.from_ == "system" and system_msg is None:
            system_msg = msg.value
        elif msg.from_ == "human" and human_text is None:
            human_text = msg.value
        elif msg.from_ == "gpt" and human_text is not None and gpt_text is None:
            gpt_text = msg.value
            break

    if human_text is None or gpt_text is None:
        raise ValueError("ShareGPTSample 缺少有效的 human -> gpt 对话对")

    if _INPUT_SEPARATOR in human_text:
        instruction, input_text = human_text.split(_INPUT_SEPARATOR, maxsplit=1)
    else:
        instruction, input_text = human_text, ""

    return AlpacaSample(
        instruction=instruction,
        input=input_text,
        output=gpt_text,
        system=system_msg,
        category=sample.category,
    )


# ---------------------------------------------------------------------------
# 3. 数据清洗、过滤与去重（Exact Hash + N-gram Jaccard）
# ---------------------------------------------------------------------------

_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200d\ufeff]")
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def normalize_whitespace(text: str) -> str:
    """规范化文本空白字符：去除零宽字符、折叠多余空格与连续空行."""
    cleaned = _ZERO_WIDTH_RE.sub("", text)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_MULTI_SPACE_RE.sub(" ", line).strip() for line in cleaned.split("\n")]
    cleaned = "\n".join(lines).strip()
    return _MULTI_NEWLINE_RE.sub("\n\n", cleaned)


def char_ngrams(text: str, n: int = 3) -> set[str]:
    """提取字符级 N-gram 集合（兼容中文无空格分词场景）."""
    compact = re.sub(r"\s+", "", text.lower())
    if not compact:
        return set()
    if len(compact) <= n:
        return {compact}
    return {compact[i : i + n] for i in range(len(compact) - n + 1)}


def jaccard_similarity(text_a: str, text_b: str, ngram_size: int = 3) -> float:
    """计算两段文本基于字符 N-gram 的 Jaccard 相似度 [0.0, 1.0]."""
    set_a = char_ngrams(text_a, n=ngram_size)
    set_b = char_ngrams(text_b, n=ngram_size)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union


class DeduplicationStats(BaseModel):
    """清洗与去重流水线统计报告."""

    input_count: int
    filtered_short_count: int
    exact_duplicate_count: int
    near_duplicate_count: int
    output_count: int


def clean_and_deduplicate_with_stats(
    samples: Sequence[AlpacaSample],
    *,
    min_instruction_len: int = 4,
    min_output_len: int = 8,
    jaccard_threshold: float = 0.85,
    ngram_size: int = 3,
) -> tuple[list[AlpacaSample], DeduplicationStats]:
    """对指令样本执行空白规范化、最小长度过滤、SHA-256 精确去重与 Jaccard 近似去重."""
    if not 0.0 < jaccard_threshold <= 1.0:
        raise ValueError("jaccard_threshold 必须在 (0.0, 1.0] 区间内")

    seen_hashes: set[str] = set()
    kept_samples: list[AlpacaSample] = []
    kept_ngrams: list[set[str]] = []
    ngram_index: dict[str, list[int]] = defaultdict(list)

    filtered_short = 0
    exact_dups = 0
    near_dups = 0

    for raw in samples:
        norm_inst = normalize_whitespace(raw.instruction)
        norm_inp = normalize_whitespace(raw.input)
        norm_out = normalize_whitespace(raw.output)
        norm_sys = normalize_whitespace(raw.system) if raw.system is not None else None

        if len(norm_inst) < min_instruction_len or len(norm_out) < min_output_len:
            filtered_short += 1
            continue

        # 1) SHA-256 精确去重（针对规范化后的 instruction + input）
        canonical_key = f"{norm_inst}\n||{norm_inp}".encode("utf-8")
        digest = hashlib.sha256(canonical_key).hexdigest()
        if digest in seen_hashes:
            exact_dups += 1
            continue

        # 2) 基于倒排索引加速的 N-gram Jaccard 近似去重
        query_text = f"{norm_inst} {norm_inp}".strip()
        q_grams = char_ngrams(query_text, n=ngram_size)

        candidate_indices: set[int] = set()
        for gram in q_grams:
            candidate_indices.update(ngram_index.get(gram, ()))

        is_near_dup = False
        for idx in candidate_indices:
            other_grams = kept_ngrams[idx]
            union_len = len(q_grams | other_grams)
            if union_len == 0:
                continue
            sim = len(q_grams & other_grams) / union_len
            if sim >= jaccard_threshold:
                is_near_dup = True
                break

        if is_near_dup:
            near_dups += 1
            continue

        seen_hashes.add(digest)
        sample_idx = len(kept_samples)
        kept_samples.append(
            AlpacaSample(
                instruction=norm_inst,
                input=norm_inp,
                output=norm_out,
                system=norm_sys,
                category=raw.category,
            )
        )
        kept_ngrams.append(q_grams)
        for gram in q_grams:
            ngram_index[gram].append(sample_idx)

    stats = DeduplicationStats(
        input_count=len(samples),
        filtered_short_count=filtered_short,
        exact_duplicate_count=exact_dups,
        near_duplicate_count=near_dups,
        output_count=len(kept_samples),
    )
    return kept_samples, stats


def clean_and_deduplicate(
    samples: Sequence[AlpacaSample],
    *,
    min_instruction_len: int = 4,
    min_output_len: int = 8,
    jaccard_threshold: float = 0.85,
    ngram_size: int = 3,
) -> list[AlpacaSample]:
    """清洗并去重指令样本列表，返回高质量样本集合."""
    cleaned, _ = clean_and_deduplicate_with_stats(
        samples,
        min_instruction_len=min_instruction_len,
        min_output_len=min_output_len,
        jaccard_threshold=jaccard_threshold,
        ngram_size=ngram_size,
    )
    return cleaned


# ---------------------------------------------------------------------------
# 4. Self-Instruct 垂直领域合成数据集生成器（企业级智能客服 500 条）
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = "你是星辰数科「智枢」企业级智能客服助手，请结合业务规则给出准确、礼貌、可执行的解答。"

_PERSONA_PREFIXES: list[str] = [
    "你好，麻烦帮忙核实一下：",
    "急！请问现在这个情况怎么处理：",
    "我是企业采购负责人，想确认一下：",
    "抱歉打扰，我在 App 上操作遇到疑问：",
    "请帮我查一下后台记录并给出处理方案：",
    "我想了解贵司最新的服务政策：",
    "刚才系统提示操作失败，请协助排查：",
    "帮家里的老人问一下，不太懂线上流程：",
    "我需要整理一份内部报销/对账说明，请问：",
    "如果遇到这种特殊情况，规则上是怎么规定的？",
]

_CITIES = ["北京", "上海", "深圳", "杭州", "成都", "武汉", "南京", "苏州", "西安", "广州"]
_COURIERS = ["顺丰速运", "京东物流", "中通快递", "圆通速递", "EMS特快"]
_PRODUCTS = [
    "智枢企业版年度授权",
    "智能会议平板 Pro 75寸",
    "高拍仪扫描终端 S20",
    "企业级 Wi-Fi 6 路由器",
    "云端算力资源包 5000点",
    "AI 语音降噪耳麦",
    "移动办公便携显示器",
    "RFID 智能资产标签套装",
]
_PAY_CHANNELS = ["企业网银转账", "支付宝企业版", "微信支付", "对公银行汇款", "信用卡分期"]


_DEPARTMENTS = ["华东研发中心", "华南销售部", "西南交付组", "北京总部行政", "财务共享中心", "供应链运营部", "市场品牌部", "信息安全组", "海外业务部", "客户成功部"]
_TIME_WINDOWS = ["本周五下班前", "下周一上午", "月底财务关账前", "Q3 季度审计前", "明天下午 15:00 前", "下个工作日", "本周三例会前", "48 小时内", "本月 25 号前", "国庆节前"]
_EXTRA_CONSTRAINTS = [
    "请同步说明是否需要走 OA 审批流。",
    "若涉及额外费用，请一并列出收费明细。",
    "我们需要将处理结果归档至年度采购台账。",
    "希望给出手机端与网页端两种操作路径。",
    "请明确该业务的 SLA 承诺处理时效。",
    "如果遇到节假日顺延，规则如何计算？",
    "请确认是否需要加盖公司电子签章。",
    "若由第三方代理经办，需要补充哪些授权材料？",
    "请告知异常情况下的升级投诉渠道。",
    "希望提供可直接转发给业务部门的标准回复话术。",
]


def _build_order_logistics_sample(idx: int, rng: random.Random) -> AlpacaSample:
    city = _CITIES[idx % len(_CITIES)]
    courier = _COURIERS[(idx // 2) % len(_COURIERS)]
    product = _PRODUCTS[(idx // 3) % len(_PRODUCTS)]
    dept = _DEPARTMENTS[(idx // 7) % len(_DEPARTMENTS)]
    tw = _TIME_WINDOWS[(idx // 5) % len(_TIME_WINDOWS)]
    constraint = _EXTRA_CONSTRAINTS[(idx // 10) % len(_EXTRA_CONSTRAINTS)]
    order_id = f"ZS{20260000 + idx * 17}"
    days = 2 + (idx % 5)
    sub_type = idx % 10
    prefix = _PERSONA_PREFIXES[(idx // 10) % len(_PERSONA_PREFIXES)]

    scenarios = [
        (
            f"{prefix}{dept}的订单 {order_id} 购买了「{product}」，由{courier}发往{city}已滞留 {days} 天，需要在{tw}交付，怎么加急？{constraint}",
            f"订单号：{order_id} | 部门：{dept} | 承运商：{courier} | 目的地：{city} | 滞留：{days}天",
            f"您好！已记录{dept}的加急诉求（订单 {order_id}，商品「{product}」）。{courier}发往{city}的快件若超过 48 小时未更新轨迹，我们将为您触发物流异常工单：1）客服专员将在 2 小时内联系{courier}网点核实中转扫描状态；2）若确认丢失或延误超 72 小时，可为您免费补发新件或办理全额退款，力争在{tw}前妥善解决。",
        ),
        (
            f"{prefix}{dept}刚下单了「{product}」（订单 {order_id}），误填为{city}旧办公区，要求在{tw}前改派新址，未发货能自助修改吗？{constraint}",
            f"订单号：{order_id} | 部门：{dept} | 当前状态：待仓库拣货",
            f"您好！订单 {order_id} 目前处于「待仓库拣货」阶段，支持自助修改一次收货地址。请进入「我的订单 -> 订单详情 -> 修改地址」完成变更；如页面按钮已置灰，请立即提供新的{city}详细地址与联系人电话，我们将在出库拦截窗口期内为您人工改派。",
        ),
        (
            f"{prefix}{dept}批量采购「{product}」（单号 {order_id}），需拆分成发往{city}和上海两个分公司的包裹并在{tw}送达，运费怎么算？{constraint}",
            f"批次号：{order_id} | 申请部门：{dept} | 拆分地：{city} / 上海",
            f"您好！企业批量订单支持「多地址拆单发货」。针对「{product}」，单笔满 2000 元即可免除首重基础运费；拆单后发往{city}与上海的子包裹将分别生成独立运单号并同步至您的对账中心，偏远超重部分按协议价 8 折结算。",
        ),
        (
            f"{prefix}物流显示{courier}已签收{dept}的订单 {order_id}，但我和{city}前台同事都没收到「{product}」，需在{tw}核清，怎么办？{constraint}",
            f"运单状态：已签收（代收点） | 订单号：{order_id} | 部门：{dept}",
            f"非常抱歉给您带来困扰！遇到「虚假签收」请按以下步骤处理：1）先核实{courier}是否投递至{city}所在园区驿站或智能快递柜；2）若确认未收到，请在 24 小时内点击订单页「未收到货申诉」，我们将在 4 小时内调取派件员签收底单与定位记录，核实无误后优先为您先行赔付或重发。",
        ),
        (
            f"{prefix}{dept}计划在{tw}于{city}机房部署「{product}」，希望{courier}按指定时段上门派送（参考单 {order_id}），支持预约定时达吗？{constraint}",
            f"参考单号：{order_id} | 部署城市：{city} | 承运商：{courier}",
            f"您好！发往{city}核心城区的订单支持「预约定时达」服务。若选用{courier}特快专递，您可以在下单备注栏或订单详情页选择「工作日/周末指定时段派送」，定时达附加费按单笔 15 元计收，企业 VIP 客户每月享有 3 次免费定时达权益。",
        ),
        (
            f"{prefix}{dept}的订单 {order_id}（「{product}」）在{city}派送时外包装箱被雨水浸湿，当场拒收需要承担退回运费吗？{constraint}",
            f"订单号：{order_id} | 异常类型：外包装破损/浸湿 | 承运商：{courier}",
            f"您好！因{courier}运输原因导致「{product}」外包装破损或浸湿，您有权当场拍照留证并直接拒收，全程退回运费由平台与承运商承担，无需您支付任何费用。系统收到拒收回调后，将在 1 个工作日内为您重新安排全新批次发货。",
        ),
        (
            f"{prefix}{dept}从保税仓发往{city}的「{product}」（单号 {order_id}）提示清关查验中，会影响{tw}项目交付吗？一般卡多久？{constraint}",
            f"订单号：{order_id} | 物流节点：海关例行查验 | 目的地：{city}",
            f"您好！跨境或保税仓商品进入海关例行查验属于正常监管流程，通常需要 1 至 3 个工作日放行。请确保下单预留的收件人姓名与身份证号一致，清关完成后将由{courier}第一时间转运至{city}。",
        ),
        (
            f"{prefix}{dept}在{city}急用「{product}」（意向单 {order_id}），希望{tw}拿到，能选本地仓闪送或线下门店自提吗？{constraint}",
            "",
            f"您好！若{city}本地前置仓有「{product}」现货，结算页会自动展示「同城 2 小时达」与「门店自提」两个选项。选择自提后凭取货码与本人身份证件到店核销，可立减物流费并支持现场验机。",
        ),
        (
            f"{prefix}{dept}同时下了 3 笔发往{city}的「{product}」订单（含 {order_id}），系统会自动合并成一个{courier}包裹发出吗？{constraint}",
            "",
            f"您好！为保障不同批次资产清点与发票对应关系，系统默认按订单号独立打包发货，不会私自合单。如需合单以减少{city}仓库收货频次，请在付款后 30 分钟内联系在线客服登记「合并发货申请」。",
        ),
        (
            f"{prefix}{dept}的海外分支机构想采购「{product}」（询价单 {order_id}），希望{tw}安排发出，支持国际快递直邮吗？{constraint}",
            f"目的区域：亚太区海外办公室 | 采购数量：{2 + (idx % 4)} 台 | 部门：{dept}",
            f"您好！企业大宗硬件支持国际商业快递（DHL/FedEx）直邮，需由您的专属客户经理协助评估目的地海关准入资质与关税条款（DDP/DAP）。已为您标记需求，工作日 2 小时内将有国际物流专员与您对接报价单。",
        ),
    ]
    inst, inp, out = scenarios[sub_type]
    return AlpacaSample(
        instruction=inst,
        input=inp,
        output=out,
        system=_SYSTEM_PROMPT,
        category="order_logistics",
    )


def _build_refund_aftersales_sample(idx: int, rng: random.Random) -> AlpacaSample:
    product = _PRODUCTS[idx % len(_PRODUCTS)]
    pay = _PAY_CHANNELS[(idx // 2) % len(_PAY_CHANNELS)]
    dept = _DEPARTMENTS[(idx // 3) % len(_DEPARTMENTS)]
    tw = _TIME_WINDOWS[(idx // 5) % len(_TIME_WINDOWS)]
    constraint = _EXTRA_CONSTRAINTS[(idx // 10) % len(_EXTRA_CONSTRAINTS)]
    amount = 299 + (idx % 12) * 150
    order_id = f"RF{20261000 + idx * 13}"
    sub_type = idx % 10
    prefix = _PERSONA_PREFIXES[(idx // 10) % len(_PERSONA_PREFIXES)]

    scenarios = [
        (
            f"{prefix}{dept}通过{pay}购买的「{product}」（{amount} 元，单号 {order_id}）刚申请七天无理由退货，{tw}能原路退回吗？{constraint}",
            f"售后单号：{order_id} | 支付渠道：{pay} | 退款金额：{amount}元",
            f"您好！售后单 {order_id} 在仓库签收并质检通过后，系统将立即发起原路退款（{amount} 元）。通过{pay}支付的款项通常在 1-3 个工作日内到账，信用卡或对公汇款可能因银行清算周期顺延至 3-5 个工作日。",
        ),
        (
            f"{prefix}{dept}拆封通电测试过「{product}」（单号 {order_id}，{amount} 元），发现接口与旧设备不兼容，还能退换货吗？{constraint}",
            "",
            f"您好！「{product}」支持「7 天无理由退换货」，前提是商品外观无划痕、配件与说明书齐全且不影响二次销售。对于软件授权类产品（激活码已兑换绑定），一经激活则不支持无理由退货；硬件设备您可先联系技术支持确认是否可通过转接头兼容。",
        ),
        (
            f"{prefix}{dept}收到「{product}」（单号 {order_id}）发现机身磕碰且无法开机，要求{tw}换新，需要我先垫付寄回运费吗？{constraint}",
            f"售后单号：{order_id} | 故障类型：DOA 开箱即损 | 支付：{pay}",
            f"您好！开箱即损（DOA）属于质量问题售后，您无需承担任何运费。提交售后单 {order_id} 并上传开箱视频/照片后，系统将自动派发「上门取件免运费」服务，物流小哥取件的同时可为您触发「极速换新」优先发出良品。",
        ),
        (
            f"{prefix}{dept}买「{product}」（单号 {order_id}）用了 100 元满减券和 500 积分，实付 {amount} 元，部分退款时券和积分怎么退？{constraint}",
            f"订单实付：{amount}元 | 抵扣：满减券100元 + 500积分",
            f"您好！售后退款按「实付比例」拆分返还：1）使用的 500 积分将在退款完成后 24 小时内原额退回账户（有效期不变）；2）整单全额退货时，未过期的满减优惠券将自动退回卡包；若为部分退货，优惠券按分摊比例核销，不予退回。",
        ),
        (
            f"{prefix}{dept}的「{product}」（单号 {order_id}）使用 8 个月后频繁自动重启，还在质保期内吗？{tw}能修好吗？{constraint}",
            "",
            f"您好！智枢全系硬件标配「1 年免费质保」（部分企业级设备享 3 年质保）。使用 8 个月仍在免费质保期内，请您在「售后服务 -> 申请返修」提交设备 SN 码。售后中心收到机器后将在 5 个工作日内完成检测维修并免费寄回；若无法修复将直接为您更换同型号良品。",
        ),
        (
            f"{prefix}{dept}单号 {order_id} 退款提示「原{pay}绑定卡已注销导致退款失败」，{amount} 元货款怎么在{tw}前领回？{constraint}",
            f"售后单号：{order_id} | 异常原因：原卡注销 | 金额：{amount}元",
            f"您好！若原{pay}绑定银行卡已注销，款项会被银行退回至平台待处理账户。请您在「售后详情页 -> 更换收款账户」上传本人身份证正反面及名下有效一类银行卡信息，财务核验后将在 3 个工作日内为您手工打款 {amount} 元。",
        ),
        (
            f"{prefix}{dept}大促买的「{product}」（单号 {order_id}，{amount} 元）刚签收 3 天就官降 200 元，能在{tw}前申请价保吗？{constraint}",
            "",
            f"您好！自订单签收之日起 7 天内，若同规格、同配置的官方自营「{product}」发生公开直降，您可以进入「我的订单 -> 一键价保」申请退还差价。注意：限时秒杀、企业协议特价及叠加特定银行立减的活动不参与价保。",
        ),
        (
            f"{prefix}{dept}买错了「{product}」规格（单号 {order_id}），想换高配并补 {amount} 元差价，为什么只有「退货退款」按钮？{constraint}",
            "",
            f"您好！标准换货仅支持「同商品同价位不同颜色/尺码」。如需跨型号升级或更换高配版本（涉及补差价），建议您直接申请「退货退款」，同时重新下单所需型号，这样可最快锁定新货库存并避免差价结算延迟。",
        ),
        (
            f"{prefix}{dept}采购的「{product}」（单号 {order_id}）需要上门拆机检测并出具官方故障鉴定报告用于核销，{tw}能办吗？{constraint}",
            f"售后单号：{order_id} | 需求：故障鉴定报告 | 部门：{dept}",
            f"您好！针对企业客户，我们支持提供加盖售后服务专用章的《设备故障检测鉴定报告》。请在提交返修单 {order_id} 时勾选「需要书面检测报告」，工程师完成测试后将随设备或通过电子签章邮件发送给您。",
        ),
        (
            f"{prefix}{dept}的退货包裹（单号 {order_id}，{amount} 元）误用平邮寄出忘了填单号，超时关闭售后单了怎么在{tw}恢复？{constraint}",
            f"售后单号：{order_id} | 超时状态：已自动关闭",
            f"您好！请勿担心，只要商品确实在退货有效期内寄出，您可以提供平邮或快递底单照片以及收寄双方电话，联系人工客服为您「重开售后通道」并手动补录物流单号，核实仓库签收后即可继续办理 {amount} 元退款。",
        ),
    ]
    inst, inp, out = scenarios[sub_type]
    return AlpacaSample(
        instruction=inst,
        input=inp,
        output=out,
        system=_SYSTEM_PROMPT,
        category="refund_aftersales",
    )


def _build_account_security_sample(idx: int, rng: random.Random) -> AlpacaSample:
    city = _CITIES[idx % len(_CITIES)]
    dept = _DEPARTMENTS[(idx // 2) % len(_DEPARTMENTS)]
    tw = _TIME_WINDOWS[(idx // 4) % len(_TIME_WINDOWS)]
    constraint = _EXTRA_CONSTRAINTS[(idx // 10) % len(_EXTRA_CONSTRAINTS)]
    sub_type = idx % 10
    prefix = _PERSONA_PREFIXES[(idx // 10) % len(_PERSONA_PREFIXES)]
    uid = f"U{88000 + idx * 7}"

    scenarios = [
        (
            f"{prefix}{dept}员工账号 {uid} 原绑定手机号已停用，收不到验证码，怎么在{tw}前换绑{city}新手机号？{constraint}",
            f"账号ID：{uid} | 部门：{dept} | 异常场景：原手机号停用",
            f"您好！若原手机号已注销，请点击登录页下方的「无法接收验证码 -> 账号申诉换绑」。系统将引导您完成：1）输入历史常用登录地（如{city}）与最近一笔订单号；2）进行人脸活体核身或上传身份证件照片。审核通过后（通常 30 分钟内）即可绑定新手机号。",
        ),
        (
            f"{prefix}收到安全告警，{dept}账号 {uid} 在{city}异地登录并尝试改支付密码，如何在{tw}前紧急止损？{constraint}",
            f"账号ID：{uid} | 告警地点：{city} | 风险等级：高",
            f"请立即执行紧急止损三步：1）点击告警短信中的「非本人操作，一键冻结」或前往「安全中心 -> 应急冻结」锁定账号；2）踢出所有已登录设备会话；3）解冻后立即修改高强度独立密码并开启双因素认证（MFA/TOTP）。",
        ),
        (
            f"{prefix}{dept}主账号 {uid} 人员离职交接，怎么把企业实名认证与超管权限在{tw}前安全移交到{city}新同事？{constraint}",
            f"原超管：{uid} | 移交部门：{dept} | 地点：{city}",
            f"您好！为保障企业资产安全，超管权限移交需走「企业主体变更工单」：请由原超管在「企业控制台 -> 组织安全 -> 超管转让」发起申请，并上传加盖公司公章的《管理员授权委托书》及新旧管理员身份证正反面，法务审核通过后 1 个工作日内完成无缝交接。",
        ),
        (
            f"{prefix}我在{city}出差时连续输错 5 次密码，{dept}账号 {uid} 被锁定 2 小时，有办法在{tw}前提前解锁吗？{constraint}",
            f"账号ID：{uid} | 状态：密码错误次数超限锁定",
            f"您好！触发风控防暴力破解锁定后，支持通过「忘记密码 -> 短信验证码 + 实名身份核验」直接重置密码并同步解除锁定，无需干等 2 小时冷却期。",
        ),
        (
            f"{prefix}{dept}想彻底注销测试账号 {uid}，需要在{tw}前满足哪些条件？{city}节点数据会保留多久？{constraint}",
            "",
            f"您好！账号注销需同时满足：1）无进行中的订单与售后维权；2）账户余额、未结佣金及代金券已清零；3）近 15 天内无修改密码或换绑手机等敏感操作。注销提交后有 7 天冷静期，期满后您的个人隐私数据将按《个人信息保护法》彻底匿名化清除且不可恢复。",
        ),
        (
            f"{prefix}{dept}（{city}办公区）计划在{tw}接入 SSO 单点登录（OIDC/SAML 2.0）管理 {uid} 等员工账号，如何配置？{constraint}",
            "",
            f"您好！智枢企业版完全支持标准 SAML 2.0 与 OIDC 单点登录。请企业管理员进入「安全中心 -> 身份提供商（IdP）集成」，上传贵司 IdP 元数据 XML 并配置回调 URL 与域验证 TXT 记录，测试连通后即可开启全员强制 SSO 登录。",
        ),
        (
            f"{prefix}{dept}账号 {uid} 在{city}做实名认证时一直提示「身份证信息与公安库校验不一致」，{tw}要用怎么排查？{constraint}",
            f"账号ID：{uid} | 报错码：AUTH_ID_MISMATCH",
            f"您好！出现 AUTH_ID_MISMATCH 常见原因有三类：1）近期刚办理过户籍迁徙或姓名变更，公安库同步存在 3-7 天延迟；2）拍照反光导致身份证号末位 X 识别错误；3）证件已过有效期。建议在光线均匀处重新拍摄并手动核对识别字段，或转人工复核通道提交清晰原件照片。",
        ),
        (
            f"{prefix}如何给{dept}的子账号 {uid} 分配「只读权限」，让{city}财务同事只能看账单不能下单？{constraint}",
            "",
            f"您好！您可以在「企业控制台 -> 角色与权限（RBAC）」中新建自定义角色，仅勾选 `billing:read` 与 `invoice:export` 两项权限，取消 `order:write` 与 `security:manage`，随后将该角色绑定至财务同事的子账号即可实现最小权限隔离。",
        ),
        (
            f"{prefix}{dept}账号 {uid} 的 AccessKey 不小心提交到了公开仓库，如何在{tw}前完成应急轮换与审计？{constraint}",
            f"账号ID：{uid} | 安全事件：AK/SK 泄露 | 部门：{dept}",
            f"高危告警！请立即前往「开发者中心 -> 密钥管理」点击「禁用并销毁」已泄露的 AccessKey，随后生成一组全新的密钥并更新至环境变量或密钥托管服务（KMS），同时排查近期的 API 调用审计日志确认是否存在异常扣费或越权访问。",
        ),
        (
            f"{prefix}{dept}员工账号 {uid} 开启 2FA 后在{city}遗失旧手机，动态口令没了，怎么在{tw}前恢复登录？{constraint}",
            "",
            f"您好！您在开启 2FA 时系统曾生成过一组「10 位一次性备用恢复码」，使用任意一条备用码即可绕过动态口令登录并重新绑定新设备；若备用码也已遗失，请点击「2FA 丢失申诉」，通过绑定的实名手机号与人脸核身即可在 24 小时内重置双因素认证。",
        ),
    ]
    inst, inp, out = scenarios[sub_type]
    return AlpacaSample(
        instruction=inst,
        input=inp,
        output=out,
        system=_SYSTEM_PROMPT,
        category="account_security",
    )


def _build_invoice_billing_sample(idx: int, rng: random.Random) -> AlpacaSample:
    amount = 1200 + (idx % 15) * 350
    dept = _DEPARTMENTS[idx % len(_DEPARTMENTS)]
    tw = _TIME_WINDOWS[(idx // 3) % len(_TIME_WINDOWS)]
    pay = _PAY_CHANNELS[(idx // 4) % len(_PAY_CHANNELS)]
    constraint = _EXTRA_CONSTRAINTS[(idx // 10) % len(_EXTRA_CONSTRAINTS)]
    order_id = f"INV{20263000 + idx * 19}"
    sub_type = idx % 10
    prefix = _PERSONA_PREFIXES[(idx // 10) % len(_PERSONA_PREFIXES)]

    scenarios = [
        (
            f"{prefix}{dept}的订单 {order_id}（{amount} 元）需要在{tw}前报销，能开具 13% 税率的数电增值税专用发票吗？{constraint}",
            f"订单号：{order_id} | 金额：{amount}元 | 发票类型：数电专票",
            f"您好！硬件设备类商品支持开具 13% 税率的全电（数电）增值税专用发票，软件及云服务类支持 6% 税率数电专票。请在「发票中心 -> 申请开票」填写贵司完整的《一般纳税人开票信息》（抬头、税号、开户行及账号、地址电话），审核后 24 小时内推送 PDF/OFD 版式文件至您的财务邮箱。",
        ),
        (
            f"{prefix}{dept}上月开的发票 {order_id}（{amount} 元）抬头少打了「科技」二字，已跨月怎么在{tw}前红冲重开？{constraint}",
            f"原发票单号：{order_id} | 状态：已跨月 | 金额：{amount}元",
            f"您好！根据税务局最新规定，已跨月的电子/数电发票无法直接「作废」，但支持申请「红冲重开」。请您进入「发票管理 -> 申请红冲/换开」，选择「抬头信息错误」，系统将自动开具负数红字发票冲销原票，并在 1 个工作日内为您重新开具抬头正确的蓝字发票。",
        ),
        (
            f"{prefix}{dept}这半年零散下了 12 笔订单（含 {order_id}，合计 {amount} 元），能在{tw}前合并开汇总发票并附清单吗？{constraint}",
            "",
            f"您好！系统支持「多订单合并开票」。请进入「发票中心 -> 批量合并开票」，勾选同一开票主体且已完成确认收货的 12 笔订单即可合并开具一张发票；若商品明细超过 8 行，数电发票将自动生成标准《销售货物或者提供应税劳务清单》作为附件。",
        ),
        (
            f"{prefix}{dept}通过{pay}转账了 {amount} 元，已过 4 小时，订单 {order_id} 为何还显示待支付？{tw}能核销吗？{constraint}",
            f"订单号：{order_id} | 金额：{amount}元 | 方式：{pay}",
            f"您好！对公转账需等待银行大额清算回执及系统自动核销，通常在 1-2 个工作日内完成认领。若急需确认，请您核对汇款时是否在附言栏准确填写了订单识别码，并点击「上传银行电子回单」，财务专员将在 2 小时内为您人工核销到账。",
        ),
        (
            f"{prefix}{dept}开出的数电发票 {order_id}（{amount} 元）被邮箱拦截，{tw}前在哪里下载 XML 原文件和盖章 PDF？{constraint}",
            "",
            f"您好！您无需依赖邮件附件，随时可登录网页端或 App 进入「财务中心 -> 我的发票 -> 已开票列表」，点击对应发票右侧的「下载文件」，即可一键获取 PDF、OFD 以及税务入账所需的 XML 原文件压缩包。",
        ),
        (
            f"{prefix}{dept}订单 {order_id} 退了 300 元，原开出的 {amount} 元全额发票还能直接入账吗？{tw}前怎么换票？{constraint}",
            f"订单号：{order_id} | 原票金额：{amount}元 | 已退：300元",
            f"您好！发生部分退款后，原全额发票已与实际交易金额不符，不可直接入账报销。系统将在退款完成时自动触发红冲流程，作废原 {amount} 元发票并按实际保留金额（{amount - 300} 元）为您重新生成新发票。",
        ),
        (
            f"{prefix}{dept}员工用个人{pay}垫付了 {amount} 元（单号 {order_id}），{tw}前开票抬头能写公司名称吗？{constraint}",
            "",
            f"您好！可以的。平台开具发票的抬头信息与实际付款人微信/支付宝账号无强制绑定关系，只要您在申请开票时选择「企业抬头」并准确填写贵司名称与统一社会信用代码，即可正常开具供公司报销入账。",
        ),
        (
            f"{prefix}{dept}这笔 {amount} 元采购（单号 {order_id}）需要先拿发票审批再付款，{tw}前能走「先票后款」吗？{constraint}",
            "",
            f"您好！针对已签订年度框架协议或单笔金额超过 5 万元的企业授信客户，我们支持「先票后款」结算流程。请您在下单结算时选择「企业授信月结」或联系您的客户经理提交《授信开票申请单》，审批通过后即可先行开票。",
        ),
        (
            f"{prefix}{dept}订单 {order_id} 实付 {amount} 元，可开票金额只显示 {amount - 100} 元，少了 100 元去哪了？{constraint}",
            "",
            f"您好！出现开票金额小于订单总额，通常是因为您使用了「平台无门槛现金券 / 满减优惠券」或「积分抵扣」。依据税法规定，发票仅按您实际支付的货币金额（{amount - 100} 元）开具，平台补贴与积分抵扣部分不计入应税销售额。",
        ),
        (
            f"{prefix}{dept}对账发现账单 {order_id} 重复扣款 {amount} 元（{pay}），如何在{tw}前申请调账退款？{constraint}",
            f"账单号：{order_id} | 金额：{amount}元 | 异常：疑似重复扣款",
            f"非常抱歉出现对账异常！请您在「财务中心 -> 账单申诉」提交该笔重复扣款的流水号与银行截图，账务核对小组将在 24 小时内完成流水核查，确认属实后原路退回多扣的 {amount} 元并同步修正您的月度对账单。",
        ),
    ]
    inst, inp, out = scenarios[sub_type]
    return AlpacaSample(
        instruction=inst,
        input=inp,
        output=out,
        system=_SYSTEM_PROMPT,
        category="invoice_billing",
    )


def _build_vip_membership_sample(idx: int, rng: random.Random) -> AlpacaSample:
    points = 1000 + (idx % 10) * 500
    dept = _DEPARTMENTS[(idx // 2) % len(_DEPARTMENTS)]
    city = _CITIES[(idx // 3) % len(_CITIES)]
    tw = _TIME_WINDOWS[(idx // 5) % len(_TIME_WINDOWS)]
    constraint = _EXTRA_CONSTRAINTS[(idx // 10) % len(_EXTRA_CONSTRAINTS)]
    product = _PRODUCTS[(idx // 4) % len(_PRODUCTS)]
    sub_type = idx % 10
    prefix = _PERSONA_PREFIXES[(idx // 10) % len(_PERSONA_PREFIXES)]
    vip_id = f"VIP{5000 + idx * 11}"

    scenarios = [
        (
            f"{prefix}{dept}的企业黄金会员（卡号 {vip_id}）还有 15 天到期，{tw}前续费的话剩余天数和 {points} 积分会清零吗？{constraint}",
            f"会员号：{vip_id} | 当前等级：企业黄金VIP | 剩余：15天 | 积分：{points}",
            f"您好！提前续费后，新购买的会员时长将在当前到期日之后自动顺延累加，剩余 15 天绝不作废；账户内的 {points} 积分按自然年滚动有效期规则保留，不会因续费而清零。",
        ),
        (
            f"{prefix}{dept}刚下单 8000 元「{product}」（{vip_id}），为什么成长值和 {points} 积分在{tw}前还没到账？{constraint}",
            "",
            f"您好！消费成长值与积分并非下单付款后即时发放，而是在您「确认收货且无售后退款」后的 24 小时内自动入账，以防止刷单或退货导致的积分异常。",
        ),
        (
            f"{prefix}{dept}考虑在{tw}升级黑金 VIP（编号 {vip_id}），相比普通企业版在{city}技术支持时效与折扣上有哪些权益？{constraint}",
            "",
            f"您好！黑金 VIP 尊享四大核心权益：1）7×24 小时专属架构师群支持（15 分钟 SLA 极速响应）；2）硬件采购享协议价基础再 95 折与每月 5 次免运费定时达；3）免费开放企业级沙箱测试额度；4）优先内测新发布的 AI Agent 行业插件。",
        ),
        (
            f"{prefix}{dept}账户（{vip_id}）有 {points} 积分下月底过期，能在{tw}前直接兑换抵扣「{product}」或算力包费用吗？{constraint}",
            f"会员号：{vip_id} | 即将过期积分：{points} | 部门：{dept}",
            f"您好！{points} 积分可在「积分商城 -> 算力代金券」按 100 积分 = 1 元的比例兑换「云端算力无门槛抵扣券」，兑换后的代金券有效期将重新计算 90 天，下单资源包时可直接抵扣现金使用。",
        ),
        (
            f"{prefix}{dept}想把{city}同事个人账号的成长值与 {points} 积分合并到公司主号 {vip_id}，{tw}前能跨账号转移吗？{constraint}",
            "",
            f"您好！出于反欺诈与账户主体隔离要求，个人账号与企业主账号的成长值、VIP 等级及积分均不支持跨账号合并或转让。建议后续企业采购统一使用企业主账号或授权子账号下单，所有消费将自动累计至企业主账号。",
        ),
        (
            f"{prefix}{dept}会员 {vip_id} 昨晚被自动续费扣款了，但这个月不打算继续用，能在{tw}前申请全额退回吗？{constraint}",
            f"会员号：{vip_id} | 状态：自动续费扣款成功（24小时内）",
            f"您好！若在自动续费扣款后 48 小时内未使用任何新周期会员专属权益（如领券、免邮、专属客服工单），您可以进入「会员中心 -> 自动续费管理」关闭后续扣费，并点击「申请误扣全额退款」，系统将在 1-3 个工作日内原路退回款项。",
        ),
        (
            f"{prefix}{dept}（{vip_id}）推荐了{city}的 3 家伙伴完成首单，推荐奖励 {points} 积分会在{tw}前发放吗？{constraint}",
            "",
            f"您好！推荐新企业完成首单且订单金额满 3000 元、无退货记录后，系统将在被推荐方确认收货满 7 天时，自动向您的账户发放每家 2000 积分的推荐激励，可在「邀请记录」实时追踪进度。",
        ),
        (
            f"{prefix}{dept}在积分商城用 {points} 积分换了 9 折券（{vip_id}），为什么结算「{product}」时显示不可用？{constraint}",
            "",
            f"您好！请核查以下三项使用门槛：1）部分「企业特惠一口价 / 政府集采专供」商品不与其他折扣券叠加；2）该券可能限定仅适用于配件耗材类目；3）订单需满足券面规定的最低消费金额。您可在「卡券详情 -> 适用商品范围」一键查看可用清单。",
        ),
        (
            f"{prefix}{dept}在{city}的分公司主体更名了，原 {vip_id} 的 VIP 权益和 {points} 积分在{tw}前能无损保留吗？{constraint}",
            "",
            f"您好！公司更名属于工商主体延续而非主体注销。请您在「企业资料 -> 工商变更认证」上传市场监管部门出具的《准予变更登记通知书》与新版营业执照，审核通过后原有 VIP 等级、剩余有效期及 {points} 积分将 100% 完整保留。",
        ),
        (
            f"{prefix}{dept}升级铂金会员（{vip_id}）赠送了{city}「免费上门部署培训」，怎么在{tw}前预约工程师？{constraint}",
            "",
            f"您好！铂金会员赠送的「1 次免费上门/远程专项部署培训」在会员有效期内均可使用。请提前至少 5 个工作日进入「VIP 专属服务 -> 预约实施顾问」，填写贵司所在城市、期望时间与培训人数，我们将为您指派认证交付工程师。",
        ),
    ]
    inst, inp, out = scenarios[sub_type]
    return AlpacaSample(
        instruction=inst,
        input=inp,
        output=out,
        system=_SYSTEM_PROMPT,
        category="vip_membership",
    )


def generate_customer_service_dataset(
    count: int = 500,
    *,
    seed: int = 42,
    include_dirty_ratio: float = 0.0,
) -> list[AlpacaSample]:
    """Self-Instruct 风格垂直领域（企业级智能客服）合成数据集生成器.

    Args:
        count: 期望生成的样本总数（默认 500 条）。
        seed: 随机种子，保证可复现性。
        include_dirty_ratio: 可选脏数据比例 [0.0, 0.5]，用于演示清洗与去重效果。

    Returns:
        AlpacaSample 列表。
    """
    if count <= 0:
        raise ValueError("count 必须为正整数")
    if not 0.0 <= include_dirty_ratio <= 0.5:
        raise ValueError("include_dirty_ratio 必须在 [0.0, 0.5] 区间内")

    rng = random.Random(seed)
    builders = [
        _build_order_logistics_sample,
        _build_refund_aftersales_sample,
        _build_account_security_sample,
        _build_invoice_billing_sample,
        _build_vip_membership_sample,
    ]

    dirty_count = int(count * include_dirty_ratio)
    clean_target = count - dirty_count

    samples: list[AlpacaSample] = []
    for i in range(clean_target):
        builder = builders[i % len(builders)]
        sample = builder(i // len(builders), rng)
        samples.append(sample)

    # 若指定注入脏数据，则插入空白噪点与精确/近似重复样本以供清洗演示
    if dirty_count > 0 and samples:
        for d in range(dirty_count):
            base = samples[d % len(samples)]
            if d % 2 == 0:
                # 精确重复 + 多余空白噪点
                samples.append(
                    AlpacaSample(
                        instruction=f"  {base.instruction}   \u200b",
                        input=base.input,
                        output=f"\n\n{base.output}  ",
                        system=base.system,
                        category=base.category,
                    )
                )
            else:
                # 近似重复（仅末尾多一个标点或语气词）
                samples.append(
                    AlpacaSample(
                        instruction=f"{base.instruction} 谢谢！",
                        input=base.input,
                        output=base.output,
                        system=base.system,
                        category=base.category,
                    )
                )

    rng.shuffle(samples)
    return samples


# ---------------------------------------------------------------------------
# 5. JSONL 导入/导出与数据集统计分析
# ---------------------------------------------------------------------------


def export_jsonl(
    samples: Sequence[AlpacaSample | ShareGPTSample], path: Path | str
) -> Path:
    """将 AlpacaSample 或 ShareGPTSample 列表导出为 UTF-8 JSONL 文件."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for sample in samples:
            fh.write(sample.model_dump_json(by_alias=True) + "\n")
    return target


def load_jsonl(
    path: Path | str, schema: Literal["alpaca", "sharegpt"] = "alpaca"
) -> list[AlpacaSample] | list[ShareGPTSample]:
    """从 UTF-8 JSONL 文件加载并校验数据集."""
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"数据集文件不存在: {source}")

    model_cls = AlpacaSample if schema == "alpaca" else ShareGPTSample
    loaded: list[AlpacaSample | ShareGPTSample] = []
    with source.open("r", encoding="utf-8") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                loaded.append(model_cls.model_validate_json(stripped))
            except Exception as exc:
                raise ValueError(
                    f"解析 {source} 第 {line_no} 行失败: {exc}"
                ) from exc
    return loaded  # type: ignore[return-value]


class DatasetStats(BaseModel):
    """指令微调数据集统计摘要."""

    total_count: int
    category_distribution: dict[str, int]
    avg_instruction_len: float
    avg_input_len: float
    avg_output_len: float
    with_input_ratio: float


def compute_dataset_stats(samples: Sequence[AlpacaSample]) -> DatasetStats:
    """统计 Alpaca 数据集的规模、分类分布、平均字符长度与有输入比例."""
    if not samples:
        return DatasetStats(
            total_count=0,
            category_distribution={},
            avg_instruction_len=0.0,
            avg_input_len=0.0,
            avg_output_len=0.0,
            with_input_ratio=0.0,
        )

    n = len(samples)
    cats = Counter(s.category for s in samples)
    avg_inst = round(sum(len(s.instruction) for s in samples) / n, 2)
    avg_inp = round(sum(len(s.input) for s in samples) / n, 2)
    avg_out = round(sum(len(s.output) for s in samples) / n, 2)
    with_inp = round(sum(1 for s in samples if s.input.strip()) / n, 4)

    return DatasetStats(
        total_count=n,
        category_distribution=dict(sorted(cats.items())),
        avg_instruction_len=avg_inst,
        avg_input_len=avg_inp,
        avg_output_len=avg_out,
        with_input_ratio=with_inp,
    )
