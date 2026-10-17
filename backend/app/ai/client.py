"""Official SDK adapter; no tools, provider-side conversation or silent retries."""
import asyncio
import json
import openai
from pydantic import ValidationError
from app.core.exceptions import ApiError
from app.ai.prompts import SYSTEM_PROMPT
from app.ai.classification import ALLOWED_UNCERTAINTIES
from app.ai.bindings import generation_model, canonical_draft


def input_size(schema, payload, task):
    content = json.dumps({"task": task, "untrusted_data": payload}, ensure_ascii=False, separators=(",", ":"))
    return len((SYSTEM_PROMPT + content + json.dumps(generation_model(schema, payload).model_json_schema())).encode("utf-8"))


class ResearchClient:
    def __init__(self, settings, sdk=None):
        self.settings = settings
        self.sdk = sdk

    async def close(self):
        if self.sdk is not None:
            await self.sdk.close()

    async def generate(self, schema, payload, task):
        if self.sdk is None:
            self.sdk = openai.AsyncOpenAI(api_key=self.settings.openai_api_key,
                                         base_url="https://api.openai.com/v1",
                                         timeout=self.settings.openai_request_timeout, max_retries=0)
        content = json.dumps({"task": task, "untrusted_data": payload}, ensure_ascii=False, separators=(",", ":"))
        # Bind parsing to the exact serialized request, not a mutable caller or
        # another company's registry while the network request is in flight.
        request_data = json.loads(content)["untrusted_data"]
        package = request_data.get("evidence", request_data)
        registry = package.get("registry", {})
        output_model = generation_model(schema, request_data)
        # UTF-8 bytes upper-bound token count conservatively, including schema.
        size = input_size(schema, request_data, task)
        if size > self.settings.ai_max_context_tokens:
            raise ApiError("ai_context_too_large", "The research context exceeds the configured input budget.", 422)
        try:
            response = await asyncio.wait_for(self.sdk.responses.create(
                model=self.settings.openai_model, instructions=SYSTEM_PROMPT,
                input=[{"role": "user", "content": content}],
                text={"format": {"type": "json_schema", "name": schema.__name__, "strict": True,
                                 "schema": output_model.model_json_schema()}},
                max_output_tokens=self.settings.openai_max_output_tokens,
                store=False, tools=[], tool_choice="none", truncation="disabled"),
                timeout=self.settings.openai_request_timeout)
            # Inspect completion before parsing: SDK parse helpers can attempt to
            # validate a truncated JSON fragment before callers can see status.
            if response.status != "completed" or not response.output_text:
                raise ApiError("ai_incomplete_response", "AI research was incomplete or refused. No report was substituted.", 502)
            if len(response.output_text.encode("utf-8")) > 160000:
                raise ApiError("ai_response_too_large", "The AI response exceeded the permitted size.", 502)
            result = canonical_draft(schema, output_model.model_validate_json(response.output_text), registry)
            if len(result.model_dump_json().encode("utf-8")) > 160000:
                raise ApiError("ai_response_too_large", "The AI response exceeded the permitted size.", 502)
            return result
        except ApiError:
            raise
        except (asyncio.TimeoutError, openai.APITimeoutError):
            raise ApiError("ai_timeout", "AI research timed out. Please try again later.", 504) from None
        except openai.AuthenticationError:
            raise ApiError("ai_authentication_failed", "AI provider authentication failed. Check the server configuration.", 503) from None
        except openai.RateLimitError:
            raise ApiError("ai_provider_rate_limited", "The AI provider is rate limited or its quota is unavailable.", 429) from None
        except ValidationError as error:
            # Only enum labels and the bounded field path leave the parser;
            # Pydantic's raw input/context may contain untrusted private prose.
            mismatch = next((item for item in error.errors() if item["type"] == "category_uncertainty_mismatch"), None)
            if mismatch:
                context = mismatch["ctx"]
                raise ApiError("conflicting_ai_category", "The AI response used an invalid category and uncertainty combination.", 502,
                               {"rule": "category_uncertainty_mismatch", "field": list(mismatch["loc"]),
                                "finding_category": context["category"], "finding_uncertainty": context["uncertainty"],
                                "allowed_uncertainties": list(ALLOWED_UNCERTAINTIES[context["category"]])}) from None
            raise ApiError("invalid_ai_output", "The AI provider returned an invalid structured response.", 502) from None
        except ValueError:
            raise ApiError("invalid_ai_output", "The AI provider returned an invalid structured response.", 502) from None
        except openai.APIError:
            raise ApiError("ai_provider_unavailable", "The AI provider could not complete this request.", 503) from None
        except openai.OpenAIError:
            raise ApiError("invalid_ai_output", "The AI provider could not return a complete permitted structured response.", 502) from None
