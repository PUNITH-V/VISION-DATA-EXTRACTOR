from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
    APIStatusError,
    OpenAIError,
)


class VisionClientError(RuntimeError):
    """Raised when the vision API request fails or returns unusable content."""


class VisionClient:
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

    def analyze_image(
        self,
        image_base64: str,
        mime_type: str,
        prompt: str,
    ) -> str:
        if not image_base64 or not image_base64.strip():
            raise ValueError("Image Base64 data cannot be empty.")

        if mime_type not in {"image/jpeg", "image/png"}:
            raise ValueError(f"Unsupported image MIME type: {mime_type}")

        data_url = f"data:{mime_type};base64,{image_base64}"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            },
                        ],
                    }
                ],
            )

        except AuthenticationError as exc:
            raise VisionClientError(
                "Authentication failed. Check your OpenRouter API key."
            ) from exc

        except RateLimitError as exc:
            raise VisionClientError(
                "Rate limit or model quota reached. Wait before trying again."
            ) from exc

        except APITimeoutError as exc:
            raise VisionClientError(
                "The vision API request timed out."
            ) from exc

        except APIConnectionError as exc:
            raise VisionClientError(
                "Could not connect to the vision API. Check your connection."
            ) from exc

        except APIStatusError as exc:
            status = exc.status_code
            if status == 404:
                detail = (
                    "Model or endpoint unavailable. Check the model ID "
                    "and its current availability."
                )
            elif status == 400:
                detail = (
                    "The API rejected the request. Check model capabilities "
                    "and request parameters."
                )
            elif status >= 500:
                detail = "The model provider encountered a server error."
            else:
                detail = f"The API returned HTTP {status}."

            raise VisionClientError(detail) from exc

        except OpenAIError as exc:
            raise VisionClientError(
                f"The vision API request failed: {exc}"
            ) from exc

        if not response.choices:
            raise VisionClientError(
                "The vision API returned no response choices."
            )

        choice = response.choices[0]
        message = choice.message
        content = message.content

        # Useful diagnostics; do not print the image or Base64 data.
        print(f"Model used: {response.model}")
        print(f"Finish reason: {choice.finish_reason}")

        if getattr(message, "refusal", None):
            raise VisionClientError(
                "The model refused the request."
            )

        if not isinstance(content, str) or not content.strip():
            raise VisionClientError(
                "The model returned empty or non-text content."
            )

        return content.strip()