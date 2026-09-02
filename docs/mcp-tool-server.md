# MCP Tool Server

## Purpose

Step 37 exposes three existing deterministic software-asset Tools through the Model Context
Protocol. The goal is protocol interoperability, not another planning model:

```text
MCP Client
-> stdio MCP session
-> Software-Agent MCP Server
-> PackageSearchTool / DependencyAnalysisTool / VersionCompareTool
-> simulated local JSON data
```

Native Tool Calling and MCP solve different problems. Native Tool Calling lets a model choose Tools
inside the Agent loop. MCP gives an external Host a standard way to discover Tool schemas and call
the same deterministic implementations across a process boundary.

## Exposed Tools

| MCP Tool | Input | Existing implementation |
|---|---|---|
| `package_search` | required string `query` | `PackageSearchTool.run` |
| `dependency_analysis` | required string `query` | `DependencyAnalysisTool.run` |
| `version_compare` | required string `query` | `VersionCompareTool.run` |

The MCP layer contains no duplicate search logic. Typed wrapper functions generate MCP input
schemas, then return the existing normalized Tool observation with Evidence metadata.

## Run

Install the optional protocol dependency:

```bash
python -m pip install -r requirements-mcp.txt
```

Run the real Client/Server demonstration:

```bash
python -B examples/mcp_client_demo.py
```

The Client launches `python -B -m app.mcp.server`, initializes a stdio session, discovers all Tool
schemas, and calls each Tool. Run the machine-readable Gate suite with:

```bash
python -B evaluation/mcp_smoke.py
```

A Host-specific configuration can use the same command from the repository root:

```json
{
  "mcpServers": {
    "software-agent-tools": {
      "command": "python",
      "args": ["-B", "-m", "app.mcp.server"]
    }
  }
}
```

The surrounding configuration filename and working-directory field depend on the MCP Host.

## Controls

- stdio is the only enabled transport; no port is opened;
- the Server exposes exactly three read-only, allowlisted Tools;
- Tool arguments are generated from typed required `query: str` signatures;
- the child environment is allowlisted and does not forward DeepSeek or OpenAI keys;
- online LLM mode is explicitly disabled in the MCP subprocess;
- Tool facts still come from the simulated local dataset and existing Evidence normalizer;
- no Provider call, model token, or paid service is required.

## Verified Result

The local process-boundary Smoke discovered exactly three Tools and executed four calls: three
successful lookups and one expected `not_found`. All four MCP observations matched direct local Tool
execution after excluding volatile latency fields.

```text
transport: stdio
discovered_tools: 3/3
calls_returned: 4/4
local_tool_parity: 4/4
gates: 7/7 passed
provider_calls: 0
secrets_exposed: false
```

The machine-readable evidence is
[`evaluation/mcp_smoke_report.json`](../evaluation/mcp_smoke_report.json).

## Honest Boundaries

- This proves a real MCP Client/Server subprocess exchange, not deployment through Streamable HTTP.
- The project has not claimed certification against every IDE or MCP Host; the included Client uses
  the official Python SDK.
- Authentication, remote tenancy, rate limiting, and HTTP transport are outside this lightweight
  stdio experiment.
- MCP standardizes Tool discovery and invocation. It does not improve model reasoning by itself.
- All returned records are simulated project data, not enterprise assets.

## Official References

- [MCP Python SDK v2.1.1](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.1.1)
- [MCP Python SDK v2 README](https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/README.md)
- [Official stdio Client example](https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/examples/snippets/clients/stdio_client.py)

## Interview Version

> The Agent already supports model-native Tool Calling. I also wrapped three deterministic,
> read-only software-asset Tools as an MCP Server and built a real stdio Client that initializes the
> session, discovers schemas, and invokes Tools across a subprocess boundary. A four-call Smoke suite
> covered success and not-found behavior with 4/4 parity against direct Tool execution and zero
> Provider calls. This validates protocol-level reuse by an external Agent or IDE without claiming a
> production remote MCP deployment.
