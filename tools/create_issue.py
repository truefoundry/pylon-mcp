from __future__ import annotations

import html
import re
from enum import Enum
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel

from settings import settings


class Priority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

PYLON_API_URL = "https://api.usepylon.com"

# Must match an email app configured in Pylon, otherwise issue creation is rejected.
PYLON_SENDER_EMAIL = "support@truefoundry.com"

_ENTITY_TAG = re.compile(r"&lt;\s*/?\s*[a-zA-Z]")
_REAL_TAG = re.compile(r"<\s*/?\s*[a-zA-Z]")


def _decode_if_entity_encoded(body_html: str) -> str:
    """Recover markup from bodies whose tags arrive entity-encoded.

    Callers sometimes send `&lt;p&gt;` instead of `<p>`. Pylon stores that
    faithfully and renders the tags as visible text, so decode it back. Only
    applied when no real tags are present, to avoid mangling bodies that
    legitimately mix markup with escaped literals.
    """
    if _REAL_TAG.search(body_html) or not _ENTITY_TAG.search(body_html):
        return body_html
    return html.unescape(body_html)


class CreateIssueResponse(BaseModel):
    id: str
    number: int
    title: str
    state: str
    link: str | None = None


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def create_issue(
        account_id: Annotated[
            str,
            "Pylon account ID for the tenant. Get this from the get_pylon_account_id tool.",
        ],
        title: Annotated[str, "Title of the support ticket."],
        body_html: Annotated[str, "HTML content of the ticket body."],
        requester_email: Annotated[
            str, "Email of the user creating the ticket."
        ],
        priority: Annotated[
            Priority | None,
            "Ticket priority.",
        ] = None,
        tags: Annotated[
            list[str] | None, "Tags to apply to the ticket."
        ] = None,
    ) -> CreateIssueResponse:
        """Create a support ticket in Pylon on behalf of a user.

        The requester is emailed the ticket and can reply to it, so write
        body_html as a message addressed to the support team, not a summary.
        """
        payload: dict = {
            "account_id": account_id,
            "title": title,
            "body_html": _decode_if_entity_encoded(body_html),
            "requester_email": requester_email,
            "destination_metadata": {
                "destination": "email",
                "email": PYLON_SENDER_EMAIL,
            },
        }
        if priority:
            payload["priority"] = priority.value
        if tags:
            payload["tags"] = tags

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PYLON_API_URL}/issues",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.pylon_api_key}",
                },
                json=payload,
                timeout=30,
            )
            if response.status_code == 429:
                retry_after = response.headers.get("X-Retry-After", "60")
                raise Exception(
                    f"Rate limit exceeded. Wait {retry_after} seconds before retrying."
                )
            if not response.is_success:
                error_body = (
                    response.json()
                    if "application/json" in response.headers.get("content-type", "")
                    else {}
                )
                errors = error_body.get("errors", [])
                detail = "; ".join(errors) if errors else response.text
                raise Exception(f"Pylon API error ({response.status_code}): {detail}")
            issue = response.json().get("data", {})
            return CreateIssueResponse(
                id=issue["id"],
                number=issue["number"],
                title=issue["title"],
                state=issue["state"],
                link=issue.get("link"),
            )
