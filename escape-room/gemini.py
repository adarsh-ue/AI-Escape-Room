"""Thin wrapper around the Gemini API shared by V1 and V2.

- generate(...) returns a parsed pydantic object when a schema is given, else text.
- All API / network problems become LLMError with a readable message.
- MOCK_LLM=1 makes `mock` True; callers then use their offline fallbacks.
"""
import json
import os

ERROR_HINTS = {
    400: "Bad request - check GEMINI_MODEL in .env.",
    401: "Invalid API key - check GEMINI_API_KEY in .env.",
    403: "Access denied - check the key, project access and that the free tier is enabled in AI Studio.",
    404: "Model not found - check GEMINI_MODEL in .env against the models your project can use.",
    429: "Free-tier rate limit or quota reached. Wait a moment and try again.",
}


class LLMError(Exception):
    """Friendly error that can be shown in the UI."""


class Gemini:
    def __init__(self, api_key: str, model: str):
        self.model = model
        self.mock = os.getenv("MOCK_LLM") == "1"
        self.calls = 0
        if not self.mock:
            from google import genai
            self.client = genai.Client(api_key=api_key)

    def generate(self, system: str, contents: list[dict], schema=None, temperature: float = 0.7):
        """contents: list of {"role": "user"|"model", "text": str}."""
        if self.mock:
            raise LLMError("Mock mode: no LLM available.")

        from google.genai import errors, types

        config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
        if schema is not None:
            config.response_mime_type = "application/json"
            config.response_schema = schema

        msgs = [types.Content(role=m["role"], parts=[types.Part(text=m["text"])]) for m in contents]
        try:
            self.calls += 1
            resp = self.client.models.generate_content(model=self.model, contents=msgs, config=config)
        except errors.APIError as e:
            hint = ERROR_HINTS.get(e.code, "")
            raise LLMError(f"Gemini API error ({e.code}): {e.message}. {hint}".strip()) from e
        except Exception as e:  # network / connection problems
            raise LLMError(f"Could not reach Gemini: {type(e).__name__}. Check your connection and try again.") from e

        if schema is None:
            if not resp.text:
                raise LLMError("Gemini returned an empty reply. Please try again.")
            return resp.text.strip()
        if isinstance(resp.parsed, schema):
            return resp.parsed
        try:
            return schema(**json.loads(resp.text))
        except Exception as e:
            raise LLMError("Gemini returned unreadable output. Please try again.") from e
