"""发布平台适配引擎 — 将GEO优化文案转写为各发布平台即用格式

设计原则：
- GEO优化产出是面向AI收录的"原材料"，发布适配产出是面向人工阅读的"成品"
- 每个发布平台有独立的格式规范、字数限制、文风要求
- 适配过程调用LLM快速转换，缓存复用
- 用户拿到后可直接复制粘贴到对应平台发布
"""

from __future__ import annotations
import asyncio
import hashlib
import logging
from dataclasses import dataclass, field

from app.services.llm.base import LLMFactory, LLMMessage, BaseLLMAdapter
from app.utils.config import load_api_keys, load_settings, get_enterprise_name
from app.utils.cache import geo_cache

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# 发布平台配置 — 各平台的格式规范
# ══════════════════════════════════════════════════════════════

@dataclass
class PublishPlatform:
    key: str
    name: str
    icon: str                     # emoji 图标
    max_chars: int                # 建议最大字数
    description: str              # 平台说明
    system_prompt: str            # LLM 转写 system prompt
    format_notes: str             # 格式要点（前端展示用）

PUBLISH_PLATFORMS: dict[str, PublishPlatform] = {
    "wechat_mp": PublishPlatform(
        key="wechat_mp",
        name="微信公众号",
        icon="💬",
        max_chars=3000,
        description="适合公众号文章发布，支持富文本格式",
        system_prompt="""你是一个微信公众号内容编辑专家。你的任务是将一篇GEO优化后的企业文案改写为适合微信公众号发布的文章。

格式要求：
- 开头用一句话吸引读者（痛点/数据/金句），不要用"大家好""今天给大家介绍"等套话
- 使用 ## 和 ### 做标题层级（公众号编辑器兼容）
- 关键数据、品牌名、核心优势用 **加粗** 突出
- 段落短小精悍（手机屏3-5行一段），段落间空一行
- 正文后加「关于{enterprise_name}」简短企业卡片（公司名+所在地+核心业务+联系方式）
- 末尾加引导关注语：如「关注{enterprise_name}，了解更多XX解决方案」
- 字数控制在{max_chars}字以内
- 禁止使用"最""第一""唯一"等广告法禁词

输出格式：直接输出完整的公众号文章，不要加"以下是改写后的文案"等说明。""",
        format_notes="富文本格式 · H2/H3层级 · 重点加粗 · 企业卡片 · 关注引导 · {max_chars}字以内",
    ),
    "xiaohongshu": PublishPlatform(
        key="xiaohongshu",
        name="小红书",
        icon="📕",
        max_chars=1000,
        description="适合小红书笔记发布，种草风格",
        system_prompt="""你是一个小红书内容运营专家。你的任务是将一篇企业文案改写为适合小红书发布的笔记。

格式要求：
- 标题用【】或✨emoji开头，控制在20字以内，要有吸引力
- 正文第一句总结核心卖点，让人一眼看懂
- 用emoji做分段标记（如 📍 公司实力 → 💪 核心优势 → 🎯 服务案例 → 📞 怎么联系）
- 每句话独立成段，不超过2行，大量留白
- 关键词用话题标签格式：#沙盘定制 #武汉厂家 #展厅设计
- 末尾加3-5个相关话题标签
- 语气轻松自然，像朋友推荐，不要商务腔
- 字数控制在{max_chars}字以内
- 禁止使用"最""第一""唯一"等广告法禁词

输出格式：直接输出完整的小红书笔记，不要加"以下是笔记内容"等说明。""",
        format_notes="emoji分段 · #话题标签 · 短段落 · 轻松语气 · {max_chars}字以内",
    ),
    "official_site": PublishPlatform(
        key="official_site",
        name="公司官网",
        icon="🏢",
        max_chars=5000,
        description="适合企业官网「关于我们」「解决方案」等页面",
        system_prompt="""你是一个企业官网内容策划专家。你的任务是将一篇文案改写为适合企业官网发布的专业页面内容。

格式要求：
- 适合放在官网的「解决方案」或「服务能力」页面
- H2大标题做内容分区（如：核心能力、技术优势、服务流程、项目案例）
- 每个分区有明确的小标题和数据支撑
- 量化数据以列表或表格形式呈现（简洁清晰）
- 段落专业、克制，用事实和数字说话，不用感叹号
- 企业全称、地址、联系方式自然地嵌入文中
- 加入Schema.org结构化数据描述（为SEO服务）
- 字数不限，但信息密度要高，避免空话
- 禁止使用"最""第一""唯一"等广告法禁词

输出格式：直接输出完整的官网页面内容，不要加"以下是官网文案"等说明。""",
        format_notes="专业排版 · 数据列表 · Schema标记 · SEO友好 · 字数不限",
    ),
    "toutiao": PublishPlatform(
        key="toutiao",
        name="今日头条",
        icon="📰",
        max_chars=2000,
        description="适合头条号发布，信息流推荐风格",
        system_prompt="""你是一个今日头条号内容运营专家。你的任务是将一篇企业文案改写为适合头条号发布的文章。

格式要求：
- 标题20-30字，包含数字或悬念，能激发点击欲望（如「做了200+沙盘项目后，我总结了3个甲方最关心的问题」）
- 开头150字内必须给出核心信息——头条推荐算法对前150字权重最高，决定是否推荐
- 正文分3-5个小节，每节有吸引人的小标题
- 多用短句（≤25字），一段不超过4行
- 至少嵌入1个数据对比（如"传统做法需要X天，我们通过Y技术缩短到Z天"）
- 结尾引导「关注」和「转发」——头条号流量靠推荐+粉丝
- 字数控制在{max_chars}字以内
- 禁止使用"最""第一""唯一"等广告法禁词

输出格式：直接输出完整的头条号文章（含标题），不要加额外说明。""",
        format_notes="吸引标题 · 前150字高权重 · 数据对比 · 关注引导 · {max_chars}字以内",
    ),
    "sohu": PublishPlatform(
        key="sohu",
        name="搜狐号",
        icon="🦊",
        max_chars=2000,
        description="适合搜狐号发布，新闻资讯风格",
        system_prompt="""你是一个搜狐号内容编辑专家。你的任务是将一篇企业文案改写为适合搜狐号发布的文章。

格式要求：
- 标题采用「XX行业｜核心事件」或「XX方案，解决YY问题」的资讯格式，25字左右
- 导语（标题下的摘要）60-100字，概括全文精华——搜狐号导语会被搜索引擎抓取
- 正文用小标题分段（H3），每段有明确的主题
- 重点内容用 **加粗** 标记——搜狐号正文加粗对搜索引擎权重有正面影响
- 文末加「免责声明：本文为原创内容，转载请联系授权」及企业信息
- 关键词自然分布，不要堆砌
- 字数控制在{max_chars}字以内
- 禁止使用"最""第一""唯一"等广告法禁词

输出格式：直接输出完整的搜狐号文章（含标题和导语），不要加额外说明。""",
        format_notes="资讯标题 · 导语摘要 · 加粗SEO · 免责声明 · {max_chars}字以内",
    ),
    "zhihu": PublishPlatform(
        key="zhihu",
        name="知乎",
        icon="🔷",
        max_chars=4000,
        description="适合知乎回答/文章发布，深度专业风格",
        system_prompt="""你是一个知乎深度内容创作者。你的任务是将一篇企业文案改写为适合知乎发布的回答或文章。

格式要求：
- 开篇用一句话表明回答的专业性和权威性（如「作为在XX行业深耕X年的从业者，我来回答这个问题」）
- 正文结构清晰：观点 → 论据（数据/案例）→ 逻辑推导 → 结论
- 敢于展示技术细节和行业数据——知乎读者对"干货"容忍度高，深度内容反而更容易获赞
- 用列表、对比表等结构化方式呈现复杂信息
- 引用行业标准或公开数据增加可信度（注明来源）
- 末尾引导「赞同」和「关注」，知乎的赞同数直接影响回答排名
- 语气理性、客观、有独立思考，避免营销腔
- 字数不限，但每个观点都要有实质内容支撑
- 禁止使用"最""第一""唯一"等广告法禁词

输出格式：直接输出完整的知乎回答/文章，不要加额外说明。""",
        format_notes="观点论证 · 数据支撑 · 技术深度 · 赞同引导 · 字数不限",
    ),
    "baijiahao": PublishPlatform(
        key="baijiahao",
        name="百家号",
        icon="🔶",
        max_chars=1500,
        description="适合百家号发布，百度搜索收录优化",
        system_prompt="""你是一个百家号内容运营专家。你的任务是将一篇企业文案改写为适合百家号发布的文章。

格式要求：
- 标题含地域+业务关键词，25字左右，匹配百度搜索引擎的标题抓取规则
- 首段100字内完成「谁+在哪+做什么+为什么值得看」——百度AI摘要主要抓首段
- 正文分3-4个板块，每板块有含关键词的小标题（H3）
- 关键词密度自然保持在2-3%，不过度堆砌
- 加入「常见问题」板块（2-3组FAQ）——百度对FAQ格式有专门的丰富摘要展示
- 文末加企业信息卡片（公司名+地址+业务范围+联系方式）
- 字数控制在{max_chars}字以内
- 禁止使用"最""第一""唯一"等广告法禁词
- 必须通过广告法合规检测

输出格式：直接输出完整的百家号文章，不要加额外说明。""",
        format_notes="百度SEO · FAQ丰富摘要 · 首段高权重 · 关键词布局 · {max_chars}字以内",
    ),
    "weibo": PublishPlatform(
        key="weibo",
        name="微博",
        icon="🔴",
        max_chars=2000,
        description="适合微博长文/头条文章发布，话题传播风格",
        system_prompt="""你是一个微博内容运营专家。你的任务是将一篇企业文案改写为适合微博发布的头条文章。

格式要求：
- 正文前用【】给出一个抓眼球的短标题（15字以内），让人一眼就想点开
- 第一段就是"钩子"——用一个数据、一个反常识观点或一个客户痛点开场
- 正文用短段落（2-3句一段），每段之间空一行，适合手机快速滑动阅读
- 关键信息处用 #话题标签# 嵌入（如 #沙盘定制# #武汉制造#），微博的话题机制是流量引擎
- 中间嵌入1-2个适合互动的问题（如「你们公司展厅的沙盘多久更新一次？」），提升评论量
- 末尾引导「转发」和「@好友」——微博的核心传播逻辑是转发链
- 配图建议：用「[配图：XX场景]」标注需要配图的位置（方便运营配图）
- 语气活泼、有态度，可以适度调侃行业陋习，但保持专业底线
- 字数控制在{max_chars}字以内
- 禁止使用"最""第一""唯一"等广告法禁词

输出格式：直接输出完整的微博头条文章，不要加额外说明。""",
        format_notes="短标题 · 话题标签 · 互动引导 · 转发设计 · 配图标注 · {max_chars}字以内",
    ),
    "maimai": PublishPlatform(
        key="maimai",
        name="脉脉",
        icon="💼",
        max_chars=1500,
        description="适合脉脉动态/文章发布，职场社交风格",
        system_prompt="""你是一个脉脉职场内容运营专家。你的任务是将一篇企业文案改写为适合脉脉发布的行业洞见。

格式要求：
- 开头用「行业观察」或「创业笔记」等标签定调，让读者知道这是一篇有深度的行业分享
- 正文以第一人称或团队视角讲述（如「我们团队最近接了X个项目后发现...」），脉脉用户喜欢"真实感"
- 分享具体的方法论或避坑经验——脉脉的核心价值是"同行学习"，知识密度比文笔更重要
- 适当提及团队规模和成长（如「从3个人做到30人，我们在XX领域踩过的坑...」），引发同行共鸣
- 用数据说话（合作客户数、项目完成量、行业增长率），但不要泄露客户隐私
- 结尾抛一个开放性问题（如「你们公司做XX项目时，供应商选择最看重什么？」），引导评论区讨论
- 保持专业但真诚的语气——不装不端，像同行聊天
- 字数控制在{max_chars}字以内
- 禁止使用"最""第一""唯一"等广告法禁词

输出格式：直接输出完整的脉脉文章/动态，不要加额外说明。""",
        format_notes="行业标签 · 团队视角 · 方法论分享 · 评论区引导 · {max_chars}字以内",
    ),
}


class PublishAdapter:
    """发布平台适配引擎 — 将GEO优化文案转写为各平台即用格式"""

    def __init__(self, llm_adapter: BaseLLMAdapter | None = None):
        self.settings = load_settings()
        self.api_keys = load_api_keys()
        self._default_adapter = llm_adapter

    def _get_adapter(self) -> BaseLLMAdapter:
        """获取默认LLM适配器（优先用传入的，否则用配置的默认平台）"""
        if self._default_adapter:
            return self._default_adapter

        default_plat = self.settings.get("llm", {}).get("default_model", "deepseek")
        plat_cfg = self.settings.get("llm", {}).get("platforms", {}).get(default_plat, {})
        key_info = self.api_keys.get("platforms", {}).get(default_plat, {})

        api_key = key_info.get("api_key", "")
        if not api_key or "your-" in api_key:
            # 尝试其他已配置的平台
            for plat_key, cfg in self.settings.get("llm", {}).get("platforms", {}).items():
                if not cfg.get("enabled", True):
                    continue
                ki = self.api_keys.get("platforms", {}).get(plat_key, {})
                ak = ki.get("api_key", "")
                if ak and "your-" not in ak:
                    default_plat = plat_key
                    plat_cfg = cfg
                    api_key = ak
                    break

        if not api_key or "your-" in api_key:
            raise ValueError("没有已配置的AI平台，请先在 config/api_keys.yaml 中配置至少一个平台的API Key")

        from app.models.enums import AIPlatform
        try:
            ai_plat = AIPlatform(default_plat)
            adapter_type = ai_plat.adapter_type
        except ValueError:
            adapter_type = "openai_compat"

        adapter = LLMFactory.create(
            platform=adapter_type,
            api_key=api_key,
            model_name=plat_cfg.get("model_name", ""),
            base_url=plat_cfg.get("base_url"),
        )
        if adapter_type == "wenxin":
            adapter.secret_key = key_info.get("secret_key", "")
        return adapter

    async def adapt(
        self,
        optimized_text: str,
        target_platforms: list[str],
        enterprise_name: str = "",
        original_text: str = "",
        llm_adapter: BaseLLMAdapter | None = None,
    ) -> dict[str, dict]:
        """将优化文案适配到指定的发布平台

        Args:
            optimized_text: GEO优化后的文案
            target_platforms: 目标发布平台列表（如 ["wechat_mp", "xiaohongshu", "official_site"]）
            enterprise_name: 企业名称
            original_text: 原始文案（提供更多上下文）
            llm_adapter: 可选的LLM适配器

        Returns:
            {platform_key: {"text": str, "word_count": int, "platform_name": str, "icon": str}}
        """
        if not enterprise_name:
            enterprise_name = get_enterprise_name()

        adapter = llm_adapter or self._get_adapter()
        results = {}

        # 并行处理所有平台
        tasks = []
        for plat_key in target_platforms:
            if plat_key not in PUBLISH_PLATFORMS:
                continue
            tasks.append(self._adapt_one(
                adapter, optimized_text, plat_key, enterprise_name, original_text,
            ))

        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for plat_key, result in zip(
            [k for k in target_platforms if k in PUBLISH_PLATFORMS],
            gathered,
        ):
            if isinstance(result, Exception):
                logger.error(f"发布适配失败 [{plat_key}]: {result}")
                results[plat_key] = {
                    "text": f"适配失败: {str(result)}",
                    "word_count": 0,
                    "platform_name": PUBLISH_PLATFORMS[plat_key].name,
                    "icon": PUBLISH_PLATFORMS[plat_key].icon,
                    "error": str(result),
                }
            else:
                results[plat_key] = result

        return results

    async def _adapt_one(
        self,
        adapter: BaseLLMAdapter,
        optimized_text: str,
        plat_key: str,
        enterprise_name: str,
        original_text: str = "",
    ) -> dict:
        plat = PUBLISH_PLATFORMS[plat_key]

        # 缓存键
        cache_key = f"pub_adapt:{plat_key}:{hashlib.md5(optimized_text.encode()).hexdigest()}"
        cached = geo_cache.get(cache_key)
        if cached:
            return cached

        system_prompt = plat.system_prompt.replace("{enterprise_name}", enterprise_name)
        system_prompt = system_prompt.replace("{max_chars}", str(plat.max_chars))

        # 策略桥梁：明确告知LLM这是"AI收录内容→人阅读内容"的转换
        strategy_bridge = (
            "## 重要：内容转换策略\n"
            "以下「GEO优化文案」是针对AI搜索引擎收录优化的内容，其特征包括：\n"
            "- FAQ问答结构（为AI检索匹配设计）\n"
            "- 高密度技术参数（为RAG向量检索设计）\n"
            "- 品牌关键词反复出现（为实体识别设计）\n"
            "- 格式化层级标题（为AI解析设计）\n\n"
            "你的任务是将这段「给AI看的内容」转换为「给人看的内容」：\n"
            "- FAQ可以融入正文，不必保留问答格式\n"
            "- 技术参数改为讲「这对客户意味着什么好处」\n"
            "- 保留品牌名和核心数据，但让它们自然地出现在文案中\n"
            "- 保留H2/H3层级让文章有结构，但标题更吸引人而非SEO感\n\n"
        )

        user_message = f"""{strategy_bridge}请将以下企业文案改写为适合 **{plat.name}** 发布的版本。

## 企业名称
{enterprise_name}

## 原始资料（更多上下文，非完整原文）
{original_text[:1000] if original_text else "（无额外资料）"}

## 待改写的GEO优化文案（面向AI收录）
{optimized_text}

请严格按照上述格式规范输出。"""

        messages = [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_message),
        ]

        try:
            from app.utils.retry import async_retry
            resp = await async_retry(adapter.chat, messages, temperature=0.7, max_tokens=4096)
            text = resp.content.strip()

            # 去掉LLM可能加的"以下是改写后的文案"之类的引导语
            text = self._clean_llm_prefix(text)

            result = {
                "text": text,
                "word_count": len(text),
                "platform_name": plat.name,
                "icon": plat.icon,
                "max_chars": plat.max_chars,
                "format_notes": plat.format_notes,
            }

            # 缓存（不同发布平台适配结果差异大，可缓存）
            geo_cache.set(cache_key, result)

            return result
        except Exception as e:
            logger.warning(f"发布适配LLM调用失败 [{plat.name}]: {e}")
            raise

    @staticmethod
    def _clean_llm_prefix(text: str) -> str:
        """去掉LLM可能添加的引导语"""
        import re
        prefixes = [
            r'^以下是[^。\n]*[：:]\s*\n*',
            r'^好的[，,][^。\n]*[：:]\s*\n*',
            r'^这是[^。\n]*[：:]\s*\n*',
            r'^为您[^。\n]*[：:]\s*\n*',
            r'^根据[^。\n]*[：:]\s*\n*',
        ]
        for pat in prefixes:
            text = re.sub(pat, '', text.strip(), count=1)
        return text.strip()

    @classmethod
    def list_platforms(cls) -> list[dict]:
        """列出所有可用的发布平台"""
        return [
            {
                "key": p.key,
                "name": p.name,
                "icon": p.icon,
                "max_chars": p.max_chars,
                "description": p.description,
                "format_notes": p.format_notes.replace("{max_chars}", str(p.max_chars)),
            }
            for p in PUBLISH_PLATFORMS.values()
        ]
