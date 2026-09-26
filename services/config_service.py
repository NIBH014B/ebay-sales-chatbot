from collections.abc import Mapping, MutableMapping


STREAMLIT_SETTING_KEYS = (
    "GITHUB_REPO_URL",
    "GITHUB_TOKEN",
    "GITHUB_BRANCH",
    "GITHUB_DATA_PATH",
    "GITHUB_PURCHASE_PRICE_URL",
    "GOOGLE_API_KEY",
    "TYPESAFE_API_KEY",
    "GEMINI_MODEL",
    "DATA_REFRESH_HOURS",
)


def load_streamlit_secrets(secrets: Mapping[str, object], environment: MutableMapping[str, str]) -> None:
    for key in STREAMLIT_SETTING_KEYS:
        value = secrets.get(key)
        if not environment.get(key) and value is not None and str(value).strip():
            environment[key] = str(value)