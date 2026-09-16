# website-generator

> 🎓 **Educational Note**: This repository contains purely educational code meant for students learning how to build, deploy, and optimize AI agents using the Google ADK.

This is a customized ReAct agent that acts as a **Website Generator**. It takes user queries to generate a single-page HTML/CSS/JS application and can deploy it directly to **Firebase Hosting**.

Agent generated with `agents-cli` version `1.5.0`

## Project Structure

```
website-generator/
├── app/         # Core agent code
│   ├── agent.py               # Main agent logic
│   ├── fast_api_app.py        # FastAPI Backend server
│   └── app_utils/             # App utilities and helpers
├── tests/                     # Unit, integration, and load tests
├── GEMINI.md                  # AI-assisted development guide
└── pyproject.toml             # Project dependencies
```

> 💡 **Tip:** Use [Antigravity CLI](https://antigravity.google/) for AI-assisted development - project context is pre-configured in `GEMINI.md`.

## Requirements

Before you begin, ensure you have:
- **uv**: Python package manager (used for all dependency management in this project) - [Install](https://docs.astral.sh/uv/getting-started/installation/) ([add packages](https://docs.astral.sh/uv/concepts/dependencies/) with `uv add <package>`)
- **agents-cli**: Agents CLI - Install with `uv tool install google-agents-cli`
- **Google Cloud SDK**: For GCP services - [Install](https://cloud.google.com/sdk/docs/install)


## Firebase Deployment Prerequisites

The agent includes a tool to deploy generated websites directly to Firebase Hosting using Application Default Credentials (ADC). Before deploying, ensure the following setup is complete:

1. **Enable Firebase Hosting API**: Ensure `firebasehosting.googleapis.com` is enabled in your Google Cloud Project.
   ```bash
   gcloud services enable firebasehosting.googleapis.com
   ```
2. **IAM Permissions**: The account authenticated via ADC (`gcloud auth application-default login`) must have the **Firebase Hosting Admin** role (`roles/firebasehosting.admin`) or be a project Owner/Editor.
3. **Add Firebase to Project**: Your GCP project must be linked to Firebase. Visit the [Firebase Console](https://console.firebase.google.com/) and add your existing GCP project.

### 🎓 Educational Summary: How this Agent was Upgraded (v1 to v2)

If you are a student exploring how this agent was modified from the original `geap_v1` baseline, here is a summary of the technical hurdles we solved:

- **Two-Step Firebase Hosting Tooling**: Instead of one monolithic tool, the agent now uses a `save_website_content` tool to write the massive HTML payload to a persistent temporary folder (`/tmp/geap_website_deploy`). A separate `deploy_saved_website` tool then triggers the Firebase CLI. This prevents the agent from having to resend the giant HTML string if a deployment retry is needed, which saves tokens and time!
- **Safe Preview Deployments**: To prevent the agent from accidentally overwriting your live production website, the deployment tool uses `hosting:channel:deploy ai-generated-preview` instead of a standard `deploy`. This generates a safe, temporary preview URL for testing. 
  - *Cost & Lifecycle Management*: We also pass the `--expires 30m` flag to ensure the page is automatically taken down 30 minutes after you are done testing. This is crucial for avoiding accumulated charges or orphaned testing environments!
- **Node.js Strict Engine Bypasses**: The Firebase CLI strictly expects LTS versions of Node.js (v20, v22, v24). If a developer or server runs an odd version (like v25), the CLI throws an `EBADENGINE` error. We bypassed this by injecting `npm_config_engine_strict=false` directly into the subprocess environment before running `npx`.
- **Automatic Project ID Resolution**: The Firebase CLI strictly requires a `.firebaserc` file to know which project to deploy to. Since we deploy from a temporary directory, we solved this by explicitly fetching the project ID and passing it via the `--project` flag. The tool intelligently checks for `GOOGLE_CLOUD_PROJECT` first (for Google Cloud serverless environments like Cloud Run) and falls back to `gcloud config get-value project` (for local development).

## Quick Start

Install `agents-cli` and its skills if not already installed:

```bash
uvx google-agents-cli setup
```

Install required packages:

```bash
agents-cli install
```

Test the agent with a local web server:

```bash
agents-cli playground
```

You can also use features from the [ADK](https://adk.dev/) CLI with `uv run adk`.

## Commands

| Command              | Description                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `agents-cli install` | Install dependencies using uv                                                         |
| `agents-cli playground` | Launch local development environment                                                  |
| `agents-cli lint`    | Run code quality checks                                                               |
| `agents-cli eval`    | Evaluate agent behavior (generate, grade, analyze, and more — see `agents-cli eval --help`) |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests                                                        |
| `agents-cli deploy`  | Deploy agent to Agent Runtime                                                                |
| `agents-cli publish gemini-enterprise` | Register deployed agent to Gemini Enterprise                    || [A2A Inspector](https://github.com/a2aproject/a2a-inspector) | Launch A2A Protocol Inspector                                                        |

## 🛠️ Project Management

| Command | What It Does |
|---------|--------------|
| `agents-cli scaffold enhance` | Add CI/CD pipelines and Terraform infrastructure |
| `agents-cli infra cicd` | One-command setup of entire CI/CD pipeline + infrastructure |
| `agents-cli scaffold upgrade` | Auto-upgrade to latest version while preserving customizations |

---

## Development

Edit your agent logic in `app/agent.py` and test with `agents-cli playground` - it auto-reloads on save.

## Deployment

```bash
gcloud config set project <your-project-id>
agents-cli deploy
```

To add CI/CD and Terraform, run `agents-cli scaffold enhance`.
To set up your production infrastructure, run `agents-cli infra cicd`.

## Observability

Built-in telemetry exports to Cloud Trace, BigQuery, and Cloud Logging.

## A2A Inspector

This agent supports the [A2A Protocol](https://a2a-protocol.org/). Use the [A2A Inspector](https://github.com/a2aproject/a2a-inspector) to test interoperability.
See the [A2A Inspector docs](https://github.com/a2aproject/a2a-inspector) for details.
