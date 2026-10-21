
from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
    APIStatusError,
    OpenAIError,
)


class LLMClientError(RuntimeError):
    """Raised when text generation fails or returns unusable content."""


class LLMClient:
    """Generate text using an OpenAI-compatible chat completion API."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60.0,
    ):
        self.model = model
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not system_prompt.strip() or not user_prompt.strip():
            raise ValueError("Prompts cannot be empty.")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

        except AuthenticationError as exc:
            raise LLMClientError(
                "Authentication failed. Check your OpenRouter API key."
            ) from exc

        except RateLimitError as exc:
            raise LLMClientError(
                "Rate limit or model quota reached. Try again later."
            ) from exc

        except APITimeoutError as exc:
            raise LLMClientError(
                "The text-generation request timed out."
            ) from exc

        except APIConnectionError as exc:
            raise LLMClientError(
                "Could not connect to the text-generation API."
            ) from exc

        except APIStatusError as exc:
            raise LLMClientError(
                f"The API returned HTTP {exc.status_code}."
            ) from exc

        except OpenAIError as exc:
            raise LLMClientError(
                f"The text-generation request failed: {exc}"
            ) from exc

        if not response.choices:
            raise LLMClientError("The API returned no response choices.")

        content = response.choices[0].message.content

        
        if not isinstance(content, str) or not content.strip():
            raise LLMClientError(
                "The model returned empty or non-text content."
                )

        content = content.strip()

        print(f"Generation model used: {response.model}")

# Some free-router selections return status messages instead of answers.
        if content.casefold().startswith("user safety:"):
            raise LLMClientError(
                f"The selected model returned a status message instead "
                f"of an answer: {content}"
        )

        return content

