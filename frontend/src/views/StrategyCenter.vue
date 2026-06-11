<template>
  <div class="strategy-center">
    <div class="page-header">
      <h2>策略中心</h2>
      <p>平台规则监测 · 竞品情报 · 关键词策略</p>
    </div>

    <el-tabs v-model="activeTab" type="border-card">
      <!-- Tab 1: 平台规则监测 -->
      <el-tab-pane label="平台监测" name="platform">
        <div class="tab-toolbar">
          <el-input v-model="platformSearch" placeholder="搜索平台..." size="small" style="width:200px;" clearable />
          <el-select v-model="platformCategory" size="small" style="width:140px;margin-left:12px;" placeholder="分类筛选" clearable>
            <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
          </el-select>
          <el-button size="small" type="primary" style="margin-left:12px;" @click="triggerCheckAll" :loading="checkingAll">
            全量检查
          </el-button>
          <el-button size="small" style="margin-left:8px;" @click="schedulerRunning ? stopSchedulerAction() : startSchedulerAction()">
            {{ schedulerRunning ? '停止' : '启动' }}自动监测
          </el-button>
          <el-tag size="small" :type="schedulerRunning ? 'success' : 'info'" style="margin-left:8px;">
            {{ schedulerRunning ? '监测中' : '已停止' }}
          </el-tag>
        </div>

        <div v-if="platforms.length === 0 && !platformSearch && !platformCategory" style="text-align:center;padding:40px;color:#c0c4cc;">
          <p>暂无平台数据，请先在后端初始化平台规则</p>
        </div>
        <div v-else-if="filteredPlatforms.length === 0" style="text-align:center;padding:40px;color:#c0c4cc;">
          <p>无匹配平台</p>
        </div>
        <el-row :gutter="16" style="margin-top:16px;" v-else>
          <el-col :span="8" v-for="p in filteredPlatforms" :key="p.id" style="margin-bottom:16px;">
            <el-card shadow="hover" :class="{ 'platform-alert': p.alert }">
              <template #header>
                <div class="plat-card-header">
                  <span class="plat-name">{{ p.name }}</span>
                  <el-tag :type="p.alert ? 'danger' : 'success'" size="small">
                    {{ p.alert ? '有变动' : '正常' }}
                  </el-tag>
                </div>
              </template>
              <div class="plat-meta">
                <span class="plat-category">{{ p.category }}</span>
                <span class="plat-date" v-if="p.last_checked">{{ formatDate(p.last_checked) }}</span>
                <el-tag v-if="p.data_source === 'web_search'" size="small" type="success" effect="plain">最新搜索</el-tag>
                <el-tag v-else-if="p.data_source === 'llm_knowledge'" size="small" type="warning" effect="plain">LLM知识</el-tag>
              </div>
              <div class="plat-meta" v-if="p.knowledge_cutoff" style="margin-top:2px;">
                <span style="font-size:11px;color:#9B9EAA;">数据时效: {{ p.knowledge_cutoff }}</span>
                <span v-if="p.data_source === 'llm_knowledge' && isDataStale(p.last_checked)" style="font-size:11px;color:#D4956A;margin-left:6px;">⚠️ 可能已过时</span>
              </div>
              <div class="plat-summary" v-if="p.summary">{{ p.summary.length > 120 ? p.summary.slice(0, 120) + '...' : p.summary }}</div>
              <div class="plat-summary" v-else style="color:#c0c4cc;">暂无规则摘要，点击「AI生成摘要」或「查看详情」</div>
              <div style="display:flex;gap:8px;margin-top:12px;">
                <el-button size="small" type="primary" link @click="openDetail(p)">查看详情</el-button>
                <el-button size="small" link @click="generateSummary(p)">AI生成摘要</el-button>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <!-- 平台详情弹窗 -->
        <el-dialog v-model="detailVisible" :title="detailPlatform?.name" width="820px" top="4vh" class="platform-detail-dialog">
          <template v-if="detailData">
            <!-- 顶栏：元信息 + 操作 -->
            <div class="pd-topbar">
              <div class="pd-meta">
                <span class="pd-meta-tag category">{{ detailData.category }}</span>
                <span class="pd-meta-tag status" :class="detailData.status === 'changed' ? 'alert' : 'ok'">
                  <span class="status-dot"></span>
                  {{ detailData.status === 'changed' ? '规则变动' : '正常运行' }}
                </span>
                <span class="pd-meta-time" v-if="detailData.last_checked">上次检查 {{ formatDate(detailData.last_checked) }}</span>
                <span class="pd-meta-tag" :class="detailData.current_rules?.data_source === 'web_search' ? 'ok' : 'alert'" style="margin-left:4px;" v-if="detailData.current_rules?.data_source">
                  {{ detailData.current_rules?.data_source === 'web_search' ? 'Web搜索' : 'LLM知识' }}
                </span>
                <span class="pd-meta-time" v-if="detailData.current_rules?.knowledge_cutoff" style="margin-left:4px;">知识截止: {{ detailData.current_rules?.knowledge_cutoff }}</span>
              </div>
              <div class="pd-actions">
                <el-button size="small" type="primary" plain @click="generateSummaryInDetail" :loading="checkingSingle">
                  <el-icon><Refresh /></el-icon> AI重新检查
                </el-button>
                <el-button size="small" :type="detailEditMode ? 'warning' : 'default'" plain @click="detailEditMode = !detailEditMode">
                  <el-icon><Edit /></el-icon> {{ detailEditMode ? '退出编辑' : '编辑规则' }}
                </el-button>
              </div>
            </div>

            <div class="pd-body">
              <!-- 规则摘要 -->
              <section class="pd-section">
                <h4 class="pd-section-hd">
                  <span class="pd-section-icon">
                    <el-icon><Reading /></el-icon>
                  </span>
                  规则摘要
                  <span class="pd-section-badge" v-if="detailEditMode">编辑中</span>
                </h4>
                <template v-if="detailEditMode">
                  <el-input v-model="editSummary" type="textarea" :rows="3" placeholder="输入该平台的核心收录与推荐规则..." class="pd-editor" />
                </template>
                <template v-else>
                  <div v-if="editSummary" class="pd-summary-box">
                    <p v-for="(line, i) in editSummary.split('\n').filter(l => l.trim())" :key="i" class="pd-summary-line">
                      {{ line }}
                    </p>
                  </div>
                  <div v-else class="pd-empty-block">
                    <el-icon><InfoFilled /></el-icon>
                    暂无规则数据，点击「AI重新检查」自动获取最新规则
                  </div>
                </template>
              </section>

              <!-- 规则要点 -->
              <section class="pd-section" v-if="editDetails.length > 0 || detailEditMode">
                <h4 class="pd-section-hd">
                  <span class="pd-section-icon">
                    <el-icon><List /></el-icon>
                  </span>
                  规则要点
                  <span class="pd-section-count">{{ editDetails.length }} 条</span>
                </h4>
                <template v-if="detailEditMode">
                  <div class="pd-points-editor">
                    <div v-for="(d, i) in editDetails" :key="i" class="pd-point-row">
                      <span class="pd-point-num">{{ i + 1 }}</span>
                      <el-input v-model="editDetails[i]" size="small" :placeholder="'第 ' + (i + 1) + ' 条规则要点'" />
                      <el-button size="small" type="danger" :icon="Delete" circle plain @click="editDetails.splice(i,1)" />
                    </div>
                    <el-button size="small" dashed @click="editDetails.push('')" class="pd-add-btn">
                      <el-icon><Plus /></el-icon> 添加要点
                    </el-button>
                  </div>
                </template>
                <template v-else>
                  <div class="pd-points-grid">
                    <div v-for="(d, i) in editDetails" :key="i" class="pd-point-chip">
                      <span class="pd-point-chip-num">{{ i + 1 }}</span>
                      <span class="pd-point-chip-text">{{ d }}</span>
                    </div>
                  </div>
                </template>
              </section>

              <!-- 影响 & 应对 -->
              <section class="pd-section" v-if="detailEditMode || editImpact || editResponse">
                <h4 class="pd-section-hd">
                  <span class="pd-section-icon">
                    <el-icon><Warning /></el-icon>
                  </span>
                  应对策略
                </h4>
                <el-row :gutter="20">
                  <el-col :span="12">
                    <div class="pd-sub-label">影响评估</div>
                    <el-input v-if="detailEditMode" v-model="editImpact" size="small" placeholder="此规则对GEO优化的影响..." />
                    <div v-else-if="editImpact" class="pd-text-card warning">{{ editImpact }}</div>
                    <div v-else class="pd-na">暂无评估</div>
                  </el-col>
                  <el-col :span="12">
                    <div class="pd-sub-label">应对措施</div>
                    <el-input v-if="detailEditMode" v-model="editResponse" size="small" placeholder="针对变化应采取的措施..." />
                    <div v-else-if="editResponse" class="pd-text-card success">{{ editResponse }}</div>
                    <div v-else class="pd-na">暂无措施</div>
                  </el-col>
                </el-row>
              </section>

              <!-- 保存按钮 -->
              <div v-if="detailEditMode" class="pd-save-bar">
                <el-button @click="detailEditMode = false">取消</el-button>
                <el-button type="primary" @click="saveDetail" :loading="savingDetail">保存并生效</el-button>
              </div>

              <!-- 变更历史 -->
              <section class="pd-section" v-if="detailData.change_log?.length">
                <h4 class="pd-section-hd">
                  <span class="pd-section-icon">
                    <el-icon><Clock /></el-icon>
                  </span>
                  变更历史
                  <span class="pd-section-count">{{ detailData.change_log.length }} 条记录</span>
                </h4>
                <div class="pd-timeline">
                  <div v-for="(log, i) in detailData.change_log.slice(0, 10)" :key="i" class="pd-tl-item" :class="{ first: i === 0 }">
                    <div class="pd-tl-marker">
                      <div class="pd-tl-dot" :class="{ latest: i === 0 }"></div>
                      <div class="pd-tl-line" v-if="i < detailData.change_log.length - 1 && i < 9"></div>
                    </div>
                    <div class="pd-tl-card">
                      <div class="pd-tl-date">{{ log.date }}</div>
                      <div class="pd-tl-field">
                        <span class="pd-tl-label">变更前</span>
                        <span class="pd-tl-value old">{{ log.previous }}</span>
                      </div>
                      <div class="pd-tl-field">
                        <span class="pd-tl-label">变更后</span>
                        <span class="pd-tl-value new">{{ log.new }}</span>
                      </div>
                      <div class="pd-tl-field" v-if="log.impact">
                        <span class="pd-tl-label">影响</span>
                        <span class="pd-tl-value">{{ log.impact }}</span>
                      </div>
                      <div class="pd-tl-field" v-if="log.response">
                        <span class="pd-tl-label">应对</span>
                        <span class="pd-tl-value">{{ log.response }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </section>
              <section class="pd-section" v-else>
                <div class="pd-empty-block">
                  <el-icon><Clock /></el-icon>
                  暂无变更记录 — 系统将持续监测平台规则变化
                </div>
              </section>
            </div>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- Tab 2: 竞品情报 -->
      <el-tab-pane label="竞品情报" name="competitor">
        <!-- 引导提示 -->
        <div class="guide-banner">
          <div class="guide-icon"><el-icon :size="20"><InfoFilled /></el-icon></div>
          <div class="guide-text">
            <strong>竞品情报</strong> — 追踪竞争对手在 AI 搜索中的曝光情况。发现竞品没有覆盖的内容空白，就是你的 GEO 优化机会。
          </div>
        </div>

        <div class="tab-toolbar">
          <el-button size="small" type="primary" @click="openCompDialog()">添加竞品</el-button>
          <el-button size="small" style="margin-left:8px;" :disabled="selectedComps.length < 2" @click="doCompare">对比分析 ({{ selectedComps.length }})</el-button>
          <el-button size="small" style="margin-left:8px;" :disabled="selectedComps.length < 1" @click="doGenerateReport">导出报告</el-button>
          <span v-if="selectedComps.length > 0" style="margin-left:8px;font-size:12px;color:#9B9EAA;">
            已选 {{ selectedComps.length }} 个 · <el-button size="small" link @click="selectedComps = []">取消选择</el-button>
          </span>
        </div>

        <el-empty v-if="competitors.length === 0" description="暂无竞品数据，添加第一个竞品开始追踪">
          <el-button type="primary" size="small" @click="openCompDialog()">添加竞品</el-button>
        </el-empty>

        <el-row :gutter="16" style="margin-top:16px;" v-else>
          <el-col :span="8" v-for="comp in competitors" :key="comp.id" style="margin-bottom:16px;">
            <el-card shadow="hover" :class="{ 'comp-selected': selectedComps.includes(comp.id) }" @click.stop>
              <template #header>
                <div class="card-header">
                  <span class="comp-name">{{ comp.name }}</span>
                  <el-button size="small" link type="primary" @click.stop="toggleCompSelect(comp.id)">
                    {{ selectedComps.includes(comp.id) ? '已选' : '选择' }}
                  </el-button>
                </div>
              </template>
              <div class="comp-meta">
                <div v-if="comp.industry" class="comp-row">
                  <span class="comp-label">行业</span><span>{{ comp.industry }}</span>
                </div>
                <div v-if="comp.website" class="comp-row">
                  <span class="comp-label">官网</span><a :href="comp.website" target="_blank">{{ comp.website }}</a>
                </div>
                <!-- AI平台存在感 -->
                <div class="comp-row" v-if="comp.platform_exposure && Object.keys(comp.platform_exposure).length">
                  <span class="comp-label">AI平台</span>
                  <span class="comp-platform-dots">
                    <span v-for="(level, plat) in comp.platform_exposure" :key="plat"
                      class="comp-plat-dot" :class="levelClass(level)" :title="plat + ': ' + level">
                      {{ plat.slice(0,2) }}
                    </span>
                  </span>
                </div>
                <div class="comp-row" v-if="comp.snapshots?.length">
                  <span class="comp-label">引用记录</span><span>{{ comp.snapshots.length }} 条</span>
                  <span v-if="latestSnapshot(comp)" style="color:#9B9EAA;margin-left:4px;">
                    · {{ latestSnapshot(comp) }}
                  </span>
                </div>
                <div class="comp-row" v-if="comp.content_features && Object.keys(comp.content_features).length">
                  <span class="comp-label">内容特征</span>
                  <span v-for="(v, k) in comp.content_features" :key="k" style="margin-right:4px;">
                    <el-tag size="small" :type="v === '高' ? 'success' : v === '中' ? 'warning' : 'info'">{{ k }}{{ v }}</el-tag>
                  </span>
                </div>
              </div>
              <div style="display:flex;gap:6px;margin-top:10px;">
                <el-button size="small" link type="primary" @click="openCompDialog(comp)">编辑</el-button>
                <el-button size="small" link @click="openSnapshotDialog(comp)">引用记录</el-button>
                <el-button size="small" link type="danger" @click="deleteComp(comp.id)">删除</el-button>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <!-- 竞品编辑弹窗 -->
        <el-dialog v-model="compDialogVisible" :title="editingComp?.id ? '编辑竞品' : '添加竞品'" width="560px">
          <el-form label-position="top" size="small">
            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="竞品名称">
                  <el-input v-model="compForm.name" placeholder="如：XX模型公司" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="行业">
                  <el-input v-model="compForm.industry" placeholder="如：沙盘模型定制" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="官网URL">
              <el-input v-model="compForm.website" placeholder="https://..." />
            </el-form-item>

            <el-form-item label="AI 平台曝光情况">
              <div class="platform-grid">
                <div v-for="p in exposurePlatforms" :key="p.key" class="platform-grid-item">
                  <span class="platform-grid-label">{{ p.label }}</span>
                  <el-select v-model="compForm.platform_exposure[p.label]" size="small" style="width:80px;">
                    <el-option label="高" value="高" />
                    <el-option label="中" value="中" />
                    <el-option label="低" value="低" />
                    <el-option label="未见" value="未见" />
                  </el-select>
                </div>
              </div>
            </el-form-item>

            <el-form-item label="内容特征">
              <div class="feature-grid">
                <div v-for="f in contentFeatureDims" :key="f.key" class="feature-grid-item">
                  <span class="feature-label">{{ f.label }}</span>
                  <el-select v-model="compForm.content_features[f.label]" size="small" style="width:80px;" clearable placeholder="--">
                    <el-option label="高" value="高" />
                    <el-option label="中" value="中" />
                    <el-option label="低" value="低" />
                  </el-select>
                </div>
              </div>
            </el-form-item>

            <el-form-item label="备注">
              <el-input v-model="compForm.notes" type="textarea" :rows="2" placeholder="其他需要记录的信息..." />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="compDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="saveComp" :loading="compSaving">保存</el-button>
          </template>
        </el-dialog>

        <!-- 引用记录弹窗 -->
        <el-dialog v-model="snapshotVisible" title="添加引用记录" width="420px">
          <div class="guide-banner" style="margin-bottom:16px;">
            <div class="guide-text" style="font-size:12px;">
              记录你在 AI 搜索中看到的竞品引用情况。例如在豆包搜索"武汉沙盘定制"，竞品是否出现在 AI 回答中？
            </div>
          </div>
          <el-form label-position="top" size="small">
            <el-form-item label="日期">
              <el-input v-model="snapForm.date" placeholder="2026-05-28" />
            </el-form-item>
            <el-form-item label="AI平台">
              <el-select v-model="snapForm.platform" style="width:100%;">
                <el-option v-for="p in aiPlatforms" :key="p" :label="p" :value="p" />
              </el-select>
            </el-form-item>
            <el-form-item label="搜索查询词">
              <el-input v-model="snapForm.query" placeholder="你在AI中搜索的关键词..." />
            </el-form-item>
            <el-form-item label="AI 是否引用了该竞品">
              <el-switch v-model="snapForm.citation_found" active-text="有引用" inactive-text="无引用" />
            </el-form-item>
            <el-form-item label="引用片段" v-if="snapForm.citation_found">
              <el-input v-model="snapForm.citation_snippet" type="textarea" :rows="2" placeholder="AI回答中引用该竞品的原文片段..." />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="snapForm.notes" placeholder="观察备注..." />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="snapshotVisible = false">取消</el-button>
            <el-button type="primary" @click="saveSnapshot" :loading="snapSaving">保存</el-button>
          </template>
        </el-dialog>

        <!-- 对比分析弹窗 -->
        <el-dialog v-model="compareVisible" title="竞品对比分析" width="860px" top="5vh">
          <el-table :data="compareTable" size="small" border v-if="compareData" style="margin-bottom:20px;">
            <el-table-column prop="name" label="竞品" width="130" fixed />
            <el-table-column v-for="plat in comparePlatforms" :key="plat" :label="plat" width="80">
              <template #default="{ row }">
                <span class="heat-cell" :class="row[plat] ? 'heat-' + row[plat] : ''">
                  {{ row[plat] || '无数据' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column prop="features" label="内容特征" min-width="180" />
          </el-table>
          <div v-if="compareData?.llm_analysis" class="llm-insight-cards">
            <div class="insight-card" v-if="compareData.llm_analysis.analysis">
              <h4>综合分析</h4>
              <p>{{ compareData.llm_analysis.analysis }}</p>
            </div>
            <el-row :gutter="12" v-if="compareData.llm_analysis.opportunities?.length">
              <el-col :span="12">
                <div class="insight-card opportunity">
                  <h4>机会点</h4>
                  <ul>
                    <li v-for="(op, i) in compareData.llm_analysis.opportunities" :key="i">{{ op }}</li>
                  </ul>
                </div>
              </el-col>
              <el-col :span="12">
                <div class="insight-card recommendation">
                  <h4>行动建议</h4>
                  <ul>
                    <li v-for="(rec, i) in (compareData.llm_analysis.recommendations || [])" :key="i">{{ rec }}</li>
                  </ul>
                </div>
              </el-col>
            </el-row>
            <div v-if="!compareData.llm_analysis.analysis && !compareData.llm_analysis.opportunities" style="white-space:pre-wrap;font-size:13px;line-height:1.7;">
              {{ compareData.llm_analysis.analysis || JSON.stringify(compareData.llm_analysis) }}
            </div>
          </div>
        </el-dialog>

        <!-- ── 竞品自动监控面板 ── -->
        <el-divider style="margin:24px 0 16px;" />
        <div class="monitor-panel">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
            <h4 style="margin:0;">🔍 竞品自动监控</h4>
            <div>
              <el-button size="small" type="primary" :loading="monitorRunning" @click="triggerMonitor">
                {{ monitorRunning ? '监控中...' : '立即执行监控' }}
              </el-button>
              <el-button size="small" @click="loadMonitorHistory" style="margin-left:8px;">刷新历史</el-button>
            </div>
          </div>
          <p style="font-size:12px;color:#9B9EAA;margin:0 0 12px;">
            自动探测竞品在AI平台上的引用情况，反推有效内容策略。周期：3天/次。
          </p>

          <!-- 最近监控结果 -->
          <el-alert v-if="monitorError" :title="monitorError" type="error" show-icon closable @close="monitorError=''" style="margin-bottom:12px;" />
          <el-alert v-if="monitorSuccess" :title="monitorSuccess" type="success" show-icon closable @close="monitorSuccess=''" style="margin-bottom:12px;" />

          <el-table v-if="monitorHistory.length > 0" :data="monitorHistory" size="small" stripe max-height="200">
            <el-table-column prop="date" label="日期" width="110" />
            <el-table-column prop="competitors_probed" label="竞品数" width="70" />
            <el-table-column prop="platforms_probed" label="平台数" width="70" />
            <el-table-column prop="total_alerts" label="变化告警" width="80">
              <template #default="{ row }">
                <el-tag v-if="row.total_alerts > 0" size="small" type="warning">{{ row.total_alerts }}</el-tag>
                <span v-else style="color:#9B9EAA;">0</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{ row }">
                <el-tag v-if="row.no_data" size="small" type="info">无数据</el-tag>
                <el-tag v-else-if="row.error" size="small" type="danger">错误</el-tag>
                <el-tag v-else size="small" type="success">完成</el-tag>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无监控数据，点击「立即执行监控」开始" :image-size="60" />
        </div>
      </el-tab-pane>

      <!-- Tab 3: 关键词策略 -->
      <el-tab-pane label="关键词策略" name="keywords">
        <!-- 引导提示 -->
        <div class="guide-banner">
          <div class="guide-icon"><el-icon :size="20"><InfoFilled /></el-icon></div>
          <div class="guide-text">
            <strong>关键词策略</strong> — 管理你的关键词矩阵，直接指导 GEO 内容改写。覆盖越精准，AI 搜索中优先推荐的概率越高。三类词：<em>品牌词</em>（用户搜你公司）、<em>场景词</em>（用户搜产品/服务）、<em>长尾词</em>（用户问具体问题）。
          </div>
        </div>

        <!-- 沙盘类型卡片选择器 -->
        <div class="sandtable-cards">
          <div v-for="t in sandtableTypes" :key="t.key"
            class="st-card" :class="{ active: kwSandtableType === t.key }"
            @click="kwSandtableType = t.key; loadKeywords()">
            <span class="st-card-icon">{{ t.label.slice(0,2) }}</span>
            <span class="st-card-label">{{ t.label }}</span>
          </div>
        </div>

        <div v-if="!kwSandtableType" style="text-align:center;padding:50px 0;color:#9B9EAA;">
          <el-icon :size="40" style="color:#dcdfe6;"><InfoFilled /></el-icon>
          <p style="margin-top:12px;">请先在上方选择一种沙盘类型</p>
        </div>

        <template v-else>
          <!-- 统计栏 -->
          <div class="kw-stats-bar">
            <div class="kw-stat">
              <span class="kw-stat-num">{{ totalKeywordCount }}</span>
              <span class="kw-stat-label">关键词总数</span>
            </div>
            <div class="kw-stat">
              <span class="kw-stat-num core">{{ coreKeywordCount }}</span>
              <span class="kw-stat-label">核心词</span>
            </div>
            <div class="kw-stat">
              <span class="kw-stat-num success">{{ optimizedKeywordCount }}</span>
              <span class="kw-stat-label">已优化</span>
            </div>
            <div class="kw-stat" v-if="kwExpandedList.length > 0">
              <span class="kw-stat-num warning">{{ kwExpandedList.length }}</span>
              <span class="kw-stat-label">待添加</span>
            </div>
            <div class="kw-actions-right">
              <el-button size="small" @click="kwAddVisible = true">添加关键词</el-button>
              <el-button size="small" type="primary" @click="expandByLLM" :loading="kwExpanding">LLM 智能扩展</el-button>
              <el-button size="small" @click="exportKeywordsCSVAction">导出 CSV</el-button>
              <el-button size="small" @click="openKwImport">导入 CSV</el-button>
            </div>
          </div>

          <!-- 三个分类面板 -->
          <el-row :gutter="16" style="margin-top:16px;">
            <el-col :span="8" v-for="cat in kwCategories" :key="cat.key">
              <div class="kw-cat-card">
                <div class="kw-cat-header">
                  <span class="kw-cat-title">{{ cat.label }}</span>
                  <el-tag size="small" round>{{ kwData[cat.key]?.length || 0 }}</el-tag>
                </div>
                <div class="kw-cat-body">
                  <div v-for="kw in kwData[cat.key]" :key="kw.word" class="kw-row">
                    <span class="kw-word-text" :title="kw.word">{{ kw.word }}</span>
                    <span class="kw-row-tags">
                      <span class="kw-weight-tag" :class="kw.weight">{{ weightLabel(kw.weight) }}</span>
                      <span class="kw-status-dot" :class="kw.status" :title="kw.status === 'optimized' ? '已优化' : '待优化'"></span>
                    </span>
                    <span class="kw-row-actions">
                      <el-button size="small" link @click="editKeyword(cat.key, kw)">
                        <el-icon><Edit /></el-icon>
                      </el-button>
                      <el-button size="small" link @click="removeKeyword(cat.key, kw.word)">
                        <el-icon><Delete /></el-icon>
                      </el-button>
                    </span>
                  </div>
                  <div v-if="!kwData[cat.key]?.length" class="kw-empty">暂无关键词</div>
                </div>
              </div>
            </el-col>
          </el-row>

          <!-- LLM扩展结果 -->
          <div v-if="kwExpandedList.length > 0" class="kw-expanded-panel">
            <div class="kw-expanded-header">
              <span>LLM 扩展结果（{{ kwExpandedList.length }} 个关键词）</span>
              <span>
                <el-button size="small" link @click="selectAllExpanded">全选</el-button>
                <el-button size="small" type="primary" @click="batchAddExpanded" :disabled="kwExpandedList.filter(k => k._selected).length === 0">
                  添加选中 ({{ kwExpandedList.filter(k => k._selected).length }})
                </el-button>
              </span>
            </div>
            <div class="kw-expanded-grid">
              <div v-for="kw in kwExpandedList" :key="kw.word" class="kw-expanded-item" :class="{ selected: kw._selected }" @click="kw._selected = !kw._selected">
                <span class="kw-exp-word">{{ kw.word }}</span>
                <span class="kw-exp-meta">{{ weightLabel(kw.weight) }} · {{ kw.search_intent || kw.category || '' }}</span>
              </div>
            </div>
          </div>

          <!-- CSV导入弹窗 -->
          <el-dialog v-model="kwImportVisible" title="导入 CSV 关键词" width="500px">
            <el-input v-model="kwImportText" type="textarea" :rows="8" placeholder="粘贴CSV内容：&#10;分类,关键词,权重,状态&#10;品牌词,武汉模型定制,core,optimized&#10;场景词,智慧交通沙盘方案,core,pending" />
            <div style="margin-top:8px;font-size:12px;color:#9B9EAA;">格式：分类,关键词,权重(core/secondary/longtail),状态(pending/optimized)</div>
            <template #footer>
              <el-button @click="kwImportVisible = false">取消</el-button>
              <el-button type="primary" @click="importKeywordsCSV" :loading="kwImporting">导入</el-button>
            </template>
          </el-dialog>
        </template>

        <!-- 添加/编辑关键词弹窗 -->
        <el-dialog v-model="kwAddVisible" :title="editingKw ? '编辑关键词' : '添加关键词'" width="420px" @closed="resetKwForm">
          <el-form label-position="top" size="small">
            <el-form-item label="关键词">
              <el-input v-model="kwForm.word" placeholder="输入关键词..." />
            </el-form-item>
            <el-form-item label="分类">
              <el-select v-model="kwForm.category" style="width:100%;" :disabled="!!editingKw">
                <el-option v-for="c in kwCategories" :key="c.key" :label="c.label" :value="c.key" />
              </el-select>
            </el-form-item>
            <el-form-item label="权重">
              <el-select v-model="kwForm.weight" style="width:100%;">
                <el-option label="核心词 — 最重要的目标词" value="core" />
                <el-option label="辅助词 — 次要覆盖词" value="secondary" />
                <el-option label="长尾词 — 自然搜索问句" value="longtail" />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="kwForm.status" style="width:100%;">
                <el-option label="待优化 — 尚未用于GEO改写" value="pending" />
                <el-option label="已优化 — 已用于GEO改写" value="optimized" />
              </el-select>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="resetKwForm(); kwAddVisible = false">取消</el-button>
            <el-button type="primary" @click="saveKeyword" :loading="kwSaving">保存</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Delete, Edit, Reading, List, InfoFilled, Warning, Clock, Plus } from '@element-plus/icons-vue'
import {
  listPlatforms, getPlatformDetail, updatePlatformRules, generateLLMSummary,
  checkAllPlatforms, checkSinglePlatform, getSchedulerStatus, startScheduler, stopScheduler,
  listSandtableTypes, getKeywords, addKeyword, deleteKeyword, updateKeyword,
  expandKeywords, exportKeywordsCSV,
  listCompetitors, createCompetitor, updateCompetitor, deleteCompetitor as apiDeleteCompetitor,
  addSnapshot, compareCompetitors, generateCompetitorReport,
} from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { AI_PLATFORMS, KEYWORD_CATEGORIES, SANDTABLE_TYPES } from '../constants'
import { triggerCompetitorMonitor, getCompetitorMonitorHistory } from '../api'

const activeTab = ref('platform')

// ── 平台监测 ──
const platforms = ref([])
const platformSearch = ref('')
const platformCategory = ref('')
const categories = ['AI大模型', 'AI搜索', '社媒平台', '短视频']

const filteredPlatforms = computed(() => {
  return platforms.value.filter(p => {
    if (platformSearch.value && !p.name.includes(platformSearch.value)) return false
    if (platformCategory.value && p.category !== platformCategory.value) return false
    return true
  })
})

const detailVisible = ref(false)
const detailEditMode = ref(false)
const detailPlatform = ref(null)
const detailData = ref(null)
const editSummary = ref('')
const editDetails = ref([])
const editImpact = ref('')
const editResponse = ref('')
const savingDetail = ref(false)
const checkingSingle = ref(false)

const checkingAll = ref(false)
const schedulerRunning = ref(false)

async function loadPlatforms() {
  try {
    const res = await listPlatforms()
    platforms.value = res.data.platforms || []
  } catch (e) { ElMessage.error('平台列表加载失败: ' + (e.response?.data?.detail || e.message)) }
}

async function triggerCheckAll() {
  checkingAll.value = true
  try {
    await checkAllPlatforms()
    ElMessage.success('全量平台规则检查已在后台启动，请稍后刷新查看结果')
    loadPlatforms()
  } catch (e) {
    ElMessage.error('检查启动失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    checkingAll.value = false
  }
}

async function startSchedulerAction() {
  try {
    await startScheduler(30)
    schedulerRunning.value = true
    ElMessage.success('自动监测已启动，每30分钟检查一次')
  } catch (e) {
    ElMessage.error('启动失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function stopSchedulerAction() {
  try {
    await stopScheduler()
    schedulerRunning.value = false
    ElMessage.success('自动监测已停止')
  } catch (e) {
    ElMessage.error('停止失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function checkSchedulerStatus() {
  try {
    const res = await getSchedulerStatus()
    schedulerRunning.value = res.data.running || false
  } catch { /* ignore */ }
}

async function openDetail(p) {
  detailPlatform.value = p
  detailEditMode.value = false
  try {
    const res = await getPlatformDetail(p.id)
    detailData.value = res.data
    editSummary.value = res.data.current_rules?.summary || ''
    editDetails.value = res.data.current_rules?.details || []
    editImpact.value = res.data.change_log?.[0]?.impact || ''
    editResponse.value = res.data.change_log?.[0]?.response || ''
    detailVisible.value = true
  } catch (e) { ElMessage.error('获取详情失败: ' + (e.response?.data?.detail || e.message)) }
}

async function saveDetail() {
  savingDetail.value = true
  try {
    await updatePlatformRules(detailPlatform.value.id, {
      summary: editSummary.value,
      details: editDetails.value.filter(d => d.trim()),
      impact: editImpact.value,
      response: editResponse.value,
      status: detailData.value.status,
    })
    ElMessage.success('规则已保存')
    detailEditMode.value = false
    await openDetail(detailPlatform.value)
    loadPlatforms()
  } catch (e) { ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message)) }
  finally { savingDetail.value = false }
}

async function generateSummaryInDetail() {
  checkingSingle.value = true
  try {
    const res = await checkSinglePlatform(detailPlatform.value.id)
    ElMessage.success(res.data.has_changes ? '检测到规则变化！' : '规则无变化')
    await openDetail(detailPlatform.value)
    loadPlatforms()
  } catch (e) {
    ElMessage.error('检查失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    checkingSingle.value = false
  }
}

async function generateSummary(p) {
  try {
    ElMessage.info('正在生成AI摘要...')
    const res = await generateLLMSummary(p.id)
    ElMessage.success('摘要生成完成')
    loadPlatforms()
  } catch (e) { ElMessage.error('摘要生成失败: ' + (e.response?.data?.detail || e.message)) }
}

function formatDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('zh-CN')
}

function isDataStale(lastChecked) {
  if (!lastChecked) return true
  const days = (Date.now() - new Date(lastChecked).getTime()) / 86400000
  return days > 30
}

// ── 关键词库 ──
const sandtableTypes = ref([])
const kwSandtableType = ref('')
const kwCategories = KEYWORD_CATEGORIES
const kwData = ref({})
const kwAddVisible = ref(false)
const kwSaving = ref(false)
const kwExpanding = ref(false)
const editingKw = ref(null)
const kwForm = ref({ word: '', category: 'scene', weight: 'core', status: 'pending' })
const kwExpandedList = ref([])
const kwImportVisible = ref(false)
const kwImportText = ref('')
const kwImporting = ref(false)

const totalKeywordCount = computed(() => {
  if (!kwData.value) return 0
  return Object.values(kwData.value).reduce((sum, arr) => sum + (arr?.length || 0), 0)
})
const coreKeywordCount = computed(() => {
  if (!kwData.value) return 0
  let count = 0
  Object.values(kwData.value).forEach(arr => {
    if (arr) arr.forEach(k => { if (k.weight === 'core') count++ })
  })
  return count
})
const optimizedKeywordCount = computed(() => {
  if (!kwData.value) return 0
  let count = 0
  Object.values(kwData.value).forEach(arr => {
    if (arr) arr.forEach(k => { if (k.status === 'optimized') count++ })
  })
  return count
})

function weightLabel(w) {
  if (w === 'core') return '核心'
  if (w === 'secondary') return '辅助'
  return '长尾'
}

function resetKwForm() {
  editingKw.value = null
  kwForm.value = { word: '', category: 'scene', weight: 'core', status: 'pending' }
}

async function loadKWTypes() {
  try {
    const res = await listSandtableTypes()
    sandtableTypes.value = res.data.types || []
  } catch (e) {
    ElMessage.error('沙盘类型加载失败: ' + (e.response?.data?.detail || e.message))
    sandtableTypes.value = SANDTABLE_TYPES.map(t => ({ key: t.value, label: t.label }))
  }
}

async function loadKeywords() {
  if (!kwSandtableType.value) return
  try {
    const res = await getKeywords(kwSandtableType.value)
    kwData.value = res.data.keywords || {}
  } catch (e) { ElMessage.error('关键词加载失败: ' + (e.response?.data?.detail || e.message)) }
}

async function saveKeyword() {
  if (!kwForm.value.word.trim()) { ElMessage.warning('请输入关键词'); return }
  kwSaving.value = true
  try {
    if (editingKw.value) {
      await updateKeyword(kwSandtableType.value, editingKw.value.category, editingKw.value.word, {
        word_new: kwForm.value.word,
        weight: kwForm.value.weight,
        status: kwForm.value.status,
      })
    } else {
      await addKeyword(kwSandtableType.value, {
        word: kwForm.value.word,
        category: kwForm.value.category,
        weight: kwForm.value.weight,
        status: kwForm.value.status,
      })
    }
    ElMessage.success(editingKw.value ? '更新成功' : '添加成功')
    kwAddVisible.value = false
    editingKw.value = null
    kwForm.value = { word: '', category: 'scene', weight: 'core', status: 'pending' }
    loadKeywords()
  } catch (e) {
    const msg = e.response?.data?.detail || '操作失败'
    ElMessage.error(msg)
  }
  finally { kwSaving.value = false }
}

function editKeyword(cat, kw) {
  editingKw.value = { ...kw, category: cat }
  kwForm.value = {
    word: kw.word,
    category: cat,
    weight: kw.weight,
    status: kw.status,
  }
  kwAddVisible.value = true
}

async function removeKeyword(cat, word) {
  try {
    await ElMessageBox.confirm(`确定删除关键词 "${word}"？`, '确认删除', { type: 'warning' })
    await deleteKeyword(kwSandtableType.value, cat, word)
    ElMessage.success('已删除')
    loadKeywords()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message)) }
}

async function expandByLLM() {
  kwExpanding.value = true
  try {
    const res = await expandKeywords(kwSandtableType.value, { seed: '' })
    const generated = (res.data.generated_keywords || []).map(k => ({ ...k, _selected: false }))
    kwExpandedList.value = generated
    if (generated.length === 0) {
      ElMessage.warning('LLM 未生成关键词，请尝试输入种子词')
    } else {
      ElMessage.success(`LLM 生成了 ${generated.length} 个关键词，点击选中后一键添加`)
    }
  } catch (e) { ElMessage.error('扩展失败: ' + (e.response?.data?.detail || e.message)) }
  finally { kwExpanding.value = false }
}

function selectAllExpanded() {
  const allSelected = kwExpandedList.value.every(k => k._selected)
  kwExpandedList.value.forEach(k => { k._selected = !allSelected })
}

async function batchAddExpanded() {
  const selected = kwExpandedList.value.filter(k => k._selected)
  if (!selected.length) return
  let added = 0
  for (const kw of selected) {
    try {
      const cat = kw.category || (kw.weight === 'longtail' ? 'longtail' : 'scene')
      await addKeyword(kwSandtableType.value, {
        word: kw.word, category: cat, weight: kw.weight || 'secondary', status: 'pending',
      })
      added++
    } catch (e) {
      if (e.response?.status !== 409) {
        ElMessage.error(`添加 "${kw.word}" 失败: ` + (e.response?.data?.detail || e.message))
      }
    }
  }
  if (added > 0) {
    ElMessage.success(`已添加 ${added} 个关键词`)
    kwExpandedList.value = kwExpandedList.value.filter(k => !k._selected)
    loadKeywords()
  }
}

function openKwImport() {
  kwImportText.value = ''
  kwImportVisible.value = true
}

async function importKeywordsCSV() {
  if (!kwImportText.value.trim()) { ElMessage.warning('请粘贴CSV内容'); return }
  kwImporting.value = true
  const lines = kwImportText.value.trim().split('\n')
  let added = 0
  for (let i = 0; i < lines.length; i++) {
    const parts = lines[i].split(',').map(s => s.trim())
    if (parts.length < 2 || i === 0 && parts[0] === '分类') continue
    const [cat, word, weight, status] = parts
    if (!word) continue
    try {
      await addKeyword(kwSandtableType.value, {
        word,
        category: cat || 'scene',
        weight: weight || 'secondary',
        status: status || 'pending',
      })
      added++
    } catch (e) {
      if (e.response?.status !== 409) {
        ElMessage.error(`导入 "${word}" 失败: ` + (e.response?.data?.detail || e.message))
      }
    }
  }
  if (added > 0) {
    ElMessage.success(`成功导入 ${added} 个关键词`)
    kwImportVisible.value = false
    loadKeywords()
  } else {
    ElMessage.warning('没有导入任何关键词')
  }
  kwImporting.value = false
}

async function exportKeywordsCSVAction() {
  try {
    const res = await exportKeywordsCSV(kwSandtableType.value)
    const blob = new Blob(['﻿' + res.data.csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = res.data.filename || 'keywords.csv'; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) { ElMessage.error('导出失败: ' + (e.response?.data?.detail || e.message)) }
}

// ── 竞品调研 ──
const competitors = ref([])
const selectedComps = ref([])
// ── 竞品自动监控 ──
const monitorRunning = ref(false)
const monitorSuccess = ref('')
const monitorError = ref('')
const monitorHistory = ref([])

async function triggerMonitor() {
  monitorRunning.value = true
  monitorSuccess.value = ''
  monitorError.value = ''
  try {
    const { data } = await triggerCompetitorMonitor()
    if (data.status === 'ok') {
      monitorSuccess.value = `监控完成：${data.competitors_probed}个竞品 × ${data.platforms_probed}个平台，发现 ${data.changes_from_previous?.alerts?.length || 0} 项变化`
    } else {
      monitorError.value = `监控跳过：${data.message || data.reason}`
    }
    await loadMonitorHistory()
  } catch (e) {
    monitorError.value = '监控失败: ' + (e.response?.data?.detail || e.message)
  } finally {
    monitorRunning.value = false
  }
}

async function loadMonitorHistory() {
  try {
    const { data } = await getCompetitorMonitorHistory(14)
    monitorHistory.value = data.cycles || []
  } catch {
    monitorHistory.value = []
  }
}
const compDialogVisible = ref(false)
const editingComp = ref(null)
const compSaving = ref(false)
const compForm = ref({
  name: '', website: '', industry: '', notes: '',
  platform_exposure: {},
  content_features: {},
})
const snapshotVisible = ref(false)
const snapshotCompId = ref('')
const snapSaving = ref(false)
const snapForm = ref({ date: new Date().toISOString().slice(0,10), platform: '', query: '', citation_found: false, citation_snippet: '', notes: '' })
const compareVisible = ref(false)
const compareData = ref(null)
const aiPlatforms = AI_PLATFORMS.map(p => p.label)

// 竞品表单预设
const exposurePlatforms = AI_PLATFORMS.map(p => ({ key: p.value, label: p.label }))
const contentFeatureDims = [
  { key: 'keyword_coverage', label: '关键词覆盖' },
  { key: 'structure_quality', label: '结构化程度' },
  { key: 'case_richness', label: '案例丰富度' },
  { key: 'tech_depth', label: '技术深度' },
  { key: 'multimedia_use', label: '多媒体使用' },
]

function levelClass(level) {
  if (level === '高') return 'high'
  if (level === '中') return 'mid'
  if (level === '低') return 'low'
  return 'none'
}

function latestSnapshot(comp) {
  const snaps = comp.snapshots || []
  if (!snaps.length) return ''
  const s = snaps[0]
  const days = Math.floor((Date.now() - new Date(s.date).getTime()) / 86400000)
  const ago = days === 0 ? '今天' : days === 1 ? '昨天' : days + '天前'
  return ago + '在' + s.platform + (s.citation_found ? '被引用' : '未被引用')
}

const comparePlatforms = computed(() => {
  const set = new Set()
  competitors.value.forEach(c => {
    if (c.platform_exposure) Object.keys(c.platform_exposure).forEach(k => set.add(k))
  })
  return [...set]
})

const compareTable = computed(() => {
  if (!compareData.value) return []
  return compareData.value.comparison.competitors.map(c => ({
    name: c.name,
    ...compareData.value.comparison.platform_coverage[c.name] || {},
    features: Object.entries(compareData.value.comparison.content_features[c.name] || {}).map(([k,v]) => `${k}:${v}`).join('; '),
  }))
})

function toggleCompSelect(id) {
  const idx = selectedComps.value.indexOf(id)
  if (idx >= 0) selectedComps.value.splice(idx, 1)
  else selectedComps.value.push(id)
}

function openCompDialog(comp) {
  editingComp.value = comp || null
  if (comp) {
    compForm.value = {
      name: comp.name, website: comp.website || '', industry: comp.industry || '',
      notes: comp.notes || '',
      platform_exposure: { ...(comp.platform_exposure || {}) },
      content_features: { ...(comp.content_features || {}) },
    }
  } else {
    compForm.value = { name: '', website: '', industry: '', notes: '', platform_exposure: {}, content_features: {} }
  }
  compDialogVisible.value = true
}

async function saveComp() {
  if (!compForm.value.name.trim()) { ElMessage.warning('请输入竞品名称'); return }
  compSaving.value = true
  try {
    // 清理空的平台曝光和内容特征
    const cleanExposure = {}
    Object.entries(compForm.value.platform_exposure).forEach(([k, v]) => {
      if (v && v !== '未见') cleanExposure[k] = v
    })
    const cleanFeatures = {}
    Object.entries(compForm.value.content_features).forEach(([k, v]) => {
      if (v) cleanFeatures[k] = v
    })
    const payload = {
      name: compForm.value.name,
      website: compForm.value.website,
      industry: compForm.value.industry,
      notes: compForm.value.notes,
      platform_exposure: cleanExposure,
      content_features: cleanFeatures,
    }
    if (editingComp.value) {
      await updateCompetitor(editingComp.value.id, payload)
    } else {
      await createCompetitor(payload)
    }
    ElMessage.success(editingComp.value ? '已更新' : '已添加')
    compDialogVisible.value = false
    loadCompetitors()
  } catch (e) { ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message)) }
  finally { compSaving.value = false }
}

async function deleteComp(id) {
  try {
    await ElMessageBox.confirm('确定删除此竞品？', '确认', { type: 'warning' })
    await apiDeleteCompetitor(id)
    ElMessage.success('已删除')
    loadCompetitors()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message)) }
}

function openSnapshotDialog(comp) {
  snapshotCompId.value = comp.id
  snapForm.value = { date: new Date().toISOString().slice(0,10), platform: '', query: '', citation_found: false, citation_snippet: '', notes: '' }
  snapshotVisible.value = true
}

async function saveSnapshot() {
  snapSaving.value = true
  try {
    await addSnapshot(snapshotCompId.value, { ...snapForm.value })
    ElMessage.success('快照已保存')
    snapshotVisible.value = false
    loadCompetitors()
  } catch (e) { ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message)) }
  finally { snapSaving.value = false }
}

async function doCompare() {
  try {
    const res = await compareCompetitors({ competitor_ids: selectedComps.value, include_llm: true })
    compareData.value = res.data
    compareVisible.value = true
  } catch (e) { ElMessage.error('对比失败: ' + (e.response?.data?.detail || e.message)) }
}

async function doGenerateReport() {
  try {
    const res = await generateCompetitorReport({ competitor_ids: selectedComps.value })
    const blob = new Blob([res.data.report], { type: 'text/markdown;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = '竞品调研报告.md'; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('报告已导出')
  } catch (e) { ElMessage.error('生成失败: ' + (e.response?.data?.detail || e.message)) }
}

async function loadCompetitors() {
  try {
    const res = await listCompetitors()
    competitors.value = res.data.competitors || []
  } catch (e) { ElMessage.error('竞品列表加载失败: ' + (e.response?.data?.detail || e.message)) }
}

onMounted(() => {
  loadPlatforms()
  loadKWTypes()
  loadCompetitors()
  checkSchedulerStatus()
})
</script>

<style scoped>
.strategy-center { max-width: 1200px; }
.page-header { margin-bottom: 20px; }
.page-header h2 { font-size: 20px; color: #2D3142; margin-bottom: 4px; }
.page-header p { font-size: 13px; color: #9B9EAA; }
.tab-toolbar { display: flex; align-items: center; flex-wrap: wrap; }
.platform-alert { border-left: 3px solid #C5554A; }
.plat-card-header { display: flex; justify-content: space-between; align-items: center; }
.plat-name { font-weight: bold; font-size: 15px; }
.plat-meta { display: flex; gap: 12px; font-size: 12px; color: #9B9EAA; margin-top: 4px; }
.plat-summary { font-size: 13px; color: #6B6E7B; margin-top: 8px; line-height: 1.6; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
/* ========= 平台详情弹窗 ========= */
.platform-detail-dialog :deep(.el-dialog__header) {
  padding: 20px 24px 16px;
  border-bottom: 1px solid #F0EDE8;
}
.platform-detail-dialog :deep(.el-dialog__body) { padding: 0; }

.pd-topbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 24px; background: linear-gradient(135deg, #FAF8F5 0%, #F0EDE8 100%);
  border-bottom: 1px solid #E8E5DF;
}
.pd-meta { display: flex; align-items: center; gap: 12px; }
.pd-meta-tag {
  font-size: 12px; padding: 3px 10px; border-radius: 4px; font-weight: 500;
}
.pd-meta-tag.category { background: rgba(200,150,62,0.06); color: #C8963E; }
.pd-meta-tag.status { display: flex; align-items: center; gap: 6px; }
.pd-meta-tag.status.ok { background: rgba(91,140,90,0.08); color: #5B8C5A; }
.pd-meta-tag.status.alert { background: rgba(197,85,74,0.08); color: #C5554A; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.status.ok .status-dot { background: #5B8C5A; }
.status.alert .status-dot { background: #C5554A; animation: pulse-dot 1.5s infinite; }
@keyframes pulse-dot { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.pd-meta-time { font-size: 12px; color: #9B9EAA; }
.pd-actions { display: flex; gap: 8px; }

.pd-body { padding: 20px 24px 24px; max-height: 62vh; overflow-y: auto; }

.pd-section { margin-bottom: 24px; }
.pd-section-hd {
  display: flex; align-items: center; gap: 8px;
  font-size: 14px; font-weight: 600; color: #2D3142;
  margin-bottom: 12px; padding-bottom: 10px;
  border-bottom: 2px solid #E8E5DF;
}
.pd-section-icon { color: #C8963E; display: flex; align-items: center; }
.pd-section-badge {
  font-size: 11px; font-weight: 400; color: #fff; background: #D4956A;
  padding: 1px 8px; border-radius: 10px; margin-left: auto;
}
.pd-section-count { font-size: 11px; color: #9B9EAA; font-weight: 400; margin-left: auto; }

/* 摘要区 */
.pd-summary-box {
  background: #FAF8F5; border-radius: 10px; padding: 16px 20px;
  border: 1px solid #E8E5DF; line-height: 1.8;
}
.pd-summary-line {
  margin: 0; color: #6B6E7B; font-size: 13px; padding: 3px 0;
  padding-left: 16px; position: relative;
}
.pd-summary-line::before {
  content: ''; position: absolute; left: 0; top: 11px;
  width: 6px; height: 6px; border-radius: 50%; background: #C8963E; opacity: 0.5;
}
.pd-empty-block {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 32px 20px; color: #bbb; font-size: 13px;
  background: #FAF8F5; border-radius: 10px; border: 1px dashed #D5D2CC;
}
.pd-editor :deep(.el-textarea__inner) { font-size: 13px; line-height: 1.7; }

/* 规则要点网格 */
.pd-points-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.pd-point-chip {
  display: flex; align-items: flex-start; gap: 8px;
  background: #fff; border: 1px solid #E8E5DF; border-radius: 10px;
  padding: 10px 14px; max-width: calc(50% - 4px); flex: 1 1 calc(50% - 4px);
  transition: border-color 0.22s cubic-bezier(0.4,0,0.2,1), box-shadow 0.2s;
}
.pd-point-chip:hover { border-color: #C8963E; box-shadow: 0 2px 8px rgba(200,150,62,0.08); }
.pd-point-chip-num {
  width: 20px; height: 20px; border-radius: 50%; background: rgba(200,150,62,0.06);
  color: #C8963E; font-size: 11px; font-weight: 600;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.pd-point-chip-text { font-size: 13px; color: #6B6E7B; line-height: 1.6; }

/* 要点编辑器 */
.pd-points-editor { }
.pd-point-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.pd-point-num {
  width: 22px; height: 22px; border-radius: 50%; background: #C8963E;
  color: #fff; font-size: 12px; font-weight: 600;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.pd-add-btn { margin-top: 4px; }

/* 应对策略 */
.pd-sub-label { font-size: 12px; font-weight: 500; color: #9B9EAA; margin-bottom: 8px; }
.pd-text-card {
  font-size: 13px; color: #6B6E7B; line-height: 1.7;
  padding: 12px 14px; border-radius: 6px; min-height: 60px;
}
.pd-text-card.warning { background: rgba(212,149,106,0.08); border-left: 3px solid #D4956A; }
.pd-text-card.success { background: rgba(91,140,90,0.08); border-left: 3px solid #5B8C5A; }
.pd-na { font-size: 12px; color: #ccc; padding: 12px 0; }

/* 保存栏 */
.pd-save-bar {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 14px 0; margin: 0 -24px;
  padding-left: 24px; padding-right: 24px;
  background: #FAF8F5; border-top: 1px solid #E8E5DF; border-bottom: 1px solid #E8E5DF;
  margin-bottom: 20px;
}

/* 时间线 */
.pd-timeline { padding-left: 4px; }
.pd-tl-item { display: flex; gap: 12px; }
.pd-tl-item.first { }
.pd-tl-marker { display: flex; flex-direction: column; align-items: center; width: 14px; flex-shrink: 0; }
.pd-tl-dot {
  width: 10px; height: 10px; border-radius: 50%; background: #D0CDC6; margin-top: 6px;
}
.pd-tl-dot.latest { background: #C8963E; box-shadow: 0 0 0 3px rgba(200,150,62,0.15); }
.pd-tl-line { flex: 1; width: 2px; background: #E8E5DF; min-height: 20px; }
.pd-tl-card {
  flex: 1; background: #FAF8F5; border: 1px solid #E8E5DF; border-radius: 10px;
  padding: 12px 14px; margin-bottom: 10px;
  transition: border-color 0.22s cubic-bezier(0.4,0,0.2,1);
}
.pd-tl-card:hover { border-color: #c0c8d4; }
.pd-tl-date { font-size: 11px; color: #9B9EAA; margin-bottom: 8px; }
.pd-tl-field { display: flex; gap: 8px; margin-bottom: 5px; font-size: 12px; line-height: 1.5; }
.pd-tl-field:last-child { margin-bottom: 0; }
.pd-tl-label {
  color: #9B9EAA; font-weight: 500; min-width: 42px; flex-shrink: 0;
  font-size: 11px; text-transform: uppercase;
}
.pd-tl-value { color: #6B6E7B; }
.pd-tl-value.old { color: #9B9EAA; text-decoration: line-through; text-decoration-color: #ddd; }
.pd-tl-value.new { color: #2D3142; font-weight: 500; }

.comp-selected { border: 2px solid #C8963E; }
.comp-name { font-weight: bold; font-size: 15px; }
.comp-meta { font-size: 13px; color: #6B6E7B; }
.comp-row { margin-bottom: 6px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.comp-label { font-size: 12px; color: #9B9EAA; min-width: 48px; }

/* 引导横幅 */
.guide-banner {
  display: flex; align-items: flex-start; gap: 12px;
  background: rgba(200,150,62,0.06); border-radius: 10px; padding: 14px 18px;
  margin-bottom: 16px; border: 1px solid rgba(200,150,62,0.12);
}
.guide-icon { color: #C8963E; flex-shrink: 0; margin-top: 1px; }
.guide-text { font-size: 13px; color: #6B6E7B; line-height: 1.7; }
.guide-text em { font-style: normal; background: rgba(200,150,62,0.12); padding: 1px 6px; border-radius: 3px; font-size: 12px; }

/* AI平台存在感色点 */
.comp-platform-dots { display: flex; gap: 3px; flex-wrap: wrap; }
.comp-plat-dot {
  display: inline-block; width: 22px; height: 22px; border-radius: 4px;
  font-size: 10px; text-align: center; line-height: 22px; cursor: default;
}
.comp-plat-dot.high { background: rgba(91,140,90,0.08); color: #5B8C5A; }
.comp-plat-dot.mid { background: rgba(212,149,106,0.15); color: #D4956A; }
.comp-plat-dot.low { background: rgba(197,85,74,0.08); color: #C5554A; }
.comp-plat-dot.none { background: #F0EDE8; color: #c0c4cc; }

/* 平台曝光网格 */
.platform-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.platform-grid-item { display: flex; align-items: center; gap: 6px; }
.platform-grid-label { font-size: 12px; color: #6B6E7B; min-width: 60px; }

/* 内容特征网格 */
.feature-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.feature-grid-item { display: flex; align-items: center; gap: 6px; }
.feature-label { font-size: 12px; color: #6B6E7B; min-width: 70px; }

/* 对比热力格 */
.heat-cell { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; width: 100%; text-align: center; }
.heat-cell.heat-高 { background: rgba(91,140,90,0.08); color: #5B8C5A; }
.heat-cell.heat-中 { background: rgba(212,149,106,0.15); color: #D4956A; }
.heat-cell.heat-低 { background: rgba(197,85,74,0.08); color: #C5554A; }
.heat-cell.heat-未见 { color: #c0c4cc; }

/* LLM洞察卡片 */
.llm-insight-cards { margin-top: 16px; }
.insight-card {
  background: #FAF8F5; border-radius: 10px; padding: 14px 16px;
  margin-bottom: 12px; border: 1px solid #E8E5DF;
}
.insight-card h4 { font-size: 14px; color: #2D3142; margin-bottom: 8px; }
.insight-card p { font-size: 13px; color: #6B6E7B; line-height: 1.7; white-space: pre-wrap; }
.insight-card.opportunity { border-left: 3px solid #5B8C5A; }
.insight-card.recommendation { border-left: 3px solid #C8963E; }
.insight-card ul { padding-left: 18px; }
.insight-card li { font-size: 13px; color: #6B6E7B; line-height: 1.8; }

/* 沙盘类型卡片选择器 */
.sandtable-cards { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.st-card {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; border-radius: 10px; border: 1px solid #E8E5DF;
  cursor: pointer; transition: all 0.22s cubic-bezier(0.4,0,0.2,1); background: #fff;
}
.st-card:hover { border-color: #C8963E; box-shadow: 0 2px 8px rgba(200,150,62,0.1); }
.st-card.active { background: rgba(200,150,62,0.06); border-color: #C8963E; }
.st-card-icon {
  width: 28px; height: 28px; border-radius: 6px; background: #F0EDE8;
  font-size: 11px; display: flex; align-items: center; justify-content: center;
  color: #6B6E7B; flex-shrink: 0;
}
.st-card.active .st-card-icon { background: #C8963E; color: #fff; }
.st-card-label { font-size: 13px; color: #2D3142; white-space: nowrap; }

/* 关键词统计栏 */
.kw-stats-bar { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; padding: 12px 0; }
.kw-stat { display: flex; align-items: baseline; gap: 6px; }
.kw-stat-num { font-size: 22px; font-weight: 700; color: #2D3142; }
.kw-stat-num.core { color: #C8963E; }
.kw-stat-num.success { color: #5B8C5A; }
.kw-stat-num.warning { color: #D4956A; }
.kw-stat-label { font-size: 12px; color: #9B9EAA; }
.kw-actions-right { margin-left: auto; display: flex; gap: 8px; }

/* 关键词分类卡片 */
.kw-cat-card { background: #fff; border: 1px solid #E8E5DF; border-radius: 10px; overflow: hidden; }
.kw-cat-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; background: #FAF8F5; border-bottom: 1px solid #E8E5DF;
}
.kw-cat-title { font-size: 14px; font-weight: 600; color: #2D3142; }
.kw-cat-body { padding: 8px 12px; max-height: 340px; overflow-y: auto; }
.kw-row {
  display: flex; align-items: center; gap: 8px; padding: 7px 8px;
  border-radius: 6px; transition: background 0.15s cubic-bezier(0.4,0,0.2,1);
}
.kw-row:hover { background: #F5F3EE; }
.kw-word-text { flex: 1; font-size: 13px; color: #2D3142; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kw-row-tags { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.kw-weight-tag {
  font-size: 10px; padding: 1px 6px; border-radius: 3px;
  background: rgba(200,150,62,0.06); color: #C8963E;
}
.kw-weight-tag.core { background: rgba(200,150,62,0.06); color: #C8963E; }
.kw-weight-tag.secondary { background: #F0EDE8; color: #9B9EAA; }
.kw-weight-tag.longtail { background: rgba(197,85,74,0.08); color: #C5554A; }
.kw-status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.kw-status-dot.optimized { background: #5B8C5A; }
.kw-status-dot.pending { background: #D4956A; }
.kw-row-actions { display: flex; gap: 2px; flex-shrink: 0; opacity: 0; transition: opacity 0.15s; }
.kw-row:hover .kw-row-actions { opacity: 1; }
.kw-empty { text-align: center; padding: 24px 0; color: #c0c4cc; font-size: 13px; }

/* LLM扩展面板 */
.kw-expanded-panel {
  margin-top: 16px; border: 1px solid #E8E5DF; border-radius: 10px;
  background: #FAF8F5; overflow: hidden;
}
.kw-expanded-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 16px; border-bottom: 1px solid #E8E5DF;
  font-size: 13px; font-weight: 500; color: #2D3142;
}
.kw-expanded-grid { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 16px; }
.kw-expanded-item {
  display: flex; flex-direction: column; gap: 2px;
  padding: 8px 12px; border-radius: 6px; border: 1px solid #E8E5DF;
  cursor: pointer; transition: all 0.15s cubic-bezier(0.4,0,0.2,1); background: #fff;
}
.kw-expanded-item:hover { border-color: #C8963E; }
.kw-expanded-item.selected { background: rgba(200,150,62,0.06); border-color: #C8963E; }
.kw-exp-word { font-size: 13px; color: #2D3142; font-weight: 500; }
.kw-exp-meta { font-size: 11px; color: #9B9EAA; }
</style>
