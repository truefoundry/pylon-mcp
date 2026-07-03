from __future__ import annotations

from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel

from settings import settings

PYLON_API_URL = "https://api.usepylon.com"


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
        tags: Annotated[
            list[str] | None, "Tags to apply to the ticket."
        ] = None,
    ) -> CreateIssueResponse:
        """Create a support ticket in Pylon on behalf of a user."""
        payload: dict = {
            "account_id": account_id,
            "title": title,
            "body_html": body_html,
            "requester_email": requester_email,
            "destination_metadata": {"destination": "internal"},
        }
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
