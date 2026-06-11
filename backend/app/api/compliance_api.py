"""合规检测API路由"""

from fastapi import APIRouter, HTTPException
from app.models.schemas import ComplianceCheckRequest, ComplianceCheckResult
from app.core.compliance import ComplianceChecker

router = APIRouter()


@router.post("/check", response_model=ComplianceCheckResult)
async def check_compliance(req: ComplianceCheckRequest):
    """检测文本中的合规问题（广告法禁词等）"""
    try:
        checker = ComplianceChecker.from_config()
        report = checker.check(req.text)
        return ComplianceCheckResult(
            passed=report.passed,
            violation_count=report.violation_count,
            violations=report.violations,
            risk_level=report.risk_level,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"合规检测失败: {str(e)}")
