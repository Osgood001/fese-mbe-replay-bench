"""Harbor Claude Code agent that expects the harness preinstalled in the task image
(built with FESE_INSTALL_AGENT=1), avoiding runtime downloads from claude.ai/apt."""
from harbor.agents.installed.claude_code import ClaudeCode


class PreinstalledClaudeCode(ClaudeCode):
    async def install(self, environment) -> None:
        await self.exec_as_agent(environment, command="claude --version")
