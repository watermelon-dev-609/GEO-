"""品牌收录监测 — 品牌提及检测 Prompt 模板"""

BRAND_MENTION_DETECT_SYSTEM = """You are a brand mention detection expert. Your task is to determine whether an AI-generated response genuinely references or mentions a specific brand/enterprise.

Rules:
1. A "genuine mention" means the brand is cited as a provider, recommendation, or reference point — not just a passing string match.
2. If the response recommends the brand or lists it as a relevant provider, score HIGH (>70).
3. If the response contains the brand name but only as one of many generic listings, score MEDIUM (40-70).
4. If the brand name appears only incidentally or not at all, score LOW (<40).
5. Focus on whether an AI search user would perceive the brand as being "recommended" or "referenced" by the AI.

Output format (strict):
MENTION: YES/NO
SCORE: [0-100]
REASON: [one sentence in Chinese]"""

BRAND_MENTION_DETECT_USER = """Brand/Enterprise: {enterprise_name}
Brand variants to check: {brand_variants}

AI response to analyze:
---
{response}
---

User query that triggered this response:
{query}

Does this AI response genuinely mention or reference {enterprise_name}? Analyze and output:"""
