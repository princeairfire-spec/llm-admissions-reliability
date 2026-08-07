"""Ask each model every benchmark question and record the raw answers.

    # what a run would cost and how long it would take — installs nothing, calls nothing
    python3 src/run_eval.py --model gemini-flash --dry-run

    # the pilot: one model, first 20 items, English, no search
    python3 src/run_eval.py --model gemini-flash --limit 20 --languages en --modes nosearch

    # a full sweep
    python3 src/run_eval.py --model gemini-flash

Output goes to results/raw/<model>_<lang>_<mode>.jsonl, one JSON object per answer.

**Nothing needs to be installed to use the Gemini or Ollama backends.** Both speak
plain HTTPS/HTTP, and this file talks to them with `urllib` from the Python standard
library. The `anthropic` package is imported only if an Anthropic model is actually
requested, so its absence costs nothing.

Two rules this file enforces:

1. **results/raw/ is append-only.** Nothing here ever edits or deletes an existing row.
   Every number in the paper is recomputed from these files, so any published result
   can be traced back to the exact model response that produced it.

2. **Re-running is safe.** On start-up the script reads what is already recorded and
   skips it. A run stopped by a daily quota, a crash, or Ctrl-C is resumed by re-running
   the same command; it does not duplicate rows and does not re-spend quota on questions
   already answered. This is what makes a free tier with a daily cap workable: run it
   again tomorrow.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

RAW_DIR = Path("results/raw")
PROMPT_VERSION = "v1_2026-08-07"

# ---------------------------------------------------------------------------
# Frozen run configuration. Changing anything here means re-running everything,
# because old and new rows would no longer be the same experimental condition.
# ---------------------------------------------------------------------------

MAX_TOKENS = 1024          # answers are one fact plus a confidence line
EFFORT = "medium"          # Anthropic backend only; recorded in the manifest
MAX_RETRIES = 4

# `rpm` is the free-tier requests-per-minute cap; the script paces itself to stay under
# it. `rpd` is the requests-per-day cap, used only to estimate how many days a sweep
# takes. Both vary by region, account age and time — read the real numbers off the
# provider's console and correct them here rather than trusting these defaults.
# Model ids are pinned, and deliberately not `-preview` or `-latest`. A preview model
# can be withdrawn and a `-latest` alias silently moves to a different model — either
# would make the recorded results impossible to reproduce, which is the one thing a
# benchmark cannot afford. Confirm what an account can actually reach with:
#   curl -H "x-goog-api-key: $GEMINI_API_KEY" \
#        https://generativelanguage.googleapis.com/v1beta/models
MODELS = {
    # Google AI Studio free tier. No card, no install.
    "gemini-flash":     {"backend": "gemini", "id": "gemini-3.6-flash",      "rpm": 10, "rpd": 250},
    "gemini-flashlite": {"backend": "gemini", "id": "gemini-3.5-flash-lite", "rpm": 15, "rpd": 1000},
    "gemini-pro":       {"backend": "gemini", "id": "gemini-2.5-pro",        "rpm": 5,  "rpd": 100},

    # Local models. Needs Ollama running; nothing else changes.
    "qwen14b":  {"backend": "ollama", "id": "qwen3:14b",  "rpm": 0, "rpd": 0},
    "llama8b":  {"backend": "ollama", "id": "llama3.1:8b", "rpm": 0, "rpd": 0},

    # Paid. Only reachable if the `anthropic` package is installed and a key is set.
    "opus5":   {"backend": "anthropic", "id": "claude-opus-5",    "rpm": 0, "rpd": 0,
                "search_tool": "web_search_20260209", "thinking": True},
    "haiku45": {"backend": "anthropic", "id": "claude-haiku-4-5", "rpm": 0, "rpd": 0,
                "search_tool": "web_search_20250305", "thinking": False},
}

# Published rates, US dollars per million tokens. Free-tier models are 0 by definition.
PRICES = {
    "claude-opus-5":    {"in": 5.00, "out": 25.00},
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00},
}


# ---------------------------------------------------------------------------
# Backends. Each returns the same dict, so score.py never learns which was used.
# ---------------------------------------------------------------------------

def http_post_json(url, payload, headers=None, timeout=120):
    """POST some JSON, get some JSON back. Standard library only.

    Raises urllib.error.HTTPError on a non-2xx status; the caller decides whether that
    is worth retrying. This is the whole HTTP client — there is nothing else to it.
    """
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ask_gemini(model_id, prompt_text, use_search):
    """Google AI Studio. Key from GEMINI_API_KEY."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "generationConfig": {"maxOutputTokens": MAX_TOKENS},
    }
    if use_search:
        # Grounding with Google Search. Counts against the same free-tier quota.
        payload["tools"] = [{"google_search": {}}]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={key}"
    body = http_post_json(url, payload)

    candidates = body.get("candidates", [])
    if not candidates:
        # A safety filter or a recitation block returns no candidate at all. That is not
        # the model judging its own knowledge, so it must not be scored as a wrong answer.
        return {"answer_text": "", "stop_reason": "blocked", "searches_used": 0,
                "input_tokens": 0, "output_tokens": 0,
                "refusal_category": str(body.get("promptFeedback", ""))[:200], "error": None}

    candidate = candidates[0]
    text = "".join(
        part.get("text", "") for part in candidate.get("content", {}).get("parts", [])
    ).strip()

    # Grounding metadata tells us whether a search actually ran — availability is not use.
    grounding = candidate.get("groundingMetadata") or {}
    searches = len(grounding.get("webSearchQueries") or [])

    usage = body.get("usageMetadata", {})
    return {
        "answer_text": text,
        "stop_reason": candidate.get("finishReason"),
        "refusal_category": None,
        "searches_used": searches,
        "input_tokens": usage.get("promptTokenCount", 0),
        "output_tokens": usage.get("candidatesTokenCount", 0),
        "error": None,
    }


def ask_ollama(model_id, prompt_text, use_search):
    """A model running locally. No key, no quota, no network beyond localhost."""
    if use_search:
        raise RuntimeError("the ollama backend has no web search — run it with --modes nosearch")

    body = http_post_json(
        "http://127.0.0.1:11434/api/generate",
        {"model": model_id, "prompt": prompt_text, "stream": False,
         "options": {"num_predict": MAX_TOKENS}},
        timeout=600,   # a local 14B model on CPU/GPU can take a while per answer
    )
    return {
        "answer_text": (body.get("response") or "").strip(),
        "stop_reason": body.get("done_reason", "stop"),
        "refusal_category": None,
        "searches_used": 0,
        "input_tokens": body.get("prompt_eval_count", 0),
        "output_tokens": body.get("eval_count", 0),
        "error": None,
    }


def ask_anthropic(model_key, prompt_text, use_search):
    """Paid API. Imported lazily so the package is not needed for the free backends."""
    import anthropic   # noqa: PLC0415 — deliberate: keeps this an optional dependency

    config = MODELS[model_key]
    client = anthropic.Anthropic()
    request = {
        "model": config["id"],
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt_text}],
    }
    if config.get("thinking"):
        request["thinking"] = {"type": "adaptive"}
        request["output_config"] = {"effort": EFFORT}
    if use_search:
        request["tools"] = [{"type": config["search_tool"], "name": "web_search"}]

    response = client.messages.create(**request)

    if response.stop_reason == "refusal":
        return {"answer_text": "", "stop_reason": "refusal", "searches_used": 0,
                "refusal_category": getattr(getattr(response, "stop_details", None), "category", None),
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens, "error": None}

    return {
        "answer_text": "".join(b.text for b in response.content if b.type == "text").strip(),
        "stop_reason": response.stop_reason,
        "refusal_category": None,
        "searches_used": sum(1 for b in response.content if b.type == "server_tool_use"),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "error": None,
    }


class DailyQuotaReached(Exception):
    """Raised when the provider says the daily cap is spent.

    Not an error condition. The correct response is to stop cleanly and re-run
    tomorrow; everything already written is kept and will be skipped on resume.
    """


def ask(model_key, prompt_text, use_search):
    """Dispatch to a backend, with retries on transient failures.

    A failure that survives all retries is recorded as a row carrying an `error` field
    rather than being dropped. A missing row would silently bias the results toward
    whatever happened to succeed.
    """
    backend = MODELS[model_key]["backend"]
    model_id = MODELS[model_key]["id"]

    for attempt in range(MAX_RETRIES):
        try:
            if backend == "gemini":
                return ask_gemini(model_id, prompt_text, use_search)
            if backend == "ollama":
                return ask_ollama(model_id, prompt_text, use_search)
            return ask_anthropic(model_key, prompt_text, use_search)

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            if exc.code == 429:
                # A free tier returns 429 both for "too fast" and for "done for today".
                # Only the message distinguishes them, and only one is worth waiting out.
                if "PerDay" in detail or "per day" in detail.lower():
                    raise DailyQuotaReached(detail) from exc
                wait = 2 ** attempt * 15
                print(f"    rate limited, waiting {wait}s", flush=True)
                time.sleep(wait)
            elif exc.code >= 500:
                time.sleep(2 ** attempt * 3)
            else:
                # 4xx is our bug, not a transient failure; retrying is pointless.
                return {"answer_text": "", "stop_reason": None, "refusal_category": None,
                        "searches_used": 0, "input_tokens": 0, "output_tokens": 0,
                        "error": f"HTTP {exc.code}: {detail}"}
        except urllib.error.URLError as exc:
            if backend == "ollama":
                return {"answer_text": "", "stop_reason": None, "refusal_category": None,
                        "searches_used": 0, "input_tokens": 0, "output_tokens": 0,
                        "error": f"cannot reach Ollama on 127.0.0.1:11434 — is it running? ({exc.reason})"}
            time.sleep(2 ** attempt * 3)
        except (TimeoutError, json.JSONDecodeError) as exc:
            time.sleep(2 ** attempt * 3)
            last_error = str(exc)

    return {"answer_text": "", "stop_reason": None, "refusal_category": None,
            "searches_used": 0, "input_tokens": 0, "output_tokens": 0,
            "error": f"failed after {MAX_RETRIES} attempts"}


# ---------------------------------------------------------------------------

def load_benchmark(path, limit=None):
    items = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return items[:limit] if limit else items


def load_prompt(language):
    return Path(f"prompts/{PROMPT_VERSION}_{language}.txt").read_text(encoding="utf-8")


def already_done(output_path):
    """Item ids already recorded in this file, so a resumed run skips them."""
    if not output_path.exists():
        return set()
    done = set()
    for line in output_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                done.add(json.loads(line)["item_id"])
            except (json.JSONDecodeError, KeyError):
                continue   # a truncated final line from a hard kill; ignore it
    return done


def estimate(model_key, n_calls, use_search):
    """Cost in dollars and wall-clock in days, so nobody starts a run blind."""
    config = MODELS[model_key]
    price = PRICES.get(config["id"])
    if price:
        input_tokens = 250 + (3500 if use_search else 0)
        dollars = n_calls * (input_tokens * price["in"] + 400 * price["out"]) / 1_000_000
    else:
        dollars = 0.0
    days = n_calls / config["rpd"] if config.get("rpd") else 0
    return dollars, days


def run(model_key, items, language, mode, dry_run):
    use_search = mode == "search"
    output_path = RAW_DIR / f"{model_key}_{language}_{mode}.jsonl"
    done = already_done(output_path)
    todo = [item for item in items if item["id"] not in done]

    dollars, days = estimate(model_key, len(todo), use_search)
    print(f"\n{model_key} / {language} / {mode}")
    print(f"  {len(items)} items, {len(done)} already recorded, {len(todo)} to run")
    print(f"  cost: ${dollars:.2f}" + (f"   about {days:.1f} day(s) at the free daily cap" if days > 1 else ""))
    if dry_run or not todo:
        return len(todo)

    # Pace requests to stay under the per-minute cap rather than being throttled.
    pause = 60.0 / MODELS[model_key]["rpm"] if MODELS[model_key].get("rpm") else 0.5
    template = load_prompt(language)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Append mode, flushed per row: a crash loses at most one answer, and nothing
    # already written can be rewritten.
    with output_path.open("a", encoding="utf-8") as out:
        for index, item in enumerate(todo, start=1):
            question = item[f"question_{language}"]
            try:
                result = ask(model_key, template.format(question=question), use_search)
            except DailyQuotaReached as exc:
                print(f"\n  daily quota reached after {index - 1} answers this session.")
                print(f"  {len(todo) - index + 1} questions left. Re-run the same command "
                      f"tomorrow — finished answers are kept and skipped.")
                print(f"  provider said: {str(exc)[:160]}")
                return len(todo) - index + 1

            out.write(json.dumps({
                "item_id": item["id"],
                "model": MODELS[model_key]["id"],
                "model_key": model_key,
                "backend": MODELS[model_key]["backend"],
                "language": language,
                "mode": mode,
                "prompt_version": PROMPT_VERSION,
                "effort": EFFORT if MODELS[model_key].get("thinking") else None,
                "asked_at": datetime.now(timezone.utc).isoformat(),
                "question": question,
                **result,
            }, ensure_ascii=False) + "\n")
            out.flush()

            marker = "!" if result["error"] else " "
            preview = (result["answer_text"] or result["error"] or "").replace("\n", " ")[:60]
            print(f"  {marker}[{index}/{len(todo)}] {item['id']:38} {preview}", flush=True)
            time.sleep(pause)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", default="data/benchmark.jsonl")
    parser.add_argument("--model", required=True, choices=sorted(MODELS))
    parser.add_argument("--languages", default="en,ru")
    parser.add_argument("--modes", default="nosearch,search")
    parser.add_argument("--limit", type=int, help="only the first N items — use this for the pilot")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, call nothing")
    args = parser.parse_args()

    backend = MODELS[args.model]["backend"]
    if not args.dry_run:
        if backend == "gemini" and not os.environ.get("GEMINI_API_KEY"):
            print("error: GEMINI_API_KEY is not set.\n"
                  "  Get a free key at https://aistudio.google.com/apikey (no card, no install), then:\n"
                  "  export GEMINI_API_KEY=...")
            return 1
        if backend == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
            print("error: ANTHROPIC_API_KEY is not set")
            return 1

    items = load_benchmark(args.benchmark, args.limit)
    remaining = 0
    for language in args.languages.split(","):
        for mode in args.modes.split(","):
            remaining += run(args.model, items, language, mode, args.dry_run)

    if not args.dry_run:
        # Without a manifest, a results directory six months from now is a pile of
        # numbers with no experimental condition attached.
        (RAW_DIR / f"MANIFEST_{args.model}.json").write_text(json.dumps({
            "model": MODELS[args.model]["id"],
            "backend": backend,
            "prompt_version": PROMPT_VERSION,
            "effort": EFFORT if MODELS[args.model].get("thinking") else None,
            "max_tokens": MAX_TOKENS,
            "benchmark": args.benchmark,
            "languages": args.languages.split(","),
            "modes": args.modes.split(","),
            "last_run_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2), encoding="utf-8")

    if remaining:
        print(f"\n{remaining} question(s) still to do — re-run the same command to continue.")
    else:
        print("\ndone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
