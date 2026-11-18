import logging
from typing import Any, Optional, Type, TypeVar
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import BaseModel
from app.core.config import get_settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def get_gemini_llm(model_name: str, temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
        max_retries=0,
    )


def get_groq_llm(model_name: str, temperature: float = 0.0) -> ChatGroq:
    settings = get_settings()
    return ChatGroq(
        model=model_name,
        groq_api_key=settings.groq_api_key,
        temperature=temperature,
        max_retries=0,
    )


def get_langfuse_callbacks(session_id: Optional[str] = None) -> list[Any]:
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return []

    try:
        from langfuse.callback import CallbackHandler

        handler = CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            session_id=session_id,
            trace_name="veriaudit-agent-run",
        )
        return [handler]
    except Exception as exc:
        logger.warning("Langfuse callback tidak aktif: %s", exc)
        return []


def invoke_structured_with_fallback(
    schema: Type[T],
    messages: list[BaseMessage],
    prefer_provider: str = "groq",
    callbacks: Optional[list[Any]] = None,
) -> tuple[T, str]:
    settings = get_settings()
    config = {"callbacks": callbacks} if callbacks else {}

    providers: list[tuple[str, Any]] = [
        (settings.groq_primary_model, get_groq_llm(settings.groq_primary_model)),
        (settings.groq_secondary_model, get_groq_llm(settings.groq_secondary_model)),
        (
            settings.gemini_vision_models[0],
            get_gemini_llm(settings.gemini_vision_models[0]),
        ),
    ]

    last_error: Optional[Exception] = None
    for provider_name, llm in providers:
        try:
            structured_llm = llm.with_structured_output(schema)
            result = structured_llm.invoke(messages, config=config)
            if result is not None:
                return result, provider_name
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Provider %s gagal, beralih ke fallback: %s", provider_name, exc
            )

    raise RuntimeError(
        f"Semua provider LLM gagal menghasilkan output terstruktur: {last_error}"
    )


def invoke_multimodal_extraction_with_fallback(
    schema: Type[T],
    system_prompt: str,
    text_prompt: str,
    page_images_b64: list[str],
    is_scanned: bool = True,
    callbacks: Optional[list[Any]] = None,
) -> tuple[T, str]:
    """
    Adaptive Multimodal Routing:
    - Jika dokumen berupa scan/foto (is_scanned=True): utamakan Gemini Vision -> Groq fallback.
    - Jika PDF memiliki teks digital (is_scanned=False): utamakan Groq 120B (cepat & hemat kuota Vision) -> Gemini Vision fallback.
    """
    settings = get_settings()
    config = {"callbacks": callbacks} if callbacks else {}

    multimodal_blocks: list[dict[str, Any]] = [{"type": "text", "text": text_prompt}]
    for img_b64 in page_images_b64[:2]:
        multimodal_blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
            }
        )

    vision_attempts: list[tuple[str, Any, list[BaseMessage]]] = [
        (
            model_name,
            get_gemini_llm(model_name),
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=multimodal_blocks),
            ],
        )
        for model_name in settings.gemini_vision_models
    ]

    text_attempt: tuple[str, Any, list[BaseMessage]] = (
        f"{settings.groq_primary_model} (fast-text)",
        get_groq_llm(settings.groq_primary_model),
        [SystemMessage(content=system_prompt), HumanMessage(content=text_prompt)],
    )

    attempts = (
        [*vision_attempts, text_attempt]
        if is_scanned
        else [text_attempt, *vision_attempts]
    )

    last_error: Optional[Exception] = None
    for provider_name, llm, msgs in attempts:
        try:
            structured_llm = llm.with_structured_output(schema)
            result = structured_llm.invoke(msgs, config=config)
            if result is not None:
                return result, provider_name
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Ekstraksi via %s gagal, beralih ke tier berikutnya: %s",
                provider_name,
                exc,
            )

    raise RuntimeError(f"Seluruh tier ekstraksi dokumen gagal: {last_error}")
