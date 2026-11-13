import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class ApexMCPManager:
    def __init__(self):
        self.servers = {
            "fetch": StdioServerParameters(command="npx", args=["-y", "@modelcontextprotocol/server-fetch"]),
            "thinking": StdioServerParameters(command="npx", args=["-y", "@modelcontextprotocol/server-sequential-thinking"])
        }
        self.sessions = {}

    async def _connect(self, server_name):
        if server_name in self.sessions:
            return self.sessions[server_name]
        params = self.servers[server_name]
        read, write = await stdio_client(params).__aenter__()
        session = await ClientSession(read, write).__aenter__()
        await session.initialize()
        self.sessions[server_name] = session
        return session

    def call_tool(self, server_name, tool_name, arguments):
        async def _run():
            session = await self._connect(server_name)
            result = await session.call_tool(tool_name, arguments=arguments)
            return result.content[0].text
        return asyncio.run(_run())

mcp_manager = ApexMCPManager()

