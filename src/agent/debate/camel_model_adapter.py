"""Lazy CAMEL model construction for the debate backend."""

from __future__ import annotations

from typing import Any


class CamelModelAdapter:
    """Create CAMEL ChatAgents without importing CAMEL for other modes."""

    def __init__(self, config: Any):
        self.config = config

    def create_agent(self, role: str, system_prompt: str, step_timeout=None):
        try:
            from camel.agents import ChatAgent
            from camel.models import ModelFactory
            from camel.types import ModelPlatformType
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "CAMEL-AI is required for AGENT_ARCH=debate; install requirements-camel.txt"
            ) from exc

        model_name = str(getattr(self.config, "camel_model_name", "") or "").strip()
        base_url = str(getattr(self.config, "camel_base_url", "") or "").strip()
        api_key = getattr(self.config, "camel_api_key", None)
        if not model_name or not base_url or not api_key:
            raise RuntimeError(
                "CAMEL_MODEL_NAME, CAMEL_BASE_URL, and CAMEL_API_KEY are required for CAMEL debate"
            )

        platform = getattr(ModelPlatformType, "OPENAI_COMPATIBLE_MODEL", None)
        if platform is None:
            raise RuntimeError("Installed CAMEL-AI does not support OPENAI_COMPATIBLE_MODEL")

        model = ModelFactory.create(
            model_platform=platform,
            model_type=model_name,
            url=base_url,
            api_key=api_key,
            model_config_dict={
                "temperature": float(getattr(self.config, "camel_temperature", 0.1)),
                "max_tokens": int(getattr(self.config, "camel_max_tokens", 4096)),
            },
        )
        configured_timeout = float(getattr(self.config, "agent_orchestrator_timeout_s", 600) or 600)
        effective_timeout = float(step_timeout) if step_timeout and step_timeout > 0 else configured_timeout
        return ChatAgent(
            system_message=system_prompt,
            model=model,
            max_iteration=1,
            step_timeout=effective_timeout,
        )
