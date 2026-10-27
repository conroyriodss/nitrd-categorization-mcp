"""portal_get_reviewer_assignment: preview who would review an application (no write).

Routing (POLICY_VERSION nitrd-routing-v2-2026-10-26):
1. the project's program officer, if exactly one demo PO persona matches;
2. else the administering IC's NITRD representative persona;
3. else the NITRD-SIA queue persona (demo_sia).
Subprojects inherit the parent award's routing via (full_project_num, fy).
"""

from fastmcp import FastMCP

from reviewer_portal.models import RoutingDecision
from reviewer_portal.utils import EXPORTER_PROJECTS, not_implemented
from shared.models import READ_ONLY, ApplId, ResultModel, SourceInfo


class AssignmentResult(ResultModel):
    appl_id: int
    fy: int
    assignment: RoutingDecision
    source: SourceInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(annotations={**READ_ONLY, "title": "Preview reviewer assignment"})
    async def portal_get_reviewer_assignment(appl_id: ApplId) -> AssignmentResult:
        """Preview which demo reviewer this application would be routed to, and why.

        Read-only; nothing is written. Order: program officer, then the IC's
        NITRD representative, then the NITRD-SIA queue. Subprojects use their
        parent award's routing.
        """
        _ = SourceInfo(tables=[EXPORTER_PROJECTS])
        raise not_implemented("portal_get_reviewer_assignment")
