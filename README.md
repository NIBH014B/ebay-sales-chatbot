# Sales Intelligence AI

A Streamlit chat app that uses Google ADK and Gemini to interpret questions, while Python/Pandas performs sales filtering, joins, and arithmetic. Repository files are read through the GitHub API and cached by commit and blob hash. A local `local_data/` folder is also supported for development.

## Prerequisites

- Python 3.11 or newer (Python 3.12 is a good default)
- A Google AI Studio API key with Gemini API access
- A GitHub repository containing CSV, XLSX, XLS, or JSON data
- A GitHub personal access token only when the repository is private; grant read access to repository contents

## Install

From this project directory, create and activate a virtual environment, then install dependencies:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the values. Create a Google API key in Google AI Studio. For GitHub, create a fine-grained personal access token restricted to the target repository with `Contents: Read-only`; leave `GITHUB_TOKEN` empty for public repositories. Never commit `.env` or share its contents.

```dotenv
GITHUB_REPO_URL=https://github.com/owner/repository
GITHUB_TOKEN=
GITHUB_BRANCH=main
GITHUB_DATA_PATH=Raw Sales Data
GITHUB_PURCHASE_PRICE_URL=https://github.com/org/purchase-repository/blob/<commit>/path/Purchase%20Price.xlsx
GOOGLE_API_KEY=your-key
GEMINI_MODEL=gemini-2.5-flash
```

The GitHub URL must be a standard `github.com/owner/repository` URL. `GITHUB_DATA_PATH` optionally limits discovery to a repository subdirectory, such as `Raw Sales Data`; leave it empty to inspect the entire selected branch. `GITHUB_PURCHASE_PRICE_URL` optionally points to a pinned GitHub `blob` URL for a purchase-price workbook in another repository. The app considers CSV, Excel, and JSON files. For local-only development, omit `GITHUB_REPO_URL` and place datasets in `local_data/`.

For Streamlit Community Cloud, add the same uppercase keys to the app's Secrets settings using TOML format. The app reads these values from `st.secrets` when an environment variable is not set. Keep credentials in the host's secret manager; do not commit them.

```toml
GITHUB_REPO_URL = "https://github.com/owner/repository"
GITHUB_TOKEN = "your-read-only-token"
GITHUB_BRANCH = "main"
GITHUB_DATA_PATH = "Raw Sales Data"
GITHUB_PURCHASE_PRICE_URL = "https://github.com/org/repository/blob/<commit>/path/Purchase%20Price.xlsx"
GOOGLE_API_KEY = "your-google-api-key"
GEMINI_MODEL = "gemini-2.5-flash"
```

## Data Expectations

File names are not fixed. Column discovery recognizes common labels for product code/SKU, product name, date, quantity, buying price, selling price, revenue, order ID, and customer. Sales records need a product code, quantity, and a selling-price, revenue, or order field to be identified as sales. Price joins use normalized product codes; conflicting duplicate price mappings are treated as ambiguous and are not used. Profit is reported only where both buying and selling prices are available. Missing matches and source files are included in tool results.

The repository's product code is the join key between sales, product, and purchase-price datasets. If the exports do not contain a reliable shared code, the app cannot infer a relationship from product names.

## Run

```powershell
streamlit run app.py
```

The app discovers and loads data at startup. Restart it to refresh; unchanged GitHub blobs are served from `.cache/github/`, organized under the branch commit. Gemini conversation history is held in memory for the active Streamlit session.

Example questions:

- What is the buying price for SKU ABC123?
- Show me everything about product ABC123.
- Which products had the highest gross profit in August 2026?
- Compare revenue in July and August 2026.
- What are the margins for those products?
- Which products sold the most units last month?

The assistant asks Python tools to calculate/filter/group the data. It must not report net profit; only gross profit and gross margin are calculated.

## Tests

Run offline tests for schema detection, code joins, revenue, cost, gross profit, margin, date filtering, missing buying prices, and tool outputs:

```powershell
python -m pip install pytest
python -m pytest -q
```

## Troubleshooting

- **GitHub authentication or 404:** Verify owner/repository, branch, and the token's read-only contents permission. Private repositories can return 404 when access is denied.
- **No sales dataset found:** Check that a supported data file has product code, quantity, and a sales-related field; inspect the sidebar warnings and detected catalog.
- **No buying price or profit:** Confirm a buying-price column and matching product codes exist. Ambiguous duplicate mappings are excluded intentionally.
- **Excel file cannot be read:** Install dependencies from `requirements.txt`; `openpyxl` handles modern `.xlsx` workbooks.
- **Gemini unavailable:** Verify `GOOGLE_API_KEY`, model availability, network access, and API quota. The app does not show stack traces or credentials in chat.
- **GitHub rate limits:** Use an appropriately scoped token and avoid repeatedly restarting the app; downloaded file content is cached per commit and blob.

## Project Layout

```text
app.py
agent/       ADK agent, prompt, and conversation runner
services/    GitHub access, schema discovery, Pandas loading and calculations
tools/       ADK-callable data tools
tests/       Offline behavior tests
local_data/  Optional local datasets (ignored by Git)
.cache/      Commit/blob-keyed GitHub cache (ignored by Git)
```
