"""Chat API routes — multi-provider LLM chat, Socratic roundtable, Claude Code mode."""

from __future__ import annotations

import os
import json
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse

import openai
import anthropic
import google.generativeai as genai

from app.code_tools import TOOL_DEFINITIONS, execute_tool, validate_working_dir

router = APIRouter(prefix="/api/chat", tags=["chat"])

# --- Lazy clients (initialized on first use to handle missing keys) ---

_openai_client: Optional[openai.AsyncOpenAI] = None
_anthropic_client: Optional[anthropic.AsyncAnthropic] = None
_grok_client: Optional[openai.AsyncOpenAI] = None
_google_configured = False


def _get_openai():
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    return _openai_client


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))
    return _anthropic_client


def _get_grok():
    global _grok_client
    if _grok_client is None:
        _grok_client = openai.AsyncOpenAI(
            api_key=os.getenv("XAI_API_KEY", ""),
            base_url="https://api.x.ai/v1",
        )
    return _grok_client


def _ensure_google():
    global _google_configured
    if not _google_configured:
        genai.configure(api_key=os.getenv("GOOGLE_AI_API_KEY", ""))
        _google_configured = True


# --- Available Models ---

MODELS = {
    "openai": {
        "name": "OpenAI",
        "models": [
            {"id": "gpt-4o", "name": "GPT-4o", "ctx": 128000},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "ctx": 128000},
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "ctx": 128000},
            {"id": "gpt-4", "name": "GPT-4", "ctx": 8192},
            {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "ctx": 16385},
            {"id": "o1", "name": "o1", "ctx": 200000, "unsupported_params": ["temperature", "top_p", "frequency_penalty", "presence_penalty"]},
            {"id": "o1-mini", "name": "o1 Mini", "ctx": 128000, "unsupported_params": ["temperature", "top_p", "frequency_penalty", "presence_penalty"]},
            {"id": "o1-pro", "name": "o1 Pro", "ctx": 200000, "unsupported_params": ["temperature", "top_p", "frequency_penalty", "presence_penalty"]},
            {"id": "o3-mini", "name": "o3 Mini", "ctx": 200000, "unsupported_params": ["temperature", "top_p", "frequency_penalty", "presence_penalty"]},
            {"id": "gpt-4.5-preview", "name": "GPT-4.5 Preview", "ctx": 128000},
        ],
        "params": {
            "temperature": {"min": 0, "max": 2, "step": 0.01, "default": 1.0},
            "top_p": {"min": 0, "max": 1, "step": 0.01, "default": 1.0},
            "max_tokens": {"min": 1, "max": 128000, "step": 1, "default": 4096},
            "frequency_penalty": {"min": -2, "max": 2, "step": 0.01, "default": 0},
            "presence_penalty": {"min": -2, "max": 2, "step": 0.01, "default": 0},
            "seed": {"min": 0, "max": 999999, "step": 1, "default": None},
        },
    },
    "anthropic": {
        "name": "Anthropic",
        "models": [
            {"id": "claude-opus-4-6", "name": "Claude Opus 4.6", "ctx": 200000},
            {"id": "claude-sonnet-4-5-20250929", "name": "Claude Sonnet 4.5", "ctx": 200000},
            {"id": "claude-haiku-4-5-20251001", "name": "Claude Haiku 4.5", "ctx": 200000},
            {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "ctx": 200000},
            {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "ctx": 200000},
            {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "ctx": 200000},
        ],
        "params": {
            "temperature": {"min": 0, "max": 1, "step": 0.01, "default": 1.0},
            "top_p": {"min": 0, "max": 1, "step": 0.01, "default": 0.999},
            "top_k": {"min": 1, "max": 500, "step": 1, "default": None},
            "max_tokens": {"min": 1, "max": 128000, "step": 1, "default": 4096},
        },
    },
    "google": {
        "name": "Google",
        "models": [
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "ctx": 1048576},
            {"id": "gemini-2.0-flash-lite", "name": "Gemini 2.0 Flash Lite", "ctx": 1048576},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "ctx": 2097152},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "ctx": 1048576},
            {"id": "gemini-1.5-flash-8b", "name": "Gemini 1.5 Flash 8B", "ctx": 1048576},
        ],
        "params": {
            "temperature": {"min": 0, "max": 2, "step": 0.01, "default": 1.0},
            "top_p": {"min": 0, "max": 1, "step": 0.01, "default": 0.95},
            "top_k": {"min": 1, "max": 100, "step": 1, "default": 40},
            "max_output_tokens": {"min": 1, "max": 65536, "step": 1, "default": 8192},
            "candidate_count": {"min": 1, "max": 1, "step": 1, "default": 1},
        },
    },
    "grok": {
        "name": "xAI (Grok)",
        "models": [
            {"id": "grok-3", "name": "Grok 3", "ctx": 131072},
            {"id": "grok-3-fast", "name": "Grok 3 Fast", "ctx": 131072},
            {"id": "grok-3-mini", "name": "Grok 3 Mini", "ctx": 131072},
            {"id": "grok-3-mini-fast", "name": "Grok 3 Mini Fast", "ctx": 131072},
            {"id": "grok-2", "name": "Grok 2", "ctx": 131072},
            {"id": "grok-2-mini", "name": "Grok 2 Mini", "ctx": 131072},
        ],
        "params": {
            "temperature": {"min": 0, "max": 2, "step": 0.01, "default": 1.0},
            "top_p": {"min": 0, "max": 1, "step": 0.01, "default": 1.0},
            "max_tokens": {"min": 1, "max": 131072, "step": 1, "default": 4096},
            "frequency_penalty": {"min": -2, "max": 2, "step": 0.01, "default": 0},
            "presence_penalty": {"min": -2, "max": 2, "step": 0.01, "default": 0},
        },
    },
}


@router.get("/models")
async def get_models():
    return MODELS


@router.get("/validate-keys")
async def validate_keys():
    results = {}

    try:
        await _get_openai().models.list()
        results["openai"] = True
    except Exception:
        results["openai"] = False

    try:
        await _get_anthropic().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        results["anthropic"] = True
    except anthropic.AuthenticationError:
        results["anthropic"] = False
    except Exception:
        results["anthropic"] = True

    try:
        _ensure_google()
        await asyncio.to_thread(lambda: list(genai.list_models()))
        results["google"] = True
    except Exception:
        results["google"] = False

    try:
        await _get_grok().models.list()
        results["grok"] = True
    except Exception:
        results["grok"] = False

    return results


def _get_unsupported_params(provider: str, model: str) -> list[str]:
    provider_data = MODELS.get(provider, {})
    for m in provider_data.get("models", []):
        if m["id"] == model:
            return m.get("unsupported_params", [])
    return []


async def stream_openai(messages, model, params):
    unsupported = _get_unsupported_params("openai", model)
    params = {k: v for k, v in params.items() if k not in unsupported}

    kwargs = {"model": model, "messages": messages, "stream": True}
    for k in ["temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty"]:
        if k in params and params[k] is not None:
            kwargs[k] = params[k]
    if params.get("seed") is not None:
        kwargs["seed"] = int(params["seed"])

    stream = await _get_openai().chat.completions.create(**kwargs)
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def stream_anthropic(messages, model, params, system_prompt=None):
    kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": params.get("max_tokens", 4096),
    }
    if params.get("temperature") is not None:
        kwargs["temperature"] = params["temperature"]
    if params.get("top_p") is not None:
        kwargs["top_p"] = params["top_p"]
    if params.get("top_k") is not None:
        kwargs["top_k"] = int(params["top_k"])
    if system_prompt:
        kwargs["system"] = system_prompt

    async with _get_anthropic().messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield text


async def stream_google(messages, model, params):
    _ensure_google()
    gen_config = {}
    if params.get("temperature") is not None:
        gen_config["temperature"] = params["temperature"]
    if params.get("top_p") is not None:
        gen_config["top_p"] = params["top_p"]
    if params.get("top_k") is not None:
        gen_config["top_k"] = int(params["top_k"])
    if params.get("max_output_tokens") is not None:
        gen_config["max_output_tokens"] = int(params["max_output_tokens"])

    gmodel = genai.GenerativeModel(model, generation_config=gen_config)
    history = []
    for msg in messages[:-1]:
        role = "user" if msg["role"] == "user" else "model"
        history.append({"role": role, "parts": [msg["content"]]})

    chat = gmodel.start_chat(history=history)
    last_msg = messages[-1]["content"] if messages else ""
    response = await asyncio.to_thread(chat.send_message, last_msg, stream=True)
    for chunk in response:
        if chunk.text:
            yield chunk.text


async def stream_grok(messages, model, params):
    kwargs = {"model": model, "messages": messages, "stream": True}
    for k in ["temperature", "top_p", "max_tokens", "frequency_penalty", "presence_penalty"]:
        if k in params and params[k] is not None:
            kwargs[k] = params[k]

    stream = await _get_grok().chat.completions.create(**kwargs)
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


async def _stream_for_provider(provider, model, messages, system_prompt, params):
    if provider == "openai":
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)
        async for token in stream_openai(api_messages, model, params):
            yield token
    elif provider == "anthropic":
        async for token in stream_anthropic(messages, model, params, system_prompt=system_prompt or None):
            yield token
    elif provider == "google":
        api_messages = list(messages)
        if system_prompt and api_messages:
            api_messages[0] = {
                **api_messages[0],
                "content": f"[System: {system_prompt}]\n\n{api_messages[0]['content']}",
            }
        async for token in stream_google(api_messages, model, params):
            yield token
    elif provider == "grok":
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)
        async for token in stream_grok(api_messages, model, params):
            yield token


@router.post("/stream")
async def chat_stream(request: Request):
    body = await request.json()
    provider = body.get("provider", "openai")
    model = body.get("model", "gpt-4o")
    messages = body.get("messages", [])
    params = body.get("params", {})
    system_prompt = body.get("system_prompt", "")

    params = {k: v for k, v in params.items() if v is not None and v != ""}
    for k, v in params.items():
        if isinstance(v, str):
            try:
                params[k] = float(v) if "." in v else int(v)
            except ValueError:
                pass

    async def event_generator():
        try:
            if provider == "openai":
                api_messages = []
                if system_prompt:
                    api_messages.append({"role": "system", "content": system_prompt})
                api_messages.extend(messages)
                gen = stream_openai(api_messages, model, params)
            elif provider == "anthropic":
                gen = stream_anthropic(messages, model, params, system_prompt=system_prompt or None)
            elif provider == "google":
                api_messages = list(messages)
                if system_prompt and api_messages:
                    api_messages[0] = {
                        **api_messages[0],
                        "content": f"[System: {system_prompt}]\n\n{api_messages[0]['content']}",
                    }
                gen = stream_google(api_messages, model, params)
            elif provider == "grok":
                api_messages = []
                if system_prompt:
                    api_messages.append({"role": "system", "content": system_prompt})
                api_messages.extend(messages)
                gen = stream_grok(api_messages, model, params)
            else:
                yield f"data: {json.dumps({'error': f'Unknown provider: {provider}'})}\n\n"
                return

            async for token in gen:
                yield f"data: {json.dumps({'token': token})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/context")
async def estimate_context(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    system_prompt = body.get("system_prompt", "")

    msg_tokens = []
    total = 0
    for msg in messages:
        est = max(1, len(msg.get("content", "")) // 4 + 4)
        msg_tokens.append({
            "role": msg.get("role"),
            "tokens": est,
            "provider": msg.get("provider"),
            "model": msg.get("model"),
        })
        total += est

    sys_tokens = len(system_prompt) // 4 + 4 if system_prompt else 0
    total += sys_tokens

    return {"messages": msg_tokens, "system_tokens": sys_tokens, "total_tokens": total}


# --- Socratic ---

SOCRATIC_DEFAULTS = [
    {
        "name": "The Dialectician",
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "system": (
            "You are The Dialectician in a Socratic roundtable. Your method is rigorous questioning. "
            "Probe assumptions, expose contradictions, and push toward deeper truths through targeted questions. "
            "Challenge vague claims with 'What do you mean by...?' and 'How do you know...?'. "
            "Be incisive but respectful. Keep responses concise (2-4 paragraphs). "
            "Address other participants by name when responding to their points."
        ),
    },
    {
        "name": "The Pragmatist",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "system": (
            "You are The Pragmatist in a Socratic roundtable. You focus on practical implications, "
            "real-world consequences, and actionable insights. When others debate abstractions, "
            "you ground the conversation: 'But what does this mean in practice?'. "
            "Draw on concrete examples, case studies, and empirical evidence. "
            "Be direct and solution-oriented. Keep responses concise (2-4 paragraphs). "
            "Address other participants by name when responding to their points."
        ),
    },
    {
        "name": "The Contrarian",
        "provider": "openai",
        "model": "gpt-4o",
        "system": (
            "You are The Contrarian in a Socratic roundtable. Your role is to challenge "
            "conventional wisdom and popular consensus. Play devil's advocate deliberately. "
            "When the group converges, introduce the strongest possible counter-argument. "
            "Steel-man opposing positions before dismantling them. Be provocative but intellectually honest. "
            "Keep responses concise (2-4 paragraphs). "
            "Address other participants by name when responding to their points."
        ),
    },
    {
        "name": "The Synthesizer",
        "provider": "anthropic",
        "model": "claude-sonnet-4-5-20250929",
        "system": (
            "You are The Synthesizer in a Socratic roundtable. You find patterns across "
            "different perspectives and build bridges between opposing views. "
            "Identify what each participant gets right, then weave their insights into a "
            "more complete picture. Highlight hidden agreements and reframe false dichotomies. "
            "You speak last in each round to integrate what others have said. "
            "Keep responses concise (2-4 paragraphs). "
            "Address other participants by name when responding to their points."
        ),
    },
]


@router.get("/socratic/defaults")
async def get_socratic_defaults():
    return SOCRATIC_DEFAULTS


@router.post("/socratic/stream")
async def socratic_stream(request: Request):
    body = await request.json()
    participants = body.get("participants", SOCRATIC_DEFAULTS)
    history = body.get("history", [])
    user_message = body.get("user_message", "")
    rounds = body.get("rounds", 1)

    if not user_message and not history:
        return JSONResponse({"error": "user_message is required"}, status_code=400)

    async def event_generator():
        convo = list(history)
        if user_message:
            convo.append({"role": "user", "content": user_message})

        try:
            for round_num in range(rounds):
                if round_num > 0:
                    yield f"data: {json.dumps({'round': round_num + 1})}\n\n"

                for p in participants:
                    name = p["name"]
                    provider = p["provider"]
                    model = p["model"]
                    persona_system = p.get("system", "")

                    roster = ", ".join(pp["name"] for pp in participants if pp["name"] != name)
                    full_system = (
                        f"{persona_system}\n\n"
                        f"The other participants in this roundtable are: {roster}.\n"
                        f"The user who posed the question is referred to as 'the user'.\n"
                        f"Your name is {name}. Always begin your response with your name followed by a colon."
                    )

                    yield f"data: {json.dumps({'participant_start': {'name': name, 'provider': provider, 'model': model}})}\n\n"

                    api_messages = [{"role": msg["role"], "content": msg["content"]} for msg in convo]

                    full_response = ""
                    if provider == "anthropic":
                        params = {"temperature": 0.8, "max_tokens": 1024}
                    else:
                        params = {"temperature": 0.8, "max_tokens": 1024, "top_p": 0.95}

                    try:
                        async for token in _stream_for_provider(provider, model, api_messages, full_system, params):
                            full_response += token
                            yield f"data: {json.dumps({'token': token})}\n\n"
                    except Exception as e:
                        error_msg = f"[{name} error: {str(e)}]"
                        yield f"data: {json.dumps({'token': error_msg})}\n\n"
                        full_response = error_msg

                    convo.append({"role": "assistant", "content": full_response})
                    yield f"data: {json.dumps({'participant_done': {'name': name, 'content': full_response}})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- Claude Code Mode ---

@router.post("/claude-code/stream")
async def claude_code_stream(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    system_prompt = body.get("system_prompt", "")
    working_dir_str = body.get("working_directory", ".")
    max_turns = min(body.get("max_turns", 25), 50)
    model = body.get("model", "claude-sonnet-4-5-20250929")
    allowed_tools = body.get("allowed_tools", None)

    try:
        working_dir = validate_working_dir(working_dir_str)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    tools = [t for t in TOOL_DEFINITIONS if not allowed_tools or t["name"] in allowed_tools]

    code_system = (
        f"You are an AI coding assistant with access to the local filesystem.\n"
        f"Working directory: {working_dir}\n"
        f"Platform: {'Windows (use PowerShell/cmd syntax)' if os.name == 'nt' else 'Unix'}\n\n"
        f"Use tools to read, write, edit files and run commands. "
        f"Always read files before editing. Use search_files to find code. "
        f"Be precise with edit_file -- the old_string must match exactly."
    )
    if system_prompt:
        code_system = f"{system_prompt}\n\n{code_system}"

    client = _get_anthropic()

    async def event_generator():
        nonlocal messages
        turn = 0

        try:
            while turn < max_turns:
                turn += 1
                yield f"data: {json.dumps({'turn': turn, 'max_turns': max_turns})}\n\n"

                stream = await client.messages.create(
                    model=model,
                    max_tokens=16384,
                    system=code_system,
                    messages=messages,
                    tools=tools,
                    stream=True,
                )

                assistant_content = []
                current_text = ""
                current_tool_name = ""
                current_tool_id = ""
                current_tool_input_json = ""
                stop_reason = None
                tool_results_cache = {}

                async for event in stream:
                    if event.type == "content_block_start":
                        block = event.content_block
                        if block.type == "text":
                            current_text = ""
                        elif block.type == "tool_use":
                            current_tool_name = block.name
                            current_tool_id = block.id
                            current_tool_input_json = ""
                            yield f"data: {json.dumps({'tool_call_start': {'name': block.name, 'id': block.id}})}\n\n"

                    elif event.type == "content_block_delta":
                        delta = event.delta
                        if delta.type == "text_delta":
                            current_text += delta.text
                            yield f"data: {json.dumps({'token': delta.text})}\n\n"
                        elif delta.type == "input_json_delta":
                            current_tool_input_json += delta.partial_json

                    elif event.type == "content_block_stop":
                        if current_text:
                            assistant_content.append({"type": "text", "text": current_text})
                            current_text = ""
                        if current_tool_name:
                            try:
                                tool_input = json.loads(current_tool_input_json) if current_tool_input_json else {}
                            except json.JSONDecodeError:
                                tool_input = {}

                            assistant_content.append({
                                "type": "tool_use",
                                "id": current_tool_id,
                                "name": current_tool_name,
                                "input": tool_input,
                            })

                            yield f"data: {json.dumps({'tool_call_input': {'id': current_tool_id, 'name': current_tool_name, 'input': tool_input}})}\n\n"

                            result = await execute_tool(current_tool_name, tool_input, working_dir)
                            tool_results_cache[current_tool_id] = result

                            yield f"data: {json.dumps({'tool_call_result': {'id': current_tool_id, 'name': current_tool_name, 'result': result}})}\n\n"

                            current_tool_name = ""
                            current_tool_id = ""
                            current_tool_input_json = ""

                    elif event.type == "message_delta":
                        stop_reason = event.delta.stop_reason

                messages.append({"role": "assistant", "content": assistant_content})

                if stop_reason == "tool_use":
                    tool_results = []
                    for block in assistant_content:
                        if block["type"] == "tool_use":
                            result = tool_results_cache.get(block["id"], {"error": "No cached result"})
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block["id"],
                                "content": result.get("output", result.get("error", "")),
                                "is_error": "error" in result,
                            })
                    messages.append({"role": "user", "content": tool_results})
                else:
                    break

            yield f"data: {json.dumps({'done': True, 'turns_used': turn})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
