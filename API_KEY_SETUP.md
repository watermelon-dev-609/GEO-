# API Key 配置清单

> 当前状态：2/7 平台可用 | 更新时间：2026-06-02

---

## 已配置（可直接使用）

| 平台 | API Key | 状态 |
|------|---------|------|
| DeepSeek | `sk-1a1b9674d...` | ✅ 可用 |
| Kimi (Moonshot) | `sk-qthKdykfb...` | ✅ 可用 |

---

## 待配置（需申请API Key）

### 高优先级（B端政企交付必需）

| 平台 | 申请地址 | 需要的信息 | 预计费用 |
|------|---------|-----------|---------|
| **通义千问** | https://dashscope.aliyun.com | API Key | 按量付费 |
| **文心一言** | https://yiyan.baidu.com | API Key + Secret Key（双密钥） | 按量付费 |
| **腾讯元宝** | https://cloud.tencent.com | API Key + Secret ID | 按量付费 |

### 中优先级（大众传播覆盖）

| 平台 | 申请地址 | 需要的信息 | 预计费用 |
|------|---------|-----------|---------|
| **字节豆包** | https://www.volcengine.com | API Key | 按量付费 |
| **讯飞星火** | https://xinghuo.xfyun.cn | API Key | 按量付费 |

### 低优先级（可选）

| 平台 | 申请地址 | 备注 |
|------|---------|------|
| Claude | https://console.anthropic.com | 国际平台，需外币卡 |

---

## 配置步骤

1. 在对应平台注册并实名认证
2. 创建应用 → 获取 API Key
3. 编辑 `backend/.env` 文件，填入真实Key：

```env
DOUBAO_API_KEY=your-real-key-here
TONGYI_API_KEY=your-real-key-here
WENXIN_API_KEY=your-real-key-here
WENXIN_SECRET_KEY=your-real-secret-here
YUANBAO_API_KEY=your-real-key-here
YUANBAO_SECRET_ID=your-real-secret-id-here
```

4. 在系统左下角「配置API Key」中保存（或直接编辑.env后重启后端）
5. 验证：点「配置API Key」→ 查看对应平台状态变为「已配置」

---

## 配置后效果

| 平台组合 | 覆盖场景 |
|----------|---------|
| DeepSeek + Kimi（当前） | 技术型客户 |
| + 通义 + 文心 + 元宝 | **B端政企客户**（完整覆盖） |
| + 豆包 + 讯飞星火 | **大众传播 + 全平台覆盖** |

> 建议优先配置通义千问（阿里系，政企采购流量大）+ 文心一言（百度搜索生态）
