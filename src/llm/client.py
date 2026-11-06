"""Ollama client with preserved 131072 context window, structured JSON format, and retry backoff."""

import json
import logging
import re
import sys
import time
from typing import Any, Dict, Optional, Type, TypeVar, Union
from pydantic import BaseModel
import requests

from src.config import get_settings
from src.events import event_bus

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def clean_thinking_tokens(text: str) -> str:
    """Strip <think>...</think> blocks and internal monologue tokens from response."""
    if not text:
        return ""
    if "</think>" in text:
        text = text.split("</think>")[-1].strip()
    elif "<think>" in text:
        remainder = text.split("<think>", 1)[1]
        if "\n\n" in remainder:
            text = remainder.split("\n\n", 1)[1].strip()
        else:
            text = ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def extract_json_from_text(text: str) -> str:
    """Extract valid JSON substring from text containing markdown blocks or preamble."""
    cleaned = clean_thinking_tokens(text)

    # 1. Look for ```json ... ``` markdown block
    match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", cleaned, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 2. Find outermost matching braces/brackets
    start_brace = cleaned.find("{")
    start_bracket = cleaned.find("[")

    if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
        end_brace = cleaned.rfind("}")
        if end_brace != -1:
            return cleaned[start_brace:end_brace + 1].strip()
    elif start_bracket != -1:
        end_bracket = cleaned.rfind("]")
        if end_bracket != -1:
            return cleaned[start_bracket:end_bracket + 1].strip()

    return cleaned.strip()


class OllamaClient:
    """Streaming Ollama client with strict Pydantic JSON schema format and 131072 context window."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        num_ctx: Optional[int] = None,
        max_retries: int = 3,
        backoff_factor: float = 2.0
    ) -> None:
        settings = get_settings()
        self.base_url = base_url or settings.ollama_base_url
        self.model = model or settings.ollama_model
        # CRITICAL USER REQUIREMENT: Context window must always be 131072
        self.num_ctx = num_ctx or settings.num_ctx
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def is_healthy(self) -> bool:
        """Verify that Ollama server is running and accessible."""
        try:
            resp = requests.get(f"{self.base_url.rstrip('/')}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        json_schema: Optional[Union[Dict[str, Any], str]] = None,
        stream: bool = True,
        agent_name: str = "",
        run_id: str = "",
        event_sink: Optional[Any] = None
    ) -> str:
        """Invoke Ollama chat API with streaming output, thinking token extraction, and retry."""
        settings = get_settings()
        temp = temperature if temperature is not None else settings.temperature
        p_val = top_p if top_p is not None else settings.top_p
        sink = event_sink or event_bus

        url = f"{self.base_url.rstrip('/')}/api/chat"
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": stream,
            "think": True,
            "keep_alive": "30m",
            "options": {
                "temperature": temp,
                "top_p": p_val,
                "num_ctx": self.num_ctx,  # Strictly 131072
                "keep_alive": "30m"
            }
        }

        if json_schema:
            payload["format"] = json_schema

        last_exception: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                full_response = ""
                response = requests.post(url, json=payload, stream=stream, timeout=300)
                if response.status_code != 200:
                    raise RuntimeError(f"Ollama returned HTTP {response.status_code}: {response.text}")

                if stream:
                    in_think_tag = False
                    for line in response.iter_lines():
                        if line:
                            chunk = json.loads(line.decode("utf-8"))
                            if "error" in chunk:
                                raise RuntimeError(f"Ollama server error: {chunk['error']}")
                            
                            msg = chunk.get("message", {})
                            thinking_piece = msg.get("thinking", "")
                            content_piece = msg.get("content", "")

                            # 1. Dedicated thinking token from model (e.g. gemma-4-e4b with think:true)
                            if thinking_piece:
                                try:
                                    sys.stdout.write(thinking_piece)
                                    sys.stdout.flush()
                                except Exception:
                                    pass
                                if sink:
                                    sink.publish(
                                        event_type="thinking",
                                        text=thinking_piece,
                                        agent=agent_name,
                                        run_id=run_id
                                    )

                            # 2. Content tokens
                            if content_piece:
                                try:
                                    sys.stdout.write(content_piece)
                                    sys.stdout.flush()
                                except Exception:
                                    pass
                                full_response += content_piece

                                # Handle inline <think> tags if model emits them in content
                                if "</think>" in content_piece:
                                    before_close, after_close = content_piece.split("</think>", 1)
                                    clean_think = before_close.replace("<think>", "")
                                    if clean_think and sink:
                                        sink.publish(
                                            event_type="thinking",
                                            text=clean_think,
                                            agent=agent_name,
                                            run_id=run_id
                                        )
                                    in_think_tag = False
                                    if after_close and sink:
                                        sink.publish(
                                            event_type="token",
                                            text=after_close,
                                            agent=agent_name,
                                            run_id=run_id
                                        )
                                elif "<think>" in content_piece or "Thinking Process:" in content_piece or "Here's a thinking process" in content_piece:
                                    in_think_tag = True
                                    clean_text = content_piece.replace("<think>", "")
                                    if sink:
                                        sink.publish(
                                            event_type="thinking",
                                            text=clean_text,
                                            agent=agent_name,
                                            run_id=run_id
                                        )
                                elif in_think_tag and ("\n\n###" in content_piece or "\n\nÎn calitate" in content_piece or "\n\n**" in content_piece or "</think>" in content_piece):
                                    in_think_tag = False
                                    clean_text = content_piece.replace("</think>", "")
                                    if sink:
                                        sink.publish(
                                            event_type="token",
                                            text=clean_text,
                                            agent=agent_name,
                                            run_id=run_id
                                        )
                                else:
                                    ev_type = "thinking" if in_think_tag else "token"
                                    if sink:
                                        sink.publish(
                                            event_type=ev_type,
                                            text=content_piece,
                                            agent=agent_name,
                                            run_id=run_id
                                        )
                else:
                    data = response.json()
                    if "error" in data:
                        raise RuntimeError(f"Ollama server error: {data['error']}")
                    full_response = data.get("message", {}).get("content", "")

                return clean_thinking_tokens(full_response)

            except Exception as e:
                last_exception = e
                logger.warning("Ollama call failed (attempt %d/%d): %s", attempt, self.max_retries, e)
                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor ** attempt
                    time.sleep(sleep_time)

        raise RuntimeError(f"Ollama generation failed after {self.max_retries} attempts: {last_exception}")

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        stream: bool = True,
        agent_name: str = "",
        run_id: str = "",
        event_sink: Optional[Any] = None
    ) -> T:
        """Call Ollama with structured Pydantic schema in payload['format'] and parse result into model."""
        schema_dict = response_model.model_json_schema()
        raw_output = self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            top_p=top_p,
            json_schema=schema_dict,
            stream=stream,
            agent_name=agent_name,
            run_id=run_id,
            event_sink=event_sink
        )

        json_str = extract_json_from_text(raw_output)
        try:
            return response_model.model_validate_json(json_str)
        except Exception as e:
            logger.warning("Direct Pydantic model validation failed: %s. Attempting fallback parse.", e)
            parsed_dict = json.loads(json_str)
            return response_model.model_validate(parsed_dict)
