# Website Builder Simple Agent

This project is a minimal Agent Development Kit (ADK) app that uses a single LLM-powered agent to generate complete HTML+CSS+JS web pages from natural language prompts. The generated content is saved to a timestamped `.html` file and can be opened in a browser.

---

## 📦 Features

- ✅ Gemini-powered LLM agent using Google ADK
- ✅ Takes natural language queries like “Create a landing page with a red button”
- ✅ Generates clean, complete HTML pages with inline CSS/JS
- ✅ Saves output as a timestamped `.html` file
- ✅ Easily extendable with sub-agents and more tools

---

## 📂 Project Structure

```text
version_1_website_builder_simple
├── website_builder_simple/        # Main agent
│   ├── agent.py
│   ├── __init__.py
│   ├── instructions.txt
│   └── description.txt
├── tools/
│   ├── __init__.py
│   └── file_writer_tool.py        # Tool to write HTML files
├── utils/
│   ├── __init__.py
│   └── file_loader.py             # Utility for reading prompt files
├── output/                        # Auto-generated folder with HTML outputs
└── __init__.py                    # Exposes `root_agent` to ADK
```

---

## 🚀 Quickstart

### 1. Clone the Repo

```bash
git clone https://github.com/theailanguage/adk_samples.git
```

### 2. Set Up Python Environment
Required - Python 3.11+, uv, vs code and git
```bash
cd adk_samples/version_1_website_builder_simple
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate.bat on Windows
uv sync --all-groups
```

### 3. Add Your API Key

Create a `.env` file in the project root inside version_1_website_builder_simple:

```env
GOOGLE_API_KEY=your-google-api-key
GOOGLE_GENAI_USE_VERTEXAI=FALSE
```

You can get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey).

---

### 4. Run the Agent UI

```bash
cd adk_samples/version_1_website_builder_simple
adk web ./agents
```

Then open `http://localhost:8000` in your browser and select `website_builder_simple` from the agents list.

---

## 💬 Example Prompt

```
Create a webpage with a pink background and a green heading that says Hello ADK! Write this to an output file using tht tool.
```

This will generate a complete `.html` file in the `output/` folder.

---

## 🧠 How It Works

- The agent loads instructions from `instructions.txt`
- When you type a prompt, the agent generates the HTML
- It uses the `write_to_file` tool to save it
- Output file: `output/240610_132455_generated_page.html`

---

## 🛠️ Extending the Project

You can easily:
- Add sub-agents (e.g. requirement writer, layout planner)
- Add new tools (e.g. browser launcher, image fetcher)
- Support more output formats (e.g. React, Tailwind)

---

## 📜 License

This repository is licensed under the **GNU General Public License v3.0**.
See the [LICENSE](./LICENSE) file for full details.

---

Happy building with ADK! 🛠