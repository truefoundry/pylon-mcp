from fastmcp import FastMCP

import tools.create_issue as create_issue_tool

mcp = FastMCP("pylon-mcp")

create_issue_tool.register(mcp)

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", stateless_http=True)
