# JavaScript tooling

This project has no Node dependencies. Ask before adding the first one (a build tool, an MCP server, a script). If you do, use pnpm rather than npm: dependency install scripts stay off (pnpm 10's default) and `pnpm-workspace.yaml` sets `minimumReleaseAge: 4320` (refuse versions under 3 days old). Run one-off tools with `pnpm dlx`, not `npx`.
