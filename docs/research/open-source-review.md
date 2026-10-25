# Open-Source Review

Reviewed 2026-10-21. Licenses, activity dates, and archive status come from the GitHub API on that date.

## What the hackathon rules allow

| Rule | What it means for reuse |
|---|---|
| §4.3 New Projects Only | The project must be newly created after the Registration Period opened. **Libraries are fine; forking an existing app as our base is not.** |
| §4.11 Intellectual Property | Open-source software is allowed if we follow its license **and** "create software that enhances and builds upon" it. |
| §4.6 / §4.11 Ownership | Our own components must be our original work. Third-party code stays clearly marked as third-party. |
| §4.7 Use of Footage | Projects "must use synthetic, football-realistic data". **No real event or tracking data**, even when its license is permissive. |
| §4.3 Third-party integrations | We must be authorized to use any SDK, API, or data, so we follow each license and keep attribution in `THIRD_PARTY_NOTICES.md`. |

Test applied to every candidate: (1) a permissive license, (2) it contains no real match data, (3) it is a component we build on, not a finished product we re-skin.

## Adopt (runtime or build dependencies)

| Project | License | Activity | How we use it | Task |
|---|---|---|---|---|
| [microsoft/agent-framework](https://github.com/microsoft/agent-framework) | MIT | active | Core agent runtime: `agent-framework-core`, `-foundry` (`FoundryChatClient`), `-orchestrations` (sequential / concurrent / handoff builders), `-devui` (dev-only workflow visualizer), `-hosting-mcp` (`WorkflowMCPTool`) | 16, 20, 33 |
| [sqlalchemy/sqlalchemy](https://github.com/sqlalchemy/sqlalchemy) | MIT | active | Stats store: one schema for SQLite (local) and Azure SQL (plan tech stack) | 14 |
| [Azure/azure-sdk-for-python](https://github.com/Azure/azure-sdk-for-python) (`azure-storage-blob`, `azure-identity`, `azure-monitor-opentelemetry-exporter`) | MIT | active | Tracking frames in Azure Blob with managed identity (optional `azure` extra); keyless sign-in to Foundry; traces to Application Insights (the exporter only, not the `azure-monitor-opentelemetry` distro, which pulls in Django and Flask instrumentation) | 14, 16, 24 |
| [mkleehammer/pyodbc](https://github.com/mkleehammer/pyodbc) | MIT | active | Azure SQL driver for SQLAlchemy; optional `azure` extra | 14, 24 |
| [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | MIT | active | FastMCP stats server | 15 |
| [PySport/kloppy](https://github.com/PySport/kloppy) | BSD-3 | active | Export our synthetic data to the standard PySport data model | 32 |
| [Azure/azure-dev](https://github.com/Azure/azure-dev) (azd) | MIT | active | `azd up` provisioning and `azd pipeline config` GitHub OIDC | 24 |
| [pmndrs/zustand](https://github.com/pmndrs/zustand) | MIT | active | Frontend state | 23 |
| [airbnb/visx](https://github.com/airbnb/visx) | MIT | active | Momentum chart and small stat charts | 23 |
| [microsoft/playwright](https://github.com/microsoft/playwright) | Apache-2.0 | active | End-to-end smoke tests and repeatable demo-video capture | 23, 31 |
| [dequelabs/axe-core](https://github.com/dequelabs/axe-core) | MPL-2.0 | active | Accessibility checks (dev-only, unmodified) | 22, 23 |
| [andrewRowlinson/mplsoccer](https://github.com/andrewRowlinson/mplsoccer) | MIT | active | Dev-only: pitch figures for the realism report, wiki, and README | 5, 25 |

## Reference or test-only (we read it or check against it; it is not shipped)

| Project | License | How we use it | Task |
|---|---|---|---|
| [Friends-of-Tracking-Data-FoTD/LaurieOnTracking](https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking) | MIT | The reference pitch control implementation, vendored into `tests/reference/` with its license header, for a parity test against our vectorized version | 6 |
| [ML-KULeuven/socceraction](https://github.com/ML-KULeuven/socceraction) | MIT | Reference for the xT method (Singh 2019) only. **Not installed:** socceraction ≥ 1.5 pins numpy < 2 (we use numpy 2) and older releases break on current pandera (checked 2026-10-21). TASK-7 cross-checks against an exact linear solve and a hand-worked example instead. VAEP is a possible later addition, trained on our own synthetic data | 7 |
| [Alek050/databallpy](https://github.com/Alek050/databallpy), [floodlight-sports/floodlight](https://github.com/floodlight-sports/floodlight) | MIT | Cross-checks for the distance, speed, and sprint metrics | 11 |
| [martineastwood/penaltyblog](https://github.com/martineastwood/penaltyblog) | MIT | Reference for the Poisson / Dixon-Coles season model (we write our own small version) | 3 |
| [Azure-Samples/azure-ai-travel-agents](https://github.com/Azure-Samples/azure-ai-travel-agents) | MIT | Reference architecture: MCP + multi-agent on Container Apps, azd and Bicep layout | 24 |
| [Azure-Samples/get-started-with-ai-agents](https://github.com/Azure-Samples/get-started-with-ai-agents) | MIT | Foundry project provisioning in Bicep | 24 |
| [microsoft/Agent-Framework-Samples](https://github.com/microsoft/Agent-Framework-Samples), [Azure-Samples/interview-coach-agent-framework](https://github.com/Azure-Samples/interview-coach-agent-framework) | MIT | Workflow, handoff, and MCP patterns | 16–20 |
| [microsoft/mcp](https://github.com/microsoft/mcp) (Azure MCP Server) | MIT | Dev workflow: managing Azure resources from GitHub Copilot or Claude Code. Shows the "Azure MCP" hero technology; described in the README | 24, 25 |
| [probberechts/d3-soccer](https://github.com/probberechts/d3-soccer) | BSD-3 | Design reference for pitch markings (we draw our own canvas) | 23 |

## Avoid

| Project | Why |
|---|---|
| [hudl/open-data](https://github.com/hudl/open-data) (StatsBomb), [metrica-sports/sample-data](https://github.com/metrica-sports/sample-data), [SkillCorner/opendata](https://github.com/SkillCorner/opendata) | Real match data. It breaks the synthetic-data rule (§4.7) and Constitution III, whatever the license (StatsBomb: custom terms; Metrica: no license; SkillCorner: MIT). |
| Published xT grids built from real data | The same reason: derived from real matches. |
| [google-research/football](https://github.com/google-research/football) | Archived, heavy C++/Linux engine. Its simulation would become the core of our data story and weaken "original work". |
| SoccER (Morra et al., 2020, MIT) | Built on a game engine. Same originality concern, and integrating it would be a large risk. |
| Forking any complete app (for example the travel-agents sample) as our base | §4.3 requires a newly created project. We use samples only as references and copy small MIT modules with attribution. |
| Agent Framework DevUI in production | Its own README says it is a sample app, not for production. We use it only in development and for the video. |
| [UnravelSports/unravelsports](https://github.com/UnravelSports/unravelsports) | MPL-2.0 graph-neural-network tooling we don't need. |

## Sources
- GitHub API repository metadata (license, stars, last push, archived), 2026-10-21
- [Agent Framework MCP with Foundry agents (Microsoft Learn)](https://learn.microsoft.com/en-us/agent-framework/user-guide/model-context-protocol/using-mcp-with-foundry-agents)
- [Build a real-world example with Agent Framework, Foundry, MCP and Aspire (Microsoft Developer Blog)](https://developer.microsoft.com/blog/build-a-real-world-example-with-microsoft-agent-framework-microsoft-foundry-mcp-and-aspire/)
- [SoccER, SoftwareX 2020](https://iris.polito.it/handle/11583/2847886)
- [kloppy docs](https://kloppy.readthedocs.io)
