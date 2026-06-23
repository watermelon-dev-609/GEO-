/** 共享常量 — GEO生成式搜索优化系统 */

/** 8类沙盘类型 */
export const SANDTABLE_TYPES = [
  { value: 'smart_traffic', label: '智慧交通沙盘' },
  { value: 'smart_city', label: '智慧城市沙盘' },
  { value: 'smart_industry', label: '智慧工业沙盘' },
  { value: 'smart_agriculture', label: '智慧农业沙盘' },
  { value: 'smart_logistics', label: '智慧物流沙盘' },
  { value: 'military_terrain', label: '军事地形沙盘' },
  { value: 'digital_multimedia', label: '数字多媒体沙盘' },
  { value: 'real_estate', label: '地产/规划/展厅沙盘' },
  { value: 'general', label: '通用沙盘' },
]

/** 沙盘类型简写映射（用于Dashboard等短标签场景） */
export const SANDTABLE_LABELS = {
  smart_traffic: '智慧交通',
  smart_city: '智慧城市',
  smart_industry: '智慧工业',
  smart_agriculture: '智慧农业',
  smart_logistics: '智慧物流',
  military_terrain: '军事地形',
  digital_multimedia: '数字多媒体',
  real_estate: '地产/规划/展厅',
  general: '通用沙盘',
}

/** 10大AI平台（完整标签） */
export const AI_PLATFORMS = [
  { value: 'wenxin', label: '文心一言' },
  { value: 'tongyi', label: '通义千问' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'doubao', label: '字节豆包' },
  { value: 'yuanbao', label: '腾讯元宝' },
  { value: 'kimi', label: 'Kimi' },
  { value: 'xinghuo', label: '讯飞星火' },
  { value: 'claude', label: 'Claude' },
  { value: 'ollama', label: 'Ollama (本地)' },
  { value: 'lmstudio', label: 'LM Studio (本地)' },
]

/** 评测维度标签映射 */
export const DIMENSION_LABELS = {
  brand_recall: '品牌召回',
  solution_match: '方案匹配',
  semantic_alignment: '语义对齐',
  advantage_citation: '优势引用',
  real_citation: '真实采信',
  rag_retrievability: 'RAG可检索',
  structure_quality: '结构质量',
  differentiation: '差异化程度',
  source_consistency: '信源一致性',
  eeat_score: 'E-E-A-T',
}

/** AI原生维度（区别于传统人类视角维度） */
export const AI_NATIVE_DIMS = new Set(['semantic_alignment', 'rag_retrievability'])

/** 关键词分类 */
export const KEYWORD_CATEGORIES = [
  { key: 'brand', label: '品牌词' },
  { key: 'scene', label: '场景词' },
  { key: 'longtail', label: '长尾词' },
]

/** 诊断维度标签 */
export const DIAGNOSIS_LABELS = {
  entity_completeness: '实体完整性',
  structure_quality: '结构化程度',
  quantified_data: '量化数据',
  faq_friendliness: 'FAQ友好度',
  source_credibility: '信源可信度',
}

/** 评测评分颜色函数 */
export function scoreColor(score) {
  if (score >= 80) return '#5B8C5A'
  if (score >= 60) return '#D4956A'
  return '#C5554A'
}

/** 品牌收录监测 — 查询分类 */
export const QUERY_CATEGORIES = [
  { key: 'brand_direct', label: '品牌直问' },
  { key: 'scenario', label: '场景问询' },
  { key: 'product', label: '产品问询' },
]
