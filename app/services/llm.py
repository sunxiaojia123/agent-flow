"""LLM factory for creating model instances."""

from langchain_openai import ChatOpenAI
from app.config import settings


def get_llm(model: str | None = None, temperature: float = 0.0, response_format: dict | None = None) -> ChatOpenAI:
    kwargs: dict = dict(
        model=model or settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=temperature,
    )
    if response_format:
        kwargs["model_kwargs"] = {"response_format": response_format}
    return ChatOpenAI(**kwargs)


def get_streaming_llm(model: str | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.0,
        streaming=True,
    )
