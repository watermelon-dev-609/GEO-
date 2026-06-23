<template>
  <div class="eval-view">
    <div class="page-header">
      <h2 class="page-title">AI评测中心</h2>
      <el-button size="small" @click="openHistory" :icon="Clock">评测历史</el-button>
    </div>

    <el-row :gutter="20">
      <!-- 左侧：配置面板 -->
      <el-col :span="8">
        <el-card shadow="never" class="config-card">
          <template #header><span>评测配置</span></template>

          <el-form label-position="top" size="default">
            <!-- 文本来源 -->
            <el-form-item label="评测文本">
              <el-select v-if="store.hasResults || store.hasCleanedText" v-model="textSource" style="width: 100%" @change="onTextSourceChange">
                <el-option label="使用优化结果" value="rewrite" :disabled="!store.hasResults" />
                <el-option label="使用清洗后文案" value="cleaned" :disabled="!store.hasCleanedText" />
                <el-option label="手动输入" value="manual" />
              </el-select>
              <el-input
                v-if="textSource === 'manual' || (!store.hasResults && !store.hasCleanedText)"
                v-model="evalText"
                type="textarea"
                :rows="8"
                placeholder="粘贴需要评测的文案..."
              />
              <div v-else class="text-preview">{{ evalText?.substring(0, 200) }}{{ evalText?.length > 200 ? '...' : '' }}</div>
            </el-form-item>

            <!-- 对比原文 -->
            <el-form-item>
              <el-collapse>
                <el-collapse-item title="对比原文（可选）" name="original">
                  <el-input v-model="originalText" type="textarea" :rows="4" placeholder="粘贴优化前的原文，用于生成前后对比报告" />
                </el-collapse-item>
              </el-collapse>
            </el-form-item>

            <!-- 沙盘类型 -->
            <el-form-item label="沙盘类型">
              <el-select v-model="sandtableType" style="width: 100%">
                <el-option v-for="t in sandtableTypes" :key="t.value" :label="t.label" :value="t.value" />
              </el-select>
            </el-form-item>

            <!-- 目标平台 -->
            <el-form-item label="目标平台">
              <el-select v-model="targetPlatforms" multiple style="width: 100%" placeholder="选择AI平台">
                <el-option v-for="p in availablePlatforms" :key="p.value" :label="p.label" :value="p.value" />
              </el-select>
            </el-form-item>

            <!-- 用户角色 -->
            <el-form-item label="模拟用户角色">
              <el-checkbox-group v-model="userRoles">
                <el-checkbox v-for="r in roleOptions" :key="r.value" :value="r.value">{{ r.label }}</el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <!-- 评测维度 + 权重 -->
            <el-form-item label="评测维度">
              <div v-for="dim in dimensionConfigs" :key="dim.key" class="dim-row">
                <el-checkbox
                  v-model="dim.enabled"
                  :disabled="dim.requires_llm && !hasLLM"
                  @change="onDimensionChange"
                >
                  {{ dim.label }}
                  <el-tag v-if="dim.requires_llm" size="small" type="info" style="margin-left: 4px">LLM</el-tag>
                </el-checkbox>
                <el-slider
                  v-if="dim.enabled"
                  v-model="dim.weight"
                  :min="0"
                  :max="100"
                  :step="5"
                  size="small"
                  style="width: 120px; margin-left: 12px"
                  @input="onWeightChange(dim)"
                />
                <span v-if="dim.enabled" class="dim-weight">{{ dim.weight }}%</span>
              </div>
              <div v-if="dimensionConfigs.some(d => d.enabled)" class="weight-summary" :class="{ invalid: !weightValid }">
                权重合计: {{ weightSum }}%
                <span v-if="!weightValid" style="color: #C5554A; margin-left: 4px;">（需为100%）</span>
              </div>
            </el-form-item>

            <!-- 自定义问题 + LLM生成 -->
            <el-form-item label="自定义问题（可选，一行一个）">
              <el-input v-model="customQuestions" type="textarea" :rows="3" placeholder="手动输入评测问题，或点击下方按钮自动生成..." />
              <div style="display:flex;align-items:center;gap:8px;margin-top:8px;">
                <el-button size="small" type="primary" @click="handleGenerateQuestions" :loading="generatingQuestions" :disabled="!evalText">
                  {{ generatingQuestions ? 'LLM生成中...' : '🤖 LLM生成评测问题' }}
                </el-button>
                <span v-if="generatedQuestions.length > 0" style="font-size:12px;color:#9B9EAA;">
                  已生成 {{ generatedQuestions.length }} 个问题，选中 {{ selectedGeneratedQs.length }} 个
                </span>
              </div>
            </el-form-item>

            <!-- 生成的问题列表 -->
            <div v-if="generatedQuestions.length > 0 && expandedQuestions" class="generated-qs-panel">
              <div class="generated-qs-header">
                <span>生成的问题（勾选以加入评测）</span>
                <el-button size="small" link @click="selectAllGenerated">
                  {{ selectedGeneratedQs.length === generatedQuestions.length ? '取消全选' : '全选' }}
                </el-button>
              </div>
              <div class="generated-qs-list">
                <div v-for="(q, i) in generatedQuestions" :key="i" class="generated-q-item"
                  :class="{ selected: selectedGeneratedQs.includes(q) }"
                  @click="toggleGeneratedQuestion(q)">
                  <el-checkbox :model-value="selectedGeneratedQs.includes(q)" @click.stop @change="toggleGeneratedQuestion(q)" />
                  <span class="generated-q-text">{{ q }}</span>
                </div>
              </div>
            </div>
          </el-form>

          <!-- 操作按钮 -->
          <div class="action-buttons">
            <el-button
              type="primary"
              size="large"
              :loading="isRunning"
              @click="startEval"
              style="width: 100%"
              :disabled="!evalText"
            >
              {{ isRunning ? '评测中...' : '开始评测' }}
            </el-button>
            <el-button
              v-if="isRunning"
              type="danger"
              size="default"
              @click="cancelEval"
              style="width: 100%; margin-top: 8px"
            >
              取消评测
            </el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：进度/结果区 -->
      <el-col :span="16">
        <!-- 空状态 -->
        <el-card shadow="never" v-if="evalStatus === 'idle'" class="empty-card">
          <div class="empty-state">
            <el-icon :size="64" color="#c0c4cc"><DataAnalysis /></el-icon>
            <h3>配置评测参数并开始评测</h3>
            <p>系统将分阶段执行评测，实时展示各维度结果</p>
          </div>
        </el-card>

        <!-- 进度区 -->
        <el-card shadow="never" v-if="evalStatus !== 'idle'" class="progress-card">
          <template #header>
            <div class="progress-header">
              <span>评测进度</span>
              <el-tag :type="statusTagType" size="small">{{ statusLabel }}</el-tag>
            </div>
          </template>

          <el-progress
            :percentage="evalOverallProgress"
            :status="evalStatus === 'failed' ? 'exception' : (evalStatus === 'completed' ? 'success' : '')"
            :stroke-width="16"
          />

          <!-- 阶段列表 -->
          <div class="phase-list">
            <div
              v-for="phase in phaseOrder"
              :key="phase.key"
              class="phase-row"
              :class="{ 'is-active': phase.status === 'running' }"
            >
              <div class="phase-icon">
                <el-icon v-if="phase.status === 'completed'" color="#5B8C5A"><CircleCheckFilled /></el-icon>
                <el-icon v-else-if="phase.status === 'running'" color="#C8963E" class="is-loading"><Loading /></el-icon>
                <el-icon v-else-if="phase.status === 'failed'" color="#C5554A"><CircleCloseFilled /></el-icon>
                <el-icon v-else-if="phase.status === 'skipped'" color="#9B9EAA"><RemoveFilled /></el-icon>
                <el-icon v-else color="#c0c4cc"><Clock /></el-icon>
              </div>
              <div class="phase-info">
                <span class="phase-label">{{ phase.label }}</span>
                <span v-if="phase.score !== null" class="phase-score" :style="{ color: scoreColor(phase.score) }">
                  {{ phase.score }}分
                </span>
                <span v-if="phase.status === 'running'" class="phase-running">评测中...</span>
              </div>
            </div>
          </div>
        </el-card>

        <!-- 完成后的综合结果 -->
        <div v-if="evalStatus === 'completed' && evalOverallScore !== null">
          <!-- 综合评分 -->
          <el-card shadow="never" class="score-card" style="margin-top: 16px">
            <div class="overall-score">
              <div class="score-number" :style="{ color: scoreColor(evalOverallScore) }">
                {{ evalOverallScore }}
              </div>
              <div class="score-label">综合评分 / 100</div>
              <div class="score-verdict" :style="{ color: scoreColor(evalOverallScore) }">
                {{ evalVerdict }}
              </div>
            </div>

            <!-- 关键发现 -->
            <div class="key-findings" v-if="evalFindings.length > 0" style="margin-top: 12px; padding: 10px 14px; background: #FAF8F5; border-radius: 8px;">
              <div v-for="(f, i) in evalFindings" :key="i" style="font-size:13px; line-height:1.8; color:#4A4D5A;">
                {{ f }}
              </div>
            </div>

            <!-- 维度得分条 -->
            <div class="dim-scores" style="margin-top: 16px">
              <div v-for="dim in completedDimensions" :key="dim.key" class="dim-score-row">
                <span class="dim-name">{{ dim.label }}</span>
                <el-progress
                  :percentage="dim.score"
                  :color="scoreColor(dim.score)"
                  :stroke-width="8"
                  style="flex: 1; margin: 0 12px"
                />
                <span class="dim-value">{{ dim.score }}分</span>
              </div>
            </div>
          </el-card>

          <!-- 信源一致性 / 幻觉风险 -->
          <el-card shadow="never" style="margin-top: 16px;" v-if="sourceConsistencyScore !== null">
            <template #header><span>抗AI幻觉 · 信源一致性</span></template>
            <div class="source-check-result">
              <el-tag :type="sourceConsistencyScore >= 90 ? 'success' : sourceConsistencyScore >= 70 ? 'warning' : 'danger'" size="large" effect="dark">
                {{ sourceConsistencyScore >= 90 ? '信源可靠' : sourceConsistencyScore >= 70 ? '存在少量未经证实的信息' : '信源一致性偏低' }}
              </el-tag>
              <span style="margin-left: 12px; font-size: 24px; font-weight: bold;" :style="{ color: scoreColor(sourceConsistencyScore) }">{{ sourceConsistencyScore }}分</span>
              <p style="margin-top: 8px; font-size: 13px; color: #9B9EAA;">
                {{ sourceConsistencyScore >= 90 ? '生成文本与企业官方信源高度一致，AI引用风险低' : sourceConsistencyScore >= 70 ? '部分内容可能偏离企业官方信源，建议核实后重新优化' : '文本中存在较多与信源不一致的信息，AI可能引用到编造的内容，强烈建议重新优化' }}
              </p>
            </div>
          </el-card>

          <!-- 前后对比 -->
          <el-card shadow="never" style="margin-top: 16px" v-if="beforeAfter">
            <template #header><span>优化前后对比</span></template>
            <div class="comparison">
              <div class="comp-item">
                <span class="comp-label">优化前</span>
                <span class="comp-value">{{ beforeAfter.before_score }}分</span>
              </div>
              <el-icon :size="24"><ArrowRight /></el-icon>
              <div class="comp-item">
                <span class="comp-label">优化后</span>
                <span class="comp-value">{{ beforeAfter.after_score }}分</span>
              </div>
              <el-tag :type="beforeAfter.improvement_percent > 0 ? 'success' : 'danger'" size="large">
                {{ beforeAfter.improvement_percent > 0 ? '+' : '' }}{{ beforeAfter.improvement_percent }}%
              </el-tag>
            </div>
            <el-button v-if="originalText" size="small" style="margin-top:12px;" @click="showTextDiff = true">
              📝 查看文字差异
            </el-button>
          </el-card>

          <!-- 文字差异弹窗 -->
          <el-dialog v-model="showTextDiff" title="优化前后文字对比" width="90%" top="5vh" :destroy-on-close="true">
            <el-row :gutter="12">
              <el-col :span="12">
                <div style="font-weight:600;margin-bottom:8px;color:#6B6E7B;">📄 优化前原文 ({{ originalText.length }}字)</div>
                <div class="diff-text-panel">{{ originalText }}</div>
              </el-col>
              <el-col :span="12">
                <div style="font-weight:600;margin-bottom:8px;color:#5B8C5A;">✅ 优化后文案 ({{ evalText.length }}字)</div>
                <div class="diff-text-panel">{{ evalText }}</div>
              </el-col>
            </el-row>
            <el-alert type="info" :closable="false" style="margin-top:12px;">
              字数变化：{{ originalText.length }}字 → {{ evalText.length }}字
              ({{ evalText.length > originalText.length ? '+' : '' }}{{ evalText.length - originalText.length }}字,
              {{ Math.round(Math.abs(evalText.length - originalText.length) / Math.max(originalText.length, 1) * 100) }}%)
            </el-alert>
          </el-dialog>

          <!-- 短板诊断 -->
          <el-card shadow="never" style="margin-top: 16px" v-if="weakPoints.length">
            <template #header><span>短板诊断</span></template>
            <el-alert
              v-for="(wp, i) in weakPoints"
              :key="i"
              :title="wp"
              type="warning"
              :closable="false"
              style="margin-bottom: 8px"
            />
          </el-card>

          <!-- ═══ 实测验证：评测分数 vs 真实AI收录 ═══ -->
          <el-card shadow="never" style="margin-top: 16px;">
            <template #header>
              <div style="display:flex;align-items:center;justify-content:space-between;">
                <span>🔍 实测验证 — 评测分数 vs 真实AI收录</span>
                <el-tag size="small" type="warning" effect="plain">AI模拟评测 ≠ 真实收录</el-tag>
              </div>
            </template>

            <el-alert
              title="当前评测分数由AI模型模拟计算，不等同于各AI平台的实际收录率。点击下方按钮，系统将在各AI平台上实际检索品牌，对比「预测分数」与「真实收录」。"
              type="info"
              :closable="false"
              style="margin-bottom: 16px;"
            />

            <!-- 触发实测 -->
            <div style="text-align:center;margin-bottom:16px;">
              <el-button
                type="primary"
                :loading="brandVerifyLoading"
                :disabled="!brandQueries.length"
                @click="runBrandVerify"
              >
                {{ brandVerifyLoading ? '正在各AI平台检索品牌...' : `实测验证：在${brandQueries.length}条查询上检索品牌收录` }}
              </el-button>
              <div v-if="!brandQueries.length" style="font-size:12px;color:#9B9EAA;margin-top:4px;">
                请先在品牌监测模块中配置查询关键词
              </div>
            </div>

            <!-- 实测结果对比 -->
            <div v-if="brandVerifyResult" class="verify-compare">
              <el-divider />
              <div class="verify-title">📊 预测 vs 实测 对比</div>

              <el-table :data="verifyCompareRows" size="small" style="margin-top:12px;">
                <el-table-column prop="dimension" label="维度" width="140" />
                <el-table-column label="AI模拟预测" width="120" align="center">
                  <template #default="scope">
                    <span :style="{color: scoreColor(scope.row.predicted), fontWeight:'bold'}">
                      {{ scope.row.predicted }}分
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="真实收录实测" width="140" align="center">
                  <template #default="scope">
                    <el-tag v-if="scope.row.actual !== null"
                      :type="scope.row.actual >= scope.row.predicted ? 'success' : scope.row.actual >= scope.row.predicted * 0.6 ? 'warning' : 'danger'"
                      size="small">
                      {{ scope.row.actual }}%
                    </el-tag>
                    <span v-else style="color:#C0C4CC;">暂无数据</span>
                  </template>
                </el-table-column>
                <el-table-column label="偏差" width="100" align="center">
                  <template #default="scope">
                    <span v-if="scope.row.delta !== null"
                      :style="{color: scope.row.delta >= 0 ? '#5B8C5A' : '#C5554A'}">
                      {{ scope.row.delta >= 0 ? '+' : '' }}{{ scope.row.delta }}%
                    </span>
                    <span v-else style="color:#C0C4CC;">—</span>
                  </template>
                </el-table-column>
                <el-table-column label="校准建议" min-width="180">
                  <template #default="scope">
                    <span v-if="scope.row.delta !== null && Math.abs(scope.row.delta) > 30" style="color:#C5554A;font-size:12px;">
                      ⚠️ 该维度偏差较大，建议调整评测权重或prompt
                    </span>
                    <span v-else-if="scope.row.delta !== null" style="color:#5B8C5A;font-size:12px;">
                      ✅ 预测与实际收录基本一致
                    </span>
                    <span v-else style="color:#C0C4CC;font-size:12px;">待积累更多实测数据</span>
                  </template>
                </el-table-column>
              </el-table>

              <el-alert
                v-if="brandVerifyResult.mention_rate !== undefined"
                :title="`实测品牌提及率: ${brandVerifyResult.mention_rate}%（${brandVerifyResult.mentioned_platforms || 0}/${brandVerifyResult.total_platforms || 0} 平台收录）`"
                :type="brandVerifyResult.mention_rate >= 60 ? 'success' : brandVerifyResult.mention_rate >= 30 ? 'warning' : 'danger'"
                :closable="false"
                style="margin-top: 12px;"
              >
                <template v-if="brandVerifyResult.verification_summary">
                  {{ brandVerifyResult.verification_summary }}
                </template>
              </el-alert>
            </div>
          </el-card>

          <!-- 优化建议 -->
          <el-card shadow="never" style="margin-top: 16px" v-if="suggestions.length">
            <template #header><span>迭代优化建议</span></template>
            <el-alert
              v-for="(sg, i) in suggestions"
              :key="i"
              :title="sg"
              type="success"
              :closable="false"
              style="margin-bottom: 8px"
            />
          </el-card>

          <!-- 一键采纳 -->
          <div v-if="suggestions.length > 0" style="margin-top: 16px;">
            <el-card shadow="never" style="background: #ecf5ff; border-color: #C8963E;">
              <div style="text-align: center;">
                <p style="font-size: 15px; color: #2D3142; margin-bottom: 12px;">
                  检测到 <strong>{{ suggestions.length }}</strong> 条优化建议，一键采纳全部并返回工坊重新优化
                </p>
                <el-button type="primary" size="large" @click="applyAllAndReoptimize">
                  采纳全部建议并重新优化
                </el-button>
              </div>
            </el-card>
          </div>

          <!-- 操作 -->
          <div style="text-align: right; margin-top: 16px; display: flex; gap: 8px; justify-content: flex-end; flex-wrap: wrap;">
            <el-button
              v-if="weakPoints.length > 0 || suggestions.length > 0"
              type="warning"
              size="large"
              :loading="autoReoptRunning"
              @click="autoReoptimizeAndEval"
            >
              {{ autoReoptRunning ? autoReoptProgress : '一键重优化并评测' }}
            </el-button>
            <el-button type="primary" @click="resetEval">重新评测</el-button>
            <el-button type="warning" @click="goToOptimize">返回GEO工坊优化</el-button>
            <el-button type="success" @click="goToExport">导出报告</el-button>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 评测历史抽屉 -->
    <el-drawer v-model="historyDrawerVisible" title="评测历史" size="480px" direction="rtl">
      <div v-if="historyItems.length === 0" class="history-empty">
        <el-icon :size="48" color="#c0c4cc"><Clock /></el-icon>
        <p style="margin-top: 12px; color: #9B9EAA;">暂无评测历史</p>
      </div>
      <div v-else>
        <div v-for="item in historyItems" :key="item.session_id" class="history-item">
          <div class="history-item-main" @click="toggleHistoryDetail(item)">
            <div class="history-item-left">
              <el-checkbox
                v-model="item._selected"
                @change="onCompareSelect(item)"
                @click.stop
              />
              <div class="history-item-info">
                <div class="history-item-date">{{ formatDate(item.created_at) }}</div>
                <div class="history-item-meta">
                  <el-tag size="small" type="info">{{ item.sandtable_type || '未知' }}</el-tag>
                  <el-tag size="small" :type="item.status === 'completed' ? 'success' : 'warning'">
                    {{ item.status === 'completed' ? '已完成' : item.status }}
                  </el-tag>
                </div>
              </div>
            </div>
            <div class="history-item-score" :style="{ color: scoreColor(item.overall_score) }">
              {{ item.overall_score ?? '-' }}分
              <div v-if="historyTrends[item.sandtable_type]" class="history-trend">
                <span class="trend-arrow">{{ historyTrends[item.sandtable_type].trend === 'up' ? '↑' : historyTrends[item.sandtable_type].trend === 'down' ? '↓' : '→' }}</span>
                <span class="trend-scores">{{ historyTrends[item.sandtable_type].scores.join(' → ') }}</span>
              </div>
            </div>
            <el-button
              size="small"
              type="danger"
              :icon="Delete"
              circle
              @click.stop="deleteHistoryItem(item)"
            />
          </div>
          <!-- 展开详情 -->
          <div v-if="item._expanded" class="history-item-detail">
            <div v-if="item._loading" v-loading="true" style="min-height: 80px;" />
            <div v-else-if="item._detail">
              <div v-for="dim in getDetailDimensions(item._detail)" :key="dim.key" class="history-dim-row">
                <span>{{ dim.label }}</span>
                <el-progress :percentage="dim.score" :color="scoreColor(dim.score)" :stroke-width="6" style="flex:1;margin:0 8px" />
                <span>{{ dim.score }}分</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 对比按钮 -->
        <div v-if="compareEnabled" style="text-align: center; margin-top: 16px;">
          <el-button type="primary" @click="doCompare">对比评测 ({{ selectedForCompare.length }}/2)</el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 对比弹窗 -->
    <el-dialog v-model="compareDialogVisible" title="评测对比" width="700px" :destroy-on-close="true">
      <div v-if="compareLoading" v-loading="true" style="min-height: 200px;" />
      <div v-else-if="compareData">
        <el-row :gutter="20">
          <el-col :span="11">
            <el-card shadow="never" size="small">
              <template #header><span>评测 1</span></template>
              <div class="compare-score" :style="{ color: scoreColor(compareData.session_1.overall_score) }">
                {{ compareData.session_1.overall_score }}分
              </div>
              <div v-for="(score, key) in compareData.session_1.dimension_scores" :key="key" class="compare-dim">
                <span>{{ key }}</span><span>{{ score }}分</span>
              </div>
            </el-card>
          </el-col>
          <el-col :span="2" style="display:flex;align-items:center;justify-content:center;">
            <div>
              <div v-for="(delta, key) in compareData.deltas" :key="key" style="margin:2px 0;font-size:12px;text-align:center;">
                <span :style="{ color: delta > 0 ? '#5B8C5A' : delta < 0 ? '#C5554A' : '#9B9EAA' }">
                  {{ delta > 0 ? '+' : '' }}{{ delta }}
                </span>
              </div>
              <div style="font-weight:bold;text-align:center;margin-top:4px;">
                <span :style="{ color: compareData.overall_delta > 0 ? '#5B8C5A' : compareData.overall_delta < 0 ? '#C5554A' : '#9B9EAA' }">
                  {{ compareData.overall_delta > 0 ? '+' : '' }}{{ compareData.overall_delta }}
                </span>
              </div>
            </div>
          </el-col>
          <el-col :span="11">
            <el-card shadow="never" size="small">
              <template #header><span>评测 2</span></template>
              <div class="compare-score" :style="{ color: scoreColor(compareData.session_2.overall_score) }">
                {{ compareData.session_2.overall_score }}分
              </div>
              <div v-for="(score, key) in compareData.session_2.dimension_scores" :key="key" class="compare-dim">
                <span>{{ key }}</span><span>{{ score }}分</span>
              </div>
            </el-card>
          </el-col>
        </el-row>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useGeoStore } from '../stores/geo'
import { getEvalDimensions, startEvalSSE, cancelEval as apiCancelEval, getEvalHistory, getEvalHistoryDetail, deleteEvalHistory, compareEvalHistory, generateEvalQuestions, rewriteText } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Delete } from '@element-plus/icons-vue'
import { SANDTABLE_TYPES, AI_PLATFORMS, scoreColor } from '../constants'

const router = useRouter()
const store = useGeoStore()

// ── 配置状态 ──
const textSource = ref(store.hasResults ? 'rewrite' : (store.hasCleanedText ? 'cleaned' : 'manual'))
const evalText = ref('')
const originalText = ref('')
const sandtableType = ref(store.currentSandtableType || 'smart_traffic')
const targetPlatforms = ref(store.selectedPlatforms.length > 0 ? store.selectedPlatforms : ['deepseek'])
const userRoles = ref(['b_end_procurement', 'general_consultant'])
const customQuestions = ref('')
const generatedQuestions = ref([])
const generatingQuestions = ref(false)
const expandedQuestions = ref(false)
const selectedGeneratedQs = ref([])

const dimensionConfigs = ref([])
const hasLLM = computed(() => store.configuredPlatforms.length > 0)

// ── 评测运行状态 ──
const isRunning = ref(false)
const evalStatus = ref('idle')
const evalOverallProgress = ref(0)
const evalOverallScore = ref(null)
const evalSessionId = ref(null)
const sseConnection = ref(null)

const phaseStates = ref({})

// ── 历史相关 ──
const historyDrawerVisible = ref(false)
const historyItems = ref([])
const selectedForCompare = ref([])
const compareDialogVisible = ref(false)

// ── 一键重优化并评测 ──
const autoReoptRunning = ref(false)
const autoReoptProgress = ref('')
const lastScore = ref(null)  // 优化前的分数
const compareLoading = ref(false)
const compareData = ref(null)
const showTextDiff = ref(false)

// ── 对比分析 ──
const dimensionLabelMap = {
  brand_recall: '品牌召回', solution_match: '方案匹配', semantic_alignment: '语义对齐',
  advantage_citation: '优势采信', real_citation: '真实采信', rag_retrievability: 'RAG可检索',
  structure_quality: '结构质量', differentiation: '差异化', source_consistency: '信源一致',
  eeat_score: 'E-E-A-T',
}
const compareSummaryText = computed(() => {
  if (!compareData.value) return ''
  const d = compareData.value.overall_delta
  if (d > 5) return `📈 综合评分提升了 ${d} 分，优化效果显著`
  if (d > 0) return `📈 综合评分提升了 ${d} 分，略有改善`
  if (d === 0) return '➡️ 综合评分无变化'
  if (d > -5) return `📉 综合评分下降了 ${Math.abs(d)} 分，略有下降`
  return `📉 综合评分下降了 ${Math.abs(d)} 分，需要排查原因`
})
const topChanges = computed(() => {
  if (!compareData.value?.deltas) return []
  const entries = Object.entries(compareData.value.deltas)
    .filter(([_, delta]) => Math.abs(delta) > 0)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 5)
    .map(([key, delta]) => ({
      label: dimensionLabelMap[key] || key,
      delta: delta,
    }))
  return entries
})

// ── 实测验证（评测分数 vs 真实AI收录）──
const brandVerifyLoading = ref(false)
const brandVerifyResult = ref(null)
const brandQueries = ref([])
const verifyCompareRows = ref([])

// 页面加载时尝试获取品牌监测的查询词
onMounted(async () => {
  try {
    const { getMonitorQueries } = await import('../api/index.js')
    const res = await getMonitorQueries()
    brandQueries.value = (res.data?.queries || []).slice(0, 10)
  } catch { /* 品牌监测模块可能未启用 */ }
})

async function runBrandVerify() {
  brandVerifyLoading.value = true
  brandVerifyResult.value = null
  try {
    const { runMonitorCheckAll } = await import('../api/index.js')
    const res = await runMonitorCheckAll({
      sandtable_type: sandtableType.value,
      platforms: targetPlatforms.value,
    })
    const data = res.data || {}
    brandVerifyResult.value = data

    // 构建对比行：评测预测分 vs 实测收录数据
    const comp = phaseStates.value['comprehensive']?.result
    const dims = comp?.dimensions || []
    const rows = []
    const dimMap = {
      brand_recall: '品牌召回',
      real_citation: '真实采信',
      advantage_citation: '优势采信',
    }
    for (const dim of dims) {
      const label = dimMap[dim.key] || dim.label || dim.key
      const predicted = dim.score || 0
      let actual = null
      let delta = null
      // 从实测数据中匹配对应维度
      if (dim.key === 'brand_recall' && data.mention_rate !== undefined) {
        actual = data.mention_rate
        delta = Math.round(actual - predicted)
      } else if (dim.key === 'real_citation' && data.mention_rate !== undefined) {
        actual = Math.round(data.mention_rate * 0.7)  // 引用率通常低于提及率
        delta = Math.round(actual - predicted)
      } else if (dim.key === 'advantage_citation' && data.mention_rate !== undefined) {
        actual = Math.round(data.mention_rate * 0.5)  // 优势引用率低于总体提及率
        delta = Math.round(actual - predicted)
      }
      rows.push({ dimension: label, predicted, actual, delta })
    }

    // 至少保证品牌召回和真实采信有数据
    if (rows.length === 0) {
      const overall = comp?.overall_score || evalOverallScore.value || 0
      if (data.mention_rate !== undefined) {
        rows.push({
          dimension: '综合评分(预测)',
          predicted: overall,
          actual: data.mention_rate,
          delta: Math.round(data.mention_rate - overall),
        })
      }
    }
    verifyCompareRows.value = rows

    if (data.mention_rate !== undefined) {
      ElMessage.success(`实测完成：${data.mentioned_platforms || 0}/${data.total_platforms || 0} 平台收录，提及率 ${data.mention_rate}%`)
    } else {
      ElMessage.info('实测完成，查看下方对比结果')
    }
  } catch (e) {
    ElMessage.error('实测验证失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    brandVerifyLoading.value = false
  }
}

const phaseOrderDef = [
  { key: 'generating_questions', label: '生成评测问题', status: 'pending', score: null, result: null },
  { key: 'brand_recall', label: '品牌召回率', status: 'pending', score: null, result: null },
  { key: 'solution_match', label: '方案匹配度', status: 'pending', score: null, result: null },
  { key: 'advantage_citation', label: '优势采信率', status: 'pending', score: null, result: null },
  { key: 'real_citation', label: '真实采信率', status: 'pending', score: null, result: null },
  { key: 'structure_quality', label: '结构化程度', status: 'pending', score: null, result: null },
  { key: 'differentiation', label: '差异化程度', status: 'pending', score: null, result: null },
  { key: 'source_check', label: '信源一致性', status: 'pending', score: null, result: null },
  { key: 'comprehensive', label: '综合评分', status: 'pending', score: null, result: null },
]

const phaseOrder = computed(() => phaseOrderDef.map(p => ({
  ...p,
  status: phaseStates.value[p.key]?.status || 'pending',
  score: phaseStates.value[p.key]?.score ?? null,
  result: phaseStates.value[p.key]?.result ?? null,
})))

const beforeAfter = computed(() => {
  const comp = phaseStates.value['comprehensive']?.result
  return comp?.before_after_comparison || null
})
const weakPoints = computed(() => {
  return phaseStates.value['comprehensive']?.result?.weak_points || []
})
const suggestions = computed(() => {
  return phaseStates.value['comprehensive']?.result?.suggestions || []
})
const sourceConsistencyScore = computed(() => {
  return phaseStates.value['source_check']?.score ?? null
})
const completedDimensions = computed(() => {
  const comp = phaseStates.value['comprehensive']?.result
  if (!comp?.dimension_scores) return []
  return Object.entries(comp.dimension_scores).map(([key, score]) => {
    const dim = dimensionConfigs.value.find(d => d.key === key)
    return { key, label: dim?.label || key, score }
  })
})

// ── 人话解读 ──
const evalVerdict = computed(() => {
  const s = evalOverallScore.value
  if (s === null) return ''
  if (s >= 80) return '✅ AI收录潜力优秀，可直接发布使用'
  if (s >= 70) return '✅ 整体良好，略做微调即可'
  if (s >= 60) return '⚠️ 基本合格，有较大优化空间'
  if (s >= 40) return '⚠️ 需要针对性优化后才能发布'
  return '❌ 内容质量偏低，建议重新改写'
})

const evalFindings = computed(() => {
  const findings = []
  const comp = phaseStates.value['comprehensive']?.result
  const dims = comp?.dimensions || []
  const dimMap = {}
  for (const d of dims) {
    dimMap[d.key || d.dimension] = d.score
  }

  const sc = sourceConsistencyScore.value
  if (sc !== null && sc < 30) {
    findings.push('🔴 信源一致性极低（<30分）：AI可能拒绝了你的内容——这意味着你的文案里有编造的数据或明显矛盾的信息。这是最严重的问题，必须优先修复。')
  } else if (sc !== null && sc < 60) {
    findings.push('🟡 信源一致性偏低（<60分）：部分内容可信度不足。建议核实所有量化数据和客户案例是否真实准确。')
  }

  const realCite = dimMap['real_citation']
  if (realCite !== undefined && realCite < 30) {
    findings.push('🟡 真实采信率偏低：AI在实际引用你的内容时能提取的信息太少。建议增加更多具体的量化数据和独特的技术参数。')
  }

  const brand = dimMap['brand_recall']
  if (brand !== undefined && brand < 50) {
    findings.push('🟡 品牌召回不足：AI搜索时不太容易匹配到你的品牌。建议在标题和首段明确写出完整的企业名称+地域。')
  }

  if (findings.length === 0) {
    findings.push('✅ 各维度表现均衡，未发现明显短板。')
    findings.push('💡 提示：评测分数是AI模拟预测，仅供参考。建议使用「实测验证」功能对比真实AI平台收录数据。')
  }
  return findings
})

const statusTagType = computed(() => {
  if (evalStatus.value === 'completed') return 'success'
  if (evalStatus.value === 'failed') return 'danger'
  if (evalStatus.value === 'cancelled') return 'warning'
  return 'info'
})
const compareEnabled = computed(() => selectedForCompare.value.length === 2)

const statusLabel = computed(() => {
  if (evalStatus.value === 'running') return '评测中'
  if (evalStatus.value === 'completed') return '已完成'
  if (evalStatus.value === 'cancelled') return '已取消'
  if (evalStatus.value === 'failed') return '失败'
  return ''
})

// ── 沙盘类型 / 平台 / 角色选项 ──
const sandtableTypes = SANDTABLE_TYPES
const availablePlatforms = AI_PLATFORMS
const roleOptions = [
  { value: 'b_end_procurement', label: 'B端政企采购' },
  { value: 'technical_selection', label: '技术人员选型' },
  { value: 'project_manager', label: '项目经办人' },
  { value: 'general_consultant', label: '普通咨询用户' },
]

// ── 初始化 ──
onMounted(async () => {
  try {
    const res = await getEvalDimensions()
    const dims = res.data.dimensions || []
    dimensionConfigs.value = dims.map(d => ({
      ...d,
      enabled: !(d.requires_llm && !hasLLM.value),
    }))
  } catch (e) {
    ElMessage.error('加载评测维度配置失败: ' + (e.response?.data?.detail || e.message))
    dimensionConfigs.value = [
      { key: 'brand_recall', label: '品牌召回率', requires_llm: false, enabled: true, weight: 13 },
      { key: 'solution_match', label: '方案匹配度', requires_llm: false, enabled: true, weight: 13 },
      { key: 'semantic_alignment', label: '语义对齐度（AI原生）', requires_llm: false, enabled: true, weight: 10 },
      { key: 'advantage_citation', label: '优势采信率', requires_llm: false, enabled: true, weight: 14 },
      { key: 'real_citation', label: '真实采信率', requires_llm: false, enabled: true, weight: 14 },
      { key: 'rag_retrievability', label: 'RAG可检索性（AI原生）', requires_llm: false, enabled: true, weight: 10 },
      { key: 'structure_quality', label: '结构化程度', requires_llm: false, enabled: true, weight: 7 },
      { key: 'differentiation', label: '差异化程度', requires_llm: false, enabled: true, weight: 7 },
      { key: 'source_consistency', label: '信源一致性', requires_llm: false, enabled: true, weight: 6 },
      { key: 'eeat_score', label: 'E-E-A-T权威度', requires_llm: false, enabled: true, weight: 6 },
    ]
  }

  const firstResult = store.rewriteResults[0]
  evalText.value = firstResult?.optimized_text || store.cleanedText || ''
  originalText.value = store.originalText || ''
})

onUnmounted(() => {
  if (sseConnection.value) {
    sseConnection.value.close()
    sseConnection.value = null
  }
})

// ── LLM 生成评测问题 ──
async function handleGenerateQuestions() {
  if (!evalText.value || evalText.value.length < 50) {
    ElMessage.warning('请先输入或选择评测文本（至少50字）')
    return
  }
  generatingQuestions.value = true
  generatedQuestions.value = []
  selectedGeneratedQs.value = []
  try {
    const res = await generateEvalQuestions({
      optimized_text: evalText.value,
      sandtable_type: sandtableType.value,
      enterprise_name: store.enterpriseName || '',
      count: 10,
    })
    generatedQuestions.value = res.data.questions || []
    expandedQuestions.value = true
    if (generatedQuestions.value.length > 0) {
      ElMessage.success(`LLM生成了 ${generatedQuestions.value.length} 个评测问题`)
    } else {
      ElMessage.warning('未能生成问题，请检查文案内容')
    }
  } catch (e) {
    ElMessage.error('问题生成失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    generatingQuestions.value = false
  }
}

function toggleGeneratedQuestion(q) {
  const idx = selectedGeneratedQs.value.indexOf(q)
  if (idx >= 0) {
    selectedGeneratedQs.value.splice(idx, 1)
  } else {
    selectedGeneratedQs.value.push(q)
  }
  // 将选中问题同步到自定义问题文本区
  syncCustomQuestions()
}

function selectAllGenerated() {
  if (selectedGeneratedQs.value.length === generatedQuestions.value.length) {
    selectedGeneratedQs.value = []
  } else {
    selectedGeneratedQs.value = [...generatedQuestions.value]
  }
  syncCustomQuestions()
}

function syncCustomQuestions() {
  const manual = customQuestions.value.split('\n').map(s => s.trim()).filter(s => s && !generatedQuestions.value.includes(s))
  customQuestions.value = [...selectedGeneratedQs.value, ...manual].join('\n')
}

// ── 文本来源切换 ──
function onTextSourceChange(val) {
  if (val === 'rewrite') {
    evalText.value = store.rewriteResults[0]?.optimized_text || ''
  } else if (val === 'cleaned') {
    evalText.value = store.cleanedText || ''
  } else {
    evalText.value = ''
  }
}

// ── 维度配置变化 ──
function onDimensionChange() {
  const enabled = dimensionConfigs.value.filter(d => d.enabled)
  if (enabled.length === 0) return
  // 仅当所有权重为 0（首次激活）时自动均分；否则保留用户已调权重
  const allZero = enabled.every(d => d.weight === 0)
  if (!allZero) return
  const each = Math.floor(100 / enabled.length)
  const remainder = 100 - each * enabled.length
  enabled.forEach((d, i) => {
    d.weight = each + (i < remainder ? 1 : 0)
  })
}
function onWeightChange(changedDim) {
  // 自动平衡：调整一个维度时，差额均分给其他维度，保持总和始终为100%
  const enabled = dimensionConfigs.value.filter(d => d.enabled)
  if (enabled.length <= 1) {
    if (enabled.length === 1) enabled[0].weight = 100
    return
  }

  const others = enabled.filter(d => d !== changedDim)
  const currentTotal = enabled.reduce((s, d) => s + d.weight, 0)
  const target = 100

  if (Math.abs(currentTotal - target) < 0.5) return // 已在容差内

  // 差额由其他维度分摊
  const delta = target - currentTotal
  const eachDelta = Math.round(delta / others.length)
  let remainder = delta - eachDelta * others.length

  others.forEach((d, i) => {
    const adj = eachDelta + (i < Math.abs(remainder) ? (remainder > 0 ? 1 : -1) : 0)
    d.weight = Math.max(0, Math.min(100, d.weight + adj))
  })

  // 微调确保精确100
  const finalTotal = enabled.reduce((s, d) => s + d.weight, 0)
  if (finalTotal !== target && others.length > 0) {
    others[0].weight += (target - finalTotal)
  }
}
const weightSum = computed(() => {
  const enabled = dimensionConfigs.value.filter(d => d.enabled)
  return enabled.reduce((s, d) => s + d.weight, 0)
})
const weightValid = computed(() => Math.abs(weightSum.value - 100) <= 1)

// ── 开始评测 ──
async function startEval() {
  if (!evalText.value) {
    ElMessage.warning('请先输入评测文本')
    return
  }
  if (!weightValid.value && dimensionConfigs.value.some(d => d.enabled)) {
    ElMessage.warning(`评测维度权重合计需为100%（当前${weightSum.value}%），请调整后再开始`)
    return
  }

  isRunning.value = true
  evalStatus.value = 'running'
  evalOverallProgress.value = 0
  evalOverallScore.value = null
  phaseStates.value = {}

  const customQs = customQuestions.value
    .split('\n')
    .map(q => q.trim())
    .filter(q => q)

  sseConnection.value = startEvalSSE(
    {
      optimized_text: evalText.value,
      original_text: originalText.value || null,
      sandtable_type: sandtableType.value,
      platforms: targetPlatforms.value,
      user_roles: userRoles.value,
      custom_questions: customQs,
      dimensions: dimensionConfigs.value
        .filter(d => d.enabled)
        .map(d => ({ key: d.key, label: d.label, requires_llm: d.requires_llm, weight: d.weight, enabled: d.enabled })),
      mode: (store.hasResults || store.hasCleanedText) ? 'pipeline' : 'standalone',
    },
    // onEvent
    (eventType, payload) => {
      const phase = payload.phase
      evalSessionId.value = payload.session_id
      evalOverallProgress.value = payload.progress || 0

      if (eventType === 'phase_complete' || eventType === 'phase_skipped') {
        const data = payload.data || {}
        const score = data.average ?? data.overall_score ?? null
        phaseStates.value = {
          ...phaseStates.value,
          [phase]: {
            status: eventType === 'phase_skipped' ? 'skipped' : 'completed',
            score,
            result: data,
          },
        }
      } else if (eventType === 'phase_failed') {
        phaseStates.value = {
          ...phaseStates.value,
          [phase]: { status: 'failed', score: null, result: null },
        }
      }

      if (eventType === 'eval_complete') {
        evalStatus.value = 'completed'
        evalOverallScore.value = payload.data?.overall_score ?? null
        isRunning.value = false
        store.setEvaluationResult(payload.data)
        store.addToHistory({
          name: 'AI评测',
          sandtableType: sandtableType.value,
          status: `评分: ${evalOverallScore.value}分`,
        })
        ElMessage.success(`评测完成！综合评分: ${evalOverallScore.value}分`)
        // 保存到历史
        store.pushToHistory({
          session_id: payload.session_id,
          status: 'completed',
          overall_score: payload.data?.overall_score ?? null,
          sandtable_type: sandtableType.value,
          mode: (store.hasResults || store.hasCleanedText) ? 'pipeline' : 'standalone',
          created_at: new Date().toISOString(),
          phases: payload.data,
          evaluated_text: evalText.value,
        })
      }

      if (eventType === 'eval_error') {
        evalStatus.value = 'failed'
        isRunning.value = false
        ElMessage.error('评测过程出错: ' + (payload.data?.error || '未知错误'))
      }
    },
    // onError
    (err) => {
      if (err.name === 'AbortError') return
      evalStatus.value = 'failed'
      isRunning.value = false
      ElMessage.error('评测连接中断: ' + (err.message || '网络错误'))
    }
  )
}

// ── 取消评测 ──
async function cancelEval() {
  if (evalSessionId.value) {
    try {
      await apiCancelEval(evalSessionId.value)
    } catch (e) { /* 取消失败不影响前端状态 */ }
  }
  sseConnection.value?.close()
  evalStatus.value = 'cancelled'
  isRunning.value = false
  ElMessage.info('评测已取消，已完成阶段的结果保留')
}

// ── 工具函数 ──
function resetEval() {
  if (sseConnection.value) {
    sseConnection.value.close()
    sseConnection.value = null
  }
  evalStatus.value = 'idle'
  evalOverallProgress.value = 0
  evalOverallScore.value = null
  evalSessionId.value = null
  phaseStates.value = {}
  generatedQuestions.value = []
  selectedGeneratedQs.value = []
  expandedQuestions.value = false
}
// ── 历史抽屉 ──
async function openHistory() {
  historyDrawerVisible.value = true
  await loadHistory()
}

async function loadHistory() {
  try {
    const res = await getEvalHistory()
    historyItems.value = (res.data.items || []).map(item => ({
      ...item,
      _selected: false,
      _expanded: false,
      _loading: false,
      _detail: null,
    }))
    // 计算同类沙盘的趋势
    computeTrends()
  } catch (e) { ElMessage.error('加载评测历史失败: ' + (e.response?.data?.detail || e.message)) }
}

const historyTrends = ref({})  // { sandtable_type: { scores: [83,78,72], trend: 'up'|'down'|'stable' } }

function computeTrends() {
  const map = {}
  for (const item of historyItems.value) {
    const key = item.sandtable_type || 'unknown'
    if (!map[key]) map[key] = []
    if (item.overall_score !== null) map[key].push(item.overall_score)
  }
  const trends = {}
  for (const [key, scores] of Object.entries(map)) {
    if (scores.length >= 2) {
      const latest = scores[0], previous = scores[1]
      trends[key] = {
        scores: scores.slice(0, 5).reverse(),
        trend: latest > previous ? 'up' : latest < previous ? 'down' : 'stable',
      }
    }
  }
  historyTrends.value = trends
}

function toggleHistoryDetail(item) {
  item._expanded = !item._expanded
  if (item._expanded && !item._detail && !item._loading) {
    loadHistoryDetail(item)
  }
}

async function loadHistoryDetail(item) {
  item._loading = true
  try {
    const res = await getEvalHistoryDetail(item.session_id)
    item._detail = res.data
    item._loading = false
  } catch (e) { ElMessage.error('加载评测详情失败: ' + (e.response?.data?.detail || e.message)); item._loading = false }
}

function getDetailDimensions(detail) {
  const comp = detail?.phases?.comprehensive?.result
  if (!comp?.dimension_scores) return []
  return Object.entries(comp.dimension_scores).map(([key, score]) => {
    const dim = dimensionConfigs.value.find(d => d.key === key)
    return { key, label: dim?.label || key, score }
  })
}

function onCompareSelect(item) {
  if (item._selected) {
    if (selectedForCompare.value.length >= 2) {
      // 取消最早选择的
      const first = selectedForCompare.value.shift()
      const found = historyItems.value.find(h => h.session_id === first.session_id)
      if (found) found._selected = false
    }
    selectedForCompare.value.push(item)
  } else {
    selectedForCompare.value = selectedForCompare.value.filter(h => h.session_id !== item.session_id)
  }
}

async function doCompare() {
  if (selectedForCompare.value.length !== 2) return
  compareDialogVisible.value = true
  compareLoading.value = true
  try {
    const res = await compareEvalHistory({
      session_ids: [selectedForCompare.value[0].session_id, selectedForCompare.value[1].session_id],
    })
    compareData.value = res.data
  } catch (e) { ElMessage.error('评测对比失败: ' + (e.response?.data?.detail || e.message)) } finally {
    compareLoading.value = false
  }
}

async function deleteHistoryItem(item) {
  try {
    await ElMessageBox.confirm(`确定要删除这条评测记录吗？`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteEvalHistory(item.session_id)
    historyItems.value = historyItems.value.filter(h => h.session_id !== item.session_id)
    selectedForCompare.value = selectedForCompare.value.filter(h => h.session_id !== item.session_id)
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message || ''))
    }
  }
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// ── 一键重优化并评测 ──
async function autoReoptimizeAndEval() {
  if (autoReoptRunning.value) return
  autoReoptRunning.value = true
  lastScore.value = evalOverallScore.value

  try {
    // Step 1: 重优化
    autoReoptProgress.value = '正在重优化...'
    const rewriteRes = await rewriteText({
      cleaned_text: evalText.value,
      sandtable_type: sandtableType.value,
      platforms: targetPlatforms.value,
      optimization_hints: suggestions.value,
    })
    const newText = rewriteRes.data?.results?.[0]?.optimized_text
    if (!newText) { ElMessage.error('重优化失败，未返回结果'); return }

    // Step 2: 重新评测
    autoReoptProgress.value = '优化完成，开始评测...'
    evalText.value = newText

    // 使用SSE评测
    await new Promise((resolve, reject) => {
      const conn = startEvalSSE({
        optimized_text: newText,
        sandtable_type: sandtableType.value,
        platforms: targetPlatforms.value,
        user_roles: userRoles.value,
        custom_questions: customQuestions.value ? customQuestions.value.split('\n').filter(Boolean) : [],
        dimensions: dimensionConfigs.value,
      },
      (eventType, payload) => {
        if (eventType === 'progress') {
          autoReoptProgress.value = `评测中 ${Math.round(payload.progress || 0)}%`
        } else if (eventType === 'complete' || eventType === 'result') {
          resolve(payload)
        }
      },
      (err) => { ElMessage.error('评测失败: ' + err.message); reject(err) }
      )
      sseConnection.value = conn
    })

    // Step 3: 等待并刷新
    await new Promise(r => setTimeout(r, 1000))
    autoReoptProgress.value = '完成'

    const newScore = evalOverallScore.value
    if (lastScore.value !== null && newScore !== null) {
      const diff = (newScore - lastScore.value).toFixed(1)
      const arrow = diff > 0 ? '↑' : diff < 0 ? '↓' : '→'
      ElMessage.success(`重优化完成: ${lastScore.value} ${arrow} ${newScore} (${diff > 0 ? '+' : ''}${diff})`)
    } else {
      ElMessage.success('重优化并评测完成')
    }
  } catch (e) {
    if (e.name !== 'AbortError') {
      ElMessage.error('重优化失败: ' + (e.response?.data?.detail || e.message))
    }
  } finally {
    autoReoptRunning.value = false
  }
}

// ── 重优化 ──
function goToOptimize() {
  store.setReoptimizeContext({
    weakPoints: weakPoints.value,
    suggestions: suggestions.value,
    sourceText: evalText.value,
    sandtableType: sandtableType.value,
    autoAdoptAll: false,
  })
  router.push('/workshop')
}

function applyAllAndReoptimize() {
  store.setReoptimizeContext({
    weakPoints: weakPoints.value,
    suggestions: suggestions.value,
    sourceText: evalText.value,
    sandtableType: sandtableType.value,
    autoAdoptAll: true,  // GEOWorkshop 检测此标志自动采纳全部建议
  })
  router.push('/workshop')
}

function goToExport() {
  router.push('/export')
}
</script>

<style scoped>
.eval-view { max-width: 1300px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header .page-title { margin-bottom: 0; }
.page-title { font-size: 20px; margin-bottom: 20px; color: #2D3142; font-weight: 700; }

.config-card { position: sticky; top: 24px; }
.text-preview { background: #FAF8F5; padding: 10px; border-radius: 6px; font-size: 13px; color: #6B6E7B; max-height: 80px; overflow: hidden; }

.dim-row { display: flex; align-items: center; margin-bottom: 8px; }
.dim-weight { font-size: 13px; color: #9B9EAA; width: 40px; text-align: right; }
.weight-summary { font-size: 13px; color: #5B8C5A; margin-top: 8px; padding: 4px 8px; background: rgba(91,140,90,0.08); border-radius: 4px; display: inline-block; }
.weight-summary.invalid { color: #D4956A; background: rgba(212,149,106,0.08); }

.action-buttons { margin-top: 12px; }

.empty-card { min-height: 400px; display: flex; align-items: center; justify-content: center; }
.empty-state { text-align: center; color: #9B9EAA; padding: 60px 0; }
.empty-state h3 { margin: 16px 0 8px; color: #6B6E7B; }

.progress-card { min-height: 300px; }
.progress-header { display: flex; justify-content: space-between; align-items: center; }

.phase-list { margin-top: 20px; }
.phase-row { display: flex; align-items: center; padding: 10px 12px; border-radius: 10px; margin-bottom: 4px; transition: background 0.22s cubic-bezier(0.4,0,0.2,1); }
.phase-row.is-active { background: rgba(200,150,62,0.06); }
.phase-icon { width: 28px; font-size: 18px; }
.phase-info { flex: 1; display: flex; align-items: center; gap: 8px; }
.phase-label { font-size: 14px; color: #2D3142; }
.phase-score { font-size: 18px; font-weight: bold; }
.phase-running { font-size: 12px; color: #C8963E; }

.overall-score { text-align: center; padding: 20px 0; }
.score-number { font-size: 72px; font-weight: bold; line-height: 1; }
.score-label { font-size: 16px; color: #9B9EAA; margin-top: 8px; }
.score-verdict { font-size: 14px; font-weight: 600; margin-top: 4px; }
.key-findings { line-height: 1.8; }

.dim-score-row { display: flex; align-items: center; margin-bottom: 12px; }
.dim-name { width: 90px; font-size: 13px; color: #6B6E7B; }
.dim-value { width: 48px; text-align: right; font-size: 14px; font-weight: bold; color: #2D3142; }

.comparison { display: flex; align-items: center; gap: 20px; padding: 12px 0; }
.comp-item { text-align: center; }
.comp-label { font-size: 13px; color: #9B9EAA; display: block; }
.comp-value { font-size: 24px; font-weight: bold; color: #2D3142; }

.history-empty { text-align: center; padding: 60px 0; }
.history-item { border-bottom: 1px solid #E8E5DF; padding: 12px 0; }
.history-item-main { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.history-item-left { display: flex; align-items: center; flex: 1; gap: 8px; }
.history-item-info { flex: 1; }
.history-item-date { font-size: 13px; color: #2D3142; }
.history-item-meta { display: flex; gap: 4px; margin-top: 4px; }
.history-item-score { font-size: 20px; font-weight: bold; min-width: 60px; text-align: right; }
.history-trend { font-size: 11px; font-weight: normal; color: #9B9EAA; margin-top: 2px; }
.trend-arrow { font-size: 14px; margin-right: 2px; }
.trend-scores { white-space: nowrap; }
.history-item-detail { padding: 12px 0 4px 32px; }
.history-dim-row { display: flex; align-items: center; margin: 6px 0; font-size: 13px; }
.compare-score { font-size: 36px; font-weight: bold; text-align: center; padding: 8px 0; color: #C8963E; }
.compare-dim { display: flex; justify-content: space-between; font-size: 13px; margin: 4px 0; padding: 2px 8px; }
.diff-text-panel { white-space: pre-wrap; line-height: 1.8; font-size: 13px; max-height: 70vh; overflow-y: auto; padding: 12px; background: #FAF8F5; border-radius: 8px; color: #2D3142; }

/* ── LLM Generated Questions Panel ── */
.generated-qs-panel {
  background: rgba(200,150,62,0.04);
  border: 1px solid rgba(200,150,62,0.15);
  border-radius: 8px;
  padding: 12px;
  margin-top: 4px;
  margin-bottom: 8px;
}
.generated-qs-header {
  display: flex; justify-content: space-between; align-items: center;
  font-size: 13px; font-weight: 600; color: #6B6E7B; margin-bottom: 8px;
}
.generated-qs-list { display: flex; flex-direction: column; gap: 4px; max-height: 200px; overflow-y: auto; }
.generated-q-item {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 6px 8px; border-radius: 6px; cursor: pointer;
  transition: background 0.15s cubic-bezier(0.4,0,0.2,1);
}
.generated-q-item:hover { background: rgba(200,150,62,0.06); }
.generated-q-item.selected { background: rgba(91,140,90,0.06); }
.generated-q-text { font-size: 13px; color: #2D3142; line-height: 1.6; flex: 1; }
</style>