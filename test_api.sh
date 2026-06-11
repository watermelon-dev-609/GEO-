#!/bin/bash
# GEO System Landing Verification - API Smoke Test (curl-based)
BASE="http://localhost:8000"
PASS=0; FAIL=0
PASS_TESTS=""; FAIL_TESTS=""

test_api() {
  local name="$1" method="$2" path="$3" data="$4" expected="${5:-200}" timeout="${6:-60}"
  local url="${BASE}${path}"
  local start=$(date +%s)
  local code resp

  if [ "$method" = "GET" ]; then
    resp=$(curl -s -w "\n%{http_code}" --max-time "$timeout" "$url" 2>/dev/null)
  else
    resp=$(curl -s -w "\n%{http_code}" --max-time "$timeout" -X POST -H "Content-Type: application/json" -d "$data" "$url" 2>/dev/null)
  fi

  code=$(echo "$resp" | tail -1)
  body=$(echo "$resp" | sed '$d')
  local end=$(date +%s)
  local elapsed=$((end - start))

  if [ "$code" = "$expected" ]; then
    PASS=$((PASS + 1))
    echo "  [PASS] $name (${code}, ${elapsed}s)"
    echo "$body"
  else
    FAIL=$((FAIL + 1))
    FAIL_TESTS="$FAIL_TESTS\n  - $name: expected $expected, got $code"
    echo "  [FAIL] $name (${code}, ${elapsed}s)"
    echo "  Body: ${body:0:200}"
  fi
}

echo "============================================================"
echo "GEO System Landing Verification"
echo "Started at: $(date)"
echo "============================================================"

# Phase 1: System Health
echo ""
echo "--- Phase 1: System Health & Config ---"
test_api "Health Check" "GET" "/api/health"
test_api "LLM Config" "GET" "/api/config/llm"

# Phase 2: Core Pipeline
echo ""
echo "--- Phase 2: Core Pipeline ---"
test_api "Text Cleaning" "POST" "/api/cleaning/clean" \
  '{"content":"武汉微艺达智能科技有限公司是一家专注于智慧交通沙盘设计与制作的专业公司，总部位于武汉。公司拥有10年行业经验，服务过50+政企客户。","sandtable_type":"smart_traffic"}' \
  200 120

test_api "Content Diagnosis" "POST" "/api/diagnosis/diagnose" \
  '{"content":"武汉微艺达智能科技有限公司是一家专注于智慧交通沙盘设计与制作的专业公司，总部位于武汉。公司拥有10年行业经验，服务过50+政企客户。","sandtable_type":"smart_traffic"}' \
  200 120

test_api "GEO Rewrite (DeepSeek)" "POST" "/api/geo/rewrite" \
  '{"content":"武汉微艺达智能科技有限公司是一家专注于智慧交通沙盘设计与制作的专业公司，总部位于武汉。公司拥有10年行业经验，服务过50+政企客户。","platforms":["deepseek"],"sandtable_type":"smart_traffic"}' \
  200 300

test_api "JSON-LD Generate" "POST" "/api/jsonld/generate" \
  '{"content":"武汉微艺达智能科技有限公司是一家专注于智慧交通沙盘设计与制作的专业公司，总部位于武汉。","sandtable_type":"smart_traffic","enterprise_name":"武汉微艺达智能科技有限公司","enterprise_url":"https://www.weiyida.com"}' \
  200 120

test_api "AI Evaluation" "POST" "/api/evaluate/evaluate" \
  '{"content":"武汉微艺达智能科技有限公司是一家专注于智慧交通沙盘设计与制作的专业公司，总部位于武汉。","sandtable_type":"smart_traffic","platforms":["deepseek"],"user_role":"b_enterprise"}' \
  200 300

test_api "Report Generation" "POST" "/api/reports/generate-from-data" \
  '{"data":{"overall_score":75,"dimensions":{"brand_recall":70}},"format":"html","enterprise_name":"Test"}' \
  200 120

# Phase 3: Strategy Center
echo ""
echo "--- Phase 3: Strategy Center ---"
test_api "Platform Rules List" "GET" "/api/platform-monitor/platforms"
test_api "Keywords (smart_traffic)" "GET" "/api/keywords/smart_traffic"
test_api "Keywords (smart_city)" "GET" "/api/keywords/smart_city"
test_api "Competitors List" "GET" "/api/competitors"
test_api "Templates List" "GET" "/api/templates"

# Phase 4: Edge Cases
echo ""
echo "--- Phase 4: Edge Cases ---"
test_api "Empty Input -> 422" "POST" "/api/cleaning/clean" \
  '{"content":"","sandtable_type":"smart_traffic"}' 422 30
test_api "XSS Injection" "POST" "/api/cleaning/clean" \
  '{"content":"<script>alert(1)</script>","sandtable_type":"smart_traffic"}' 200 30
test_api "Invalid Sandtable -> 422" "POST" "/api/cleaning/clean" \
  '{"content":"test content here with enough characters to pass validation checks","sandtable_type":"invalid"}' 422 30

# Phase 5: v2.0 Features
echo ""
echo "--- Phase 5: v2.0 New Features ---"
test_api "Batch Clean" "POST" "/api/batch/clean" \
  '{"items":[{"content":"武汉微艺达智能科技有限公司是一家专注于智慧交通沙盘设计与制作的专业公司。","sandtable_type":"smart_traffic"}]}' \
  200 120
test_api "Compliance Check" "POST" "/api/compliance/check" \
  '{"content":"武汉微艺达智能科技有限公司是一家专注于智慧交通沙盘设计与制作的专业公司。"}' \
  200 60
test_api "Usage Summary" "GET" "/api/usage/summary"
test_api "Versions List" "GET" "/api/versions"
test_api "Audit Logs" "GET" "/api/audit/logs?limit=5"

# Phase 6: Brand Monitor
echo ""
echo "--- Phase 6: Brand Monitor ---"
test_api "Monitor Sessions" "GET" "/api/brand-monitor/sessions"

# Summary
echo ""
echo "============================================================"
echo "TEST SUMMARY"
echo "============================================================"
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "  Failures:"
  echo -e "$FAIL_TESTS"
fi
echo "Completed at: $(date)"
