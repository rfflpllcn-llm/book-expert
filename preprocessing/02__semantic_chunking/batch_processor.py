"""Batch processor for portnoy's complaint narrative analysis using LLM APIs."""

import argparse
import json
import os
import re
import shlex
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    "input_file": r"/home/rp/git/rfflpllcn-llm/book-expert/sandbox/pdf2md/portnoy_s_complaint_en-filtered.jsonl",
    "prompt_file": "/home/rp/git/rfflpllcn-llm/book-expert/sandbox/semantic_chunking/prompt.md",
    "output_raw_file": "/home/rp/git/rfflpllcn-llm/book-expert/sandbox/semantic_chunking/processed_chunks_raw.jsonl",
    "output_file": "/home/rp/git/rfflpllcn-llm/book-expert/sandbox/semantic_chunking/processed_chunks.jsonl",
    "checkpoint_file": "/home/rp/git/rfflpllcn-llm/book-expert/sandbox/semantic_chunking/.checkpoint.json",
    "errors_dir": "/home/rp/git/rfflpllcn-llm/book-expert/sandbox/semantic_chunking/errors",
    "window_size": 50,
    "window_overlap": 10,
    "requests_per_batch": 50,
    "max_tokens": 16384,
    "poll_interval": 30,
    "poll_timeout": 7200,  # 2 hours max
}

PROVIDER_CONFIG = {
    "claude": {
        "model": "claude-opus-4-6",
        "supports_batch": True,
        "batch_type": "claude",
    },
    "nebius": {
        "model": "deepseek-ai/DeepSeek-V3-0324-fast",
        "base_url": "https://api.tokenfactory.nebius.com/v1/",
        "supports_batch": False,
        "batch_type": "openai",
    },
    "openai": {
        "model": "gpt-5-mini-2025-08-07",
        "supports_batch": True,
        "batch_type": "openai",
    },
}


class LLMClient:
    """Unified interface for Claude and Nebius APIs."""

    def __init__(self, provider: str, model: str | None = None):
        self.provider = provider
        self.model = model or PROVIDER_CONFIG[provider]["model"]
        self.supports_batch = PROVIDER_CONFIG[provider]["supports_batch"]
        self.batch_type = PROVIDER_CONFIG[provider].get("batch_type", "claude")

        if provider == "claude":
            import anthropic
            self.client = anthropic.Anthropic()
        elif provider == "nebius":
            api_key = os.environ.get("NEBIUS_API_KEY")
            if not api_key:
                raise ValueError("NEBIUS_API_KEY is not set (required for --provider nebius)")
            try:
                from openai import OpenAI
            except ImportError as e:
                raise ImportError("Missing dependency: install `openai` to use --provider nebius") from e
            self.client = OpenAI(
                base_url=PROVIDER_CONFIG["nebius"]["base_url"],
                api_key=api_key,
            )
        elif provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY is not set (required for --provider openai)")
            try:
                from openai import OpenAI
            except ImportError as e:
                raise ImportError("Missing dependency: install `openai` to use --provider openai") from e

            base_url = os.environ.get("OPENAI_BASE_URL")
            if base_url:
                self.client = OpenAI(base_url=base_url, api_key=api_key)
            else:
                self.client = OpenAI(api_key=api_key)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def complete(self, system_prompt: str, user_content: str, max_tokens: int) -> str:
        """Send a completion request and return the response text."""
        if self.provider == "claude":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_content}],
            )
            if not response.content:
                raise ValueError(f"Empty response from model (stop_reason: {response.stop_reason})")
            text = response.content[0].text.strip()
            if not text:
                raise ValueError(f"Empty text in response (stop_reason: {response.stop_reason})")
            return text

        elif self.provider == "nebius":
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
            if not response.choices:
                raise ValueError("Empty response from model")
            text = response.choices[0].message.content
            if not text:
                raise ValueError("Empty text in response")
            return text.strip()

        elif self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                max_completion_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
            )
            if not response.choices:
                raise ValueError("Empty response from model")
            text = response.choices[0].message.content
            if not text:
                raise ValueError("Empty text in response")
            return text.strip()

        raise ValueError(f"Unknown provider: {self.provider}")

    def submit_batch(self, requests: list[dict], batch_file_path: Path | None = None) -> str:
        """Submit a batch of requests."""
        if self.batch_type == "claude":
            batch = self.client.messages.batches.create(requests=requests)
            return batch.id

        elif self.batch_type == "openai":
            # Write requests to JSONL file
            import tempfile
            import io

            # Convert to OpenAI batch format
            jsonl_content = ""
            for req in requests:
                openai_req = {
                    "custom_id": req["custom_id"],
                    "method": "POST",
                    "url": "/v1/chat/completions",
                    "body": {
                        "model": req["params"]["model"],
                        "max_completion_tokens": req["params"]["max_tokens"],
                        "messages": [
                            {"role": "system", "content": req["params"]["system"][0]["text"]},
                            *req["params"]["messages"],
                        ],
                    },
                }
                jsonl_content += json.dumps(openai_req, ensure_ascii=False) + "\n"

            # Upload file
            file_obj = io.BytesIO(jsonl_content.encode("utf-8"))
            file_obj.name = "batch_input.jsonl"
            batch_input_file = self.client.files.create(
                file=file_obj,
                purpose="batch"
            )

            # Create batch
            batch = self.client.batches.create(
                input_file_id=batch_input_file.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )
            return batch.id

        raise ValueError(f"Unknown batch type: {self.batch_type}")

    def poll_batch(self, batch_id: str, poll_interval: int, timeout: int) -> object:
        """Poll batch until complete."""
        start_time = time.time()

        if self.batch_type == "claude":
            terminal_states = {"ended", "failed", "expired", "canceled"}
            success_state = "ended"
        else:  # openai
            terminal_states = {"completed", "failed", "expired", "cancelled"}
            success_state = "completed"

        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise BatchTimeoutError(f"Batch {batch_id} polling exceeded {timeout}s timeout")

            if self.batch_type == "claude":
                batch = self.client.messages.batches.retrieve(batch_id)
                status = batch.processing_status
            else:  # openai
                batch = self.client.batches.retrieve(batch_id)
                status = batch.status

            if status in terminal_states:
                if status != success_state:
                    raise BatchFailedError(f"Batch {batch_id} ended with status: {status}")
                return batch

            time.sleep(poll_interval)

    def retrieve_batch_results(self, batch_id: str) -> list[dict]:
        """Retrieve results from a completed batch."""
        results = []

        if self.batch_type == "claude":
            for result in self.client.messages.batches.results(batch_id):
                window_id = result.custom_id

                if result.result.type == "succeeded":
                    raw_text = ""
                    for block in result.result.message.content:
                        if hasattr(block, "text"):
                            raw_text += block.text

                    try:
                        output = extract_json_from_response(raw_text)
                        results.append({
                            "window_id": window_id,
                            "success": True,
                            "output": output,
                        })
                    except json.JSONDecodeError as e:
                        results.append({
                            "window_id": window_id,
                            "success": False,
                            "error": f"Invalid JSON: {e}",
                            "raw_output": raw_text,
                        })
                else:
                    error_msg = getattr(result.result.error, "message", str(result.result))
                    results.append({
                        "window_id": window_id,
                        "success": False,
                        "error": error_msg,
                    })

        elif self.batch_type == "openai":
            # Get batch to find output file
            batch = self.client.batches.retrieve(batch_id)
            if not batch.output_file_id:
                raise ValueError(f"Batch {batch_id} has no output file")

            # Download results
            file_response = self.client.files.content(batch.output_file_id)
            content = file_response.content
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            results = _parse_openai_batch_output(str(content))

        return results


def _parse_openai_batch_output(content: str) -> list[dict]:
    """Parse OpenAI-style batch output JSONL into standard result records.

    Some providers return partial/variant schemas (e.g. `response: null`), so this
    parser is intentionally defensive and never raises for per-line issues.
    """
    results: list[dict] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        try:
            record = json.loads(line)
        except Exception as e:
            results.append({
                "window_id": "",
                "success": False,
                "error": f"Invalid JSONL line: {e}",
                "raw_output": raw_line,
            })
            continue

        if not isinstance(record, dict):
            results.append({
                "window_id": "",
                "success": False,
                "error": f"Invalid batch record type: {type(record).__name__}",
                "raw_output": record,
            })
            continue

        window_id = str(record.get("custom_id", "") or "")
        response_obj = record.get("response") or {}
        if not isinstance(response_obj, dict):
            response_obj = {}

        status_code = response_obj.get("status_code")
        body = response_obj.get("body") or {}
        if not isinstance(body, dict):
            body = {}

        # Treat as success if we have choices, even if status_code is missing.
        choices = body.get("choices") or []
        if status_code == 200 or choices:
            if isinstance(choices, list) and choices:
                message = choices[0].get("message") or {}
                if not isinstance(message, dict):
                    message = {}
                raw_text = message.get("content") or ""
                if not isinstance(raw_text, str):
                    raw_text = str(raw_text)
                try:
                    output = extract_json_from_response(raw_text)
                    results.append({
                        "window_id": window_id,
                        "success": True,
                        "output": output,
                    })
                except json.JSONDecodeError as e:
                    results.append({
                        "window_id": window_id,
                        "success": False,
                        "error": f"Invalid JSON: {e}",
                        "raw_output": raw_text,
                    })
            else:
                results.append({
                    "window_id": window_id,
                    "success": False,
                    "error": "No choices in response",
                    "raw_output": record,
                })
            continue

        error_obj = record.get("error") or response_obj.get("error") or {}
        if isinstance(error_obj, dict):
            error_msg = error_obj.get("message", str(error_obj))
        else:
            error_msg = str(error_obj)

        if not error_msg or error_msg == "{}":
            error_msg = "Missing response body"

        results.append({
            "window_id": window_id,
            "success": False,
            "error": error_msg,
            "raw_output": record,
        })

    return results


def load_chunks(filepath: Path) -> list[dict]:
    """Load chunks from JSONL file."""
    chunks = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def load_indices(filepath: Path) -> list[tuple[int, int]]:
    """Load index ranges from file."""
    if not filepath.exists():
        raise FileNotFoundError(f"Indices file not found: {filepath}")

    indices = []
    with open(filepath, encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            parts = line.split("-")
            if len(parts) != 2:
                raise ValueError(f"Invalid index format at line {line_num}: {line}")
            start, end = int(parts[0]), int(parts[1])
            if start > end:
                raise ValueError(f"start ({start}) must be <= end ({end}) at line {line_num}")
            indices.append((start, end))
    return indices


def generate_windows_from_indices(
    chunks: list[dict],
    indices: list[tuple[int, int]]
) -> list[dict]:
    """Generate windows based on index ranges."""
    chunk_lookup: dict[int, dict] = {}
    for chunk in chunks:
        _, num_id = _extract_numeric_key(chunk["id"])
        if num_id > 0:
            chunk_lookup[num_id] = chunk

    windows = []
    for window_num, (start, end) in enumerate(indices):
        window_chunks = []
        for num_id in range(start, end + 1):
            if num_id in chunk_lookup:
                window_chunks.append(chunk_lookup[num_id])

        if not window_chunks:
            continue

        windows.append({
            "window_id": f"window_{window_num:03d}",
            "index_range": (start, end),
            "chunks": window_chunks,
            "chunk_ids": [c["id"] for c in window_chunks],
        })

    return windows


def generate_windows(chunks: list[dict], window_size: int, overlap: int) -> list[dict]:
    """Generate sliding windows over chunks."""
    if window_size <= 0:
        raise ValueError(f"window_size must be positive, got {window_size}")
    if overlap >= window_size:
        raise ValueError(f"overlap ({overlap}) must be less than window_size ({window_size})")

    windows = []
    step = window_size - overlap
    i = 0
    window_num = 0

    while i < len(chunks):
        window_chunks = chunks[i:i + window_size]
        if window_chunks:
            windows.append({
                "window_id": f"window_{window_num:03d}",
                "start_idx": i,
                "chunks": window_chunks,
                "chunk_ids": [c["id"] for c in window_chunks],
            })
            window_num += 1
        i += step

    return windows


def build_batch_request(window: dict, system_prompt: str, model: str, max_tokens: int) -> dict:
    """Build a single batch request for a window (Claude Batch API format)."""
    chunks_jsonl = "\n".join(json.dumps(c, ensure_ascii=False) for c in window["chunks"])

    return {
        "custom_id": window["window_id"],
        "params": {
            "model": model,
            "max_tokens": max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": chunks_jsonl,
                }
            ],
        },
    }


def load_checkpoint(filepath: Path) -> dict:
    """Load checkpoint from file, or return empty checkpoint if missing."""
    if not filepath.exists():
        return {
            "total_batches": 0,
            "completed_batches": [],
            "completed_windows": [],
            "batch_ids": {},
        }
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def save_checkpoint(filepath: Path, checkpoint: dict) -> None:
    """Save checkpoint to file with timestamp."""
    checkpoint["last_updated"] = datetime.now(timezone.utc).isoformat()
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)


class BatchTimeoutError(Exception):
    """Raised when batch polling exceeds timeout."""
    pass


class BatchFailedError(Exception):
    """Raised when batch ends in a failed state."""
    pass


class BatchNotSupportedError(Exception):
    """Raised when provider batch API is unavailable/mismatched."""
    pass


def submit_batch(client: object, requests: list[dict]) -> str:
    """Submit a Claude batch request via an Anthropic-like client.

    Kept for backwards compatibility with existing tests/helpers.
    """
    batch = client.messages.batches.create(requests=requests)
    return batch.id


def poll_batch_until_complete(
    client: object,
    batch_id: str,
    poll_interval: int = 30,
    timeout: int = 7200,
) -> object:
    """Poll a Claude batch until processing is complete.

    Kept for backwards compatibility with existing tests/helpers.
    """
    start_time = time.time()
    terminal_states = {"ended", "failed", "expired", "canceled"}

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise BatchTimeoutError(f"Batch {batch_id} polling exceeded {timeout}s timeout")

        batch = client.messages.batches.retrieve(batch_id)
        status = batch.processing_status

        if status in terminal_states:
            if status != "ended":
                raise BatchFailedError(f"Batch {batch_id} ended with status: {status}")
            return batch

        time.sleep(poll_interval)


def retrieve_batch_results(client: object, batch_id: str) -> list[dict]:
    """Retrieve results from a completed Claude batch.

    Kept for backwards compatibility with existing tests/helpers.
    """
    results: list[dict] = []

    for result in client.messages.batches.results(batch_id):
        window_id = result.custom_id

        if result.result.type == "succeeded":
            raw_text = ""
            for block in result.result.message.content:
                if hasattr(block, "text"):
                    raw_text += block.text

            try:
                output = extract_json_from_response(raw_text)
                results.append({
                    "window_id": window_id,
                    "success": True,
                    "output": output,
                })
            except json.JSONDecodeError as e:
                results.append({
                    "window_id": window_id,
                    "success": False,
                    "error": f"Invalid JSON: {e}",
                    "raw_output": raw_text,
                })
        else:
            error_msg = getattr(result.result.error, "message", str(result.result))
            results.append({
                "window_id": window_id,
                "success": False,
                "error": error_msg,
            })

    return results


def extract_json_from_response(text: str) -> dict:
    """Extract JSON from response, handling markdown fences and preambles."""
    # Try to find JSON in code fences first
    fence_pattern = r'```(?:json)?\s*\n?([\s\S]*?)\n?```'
    fence_match = re.search(fence_pattern, text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Use raw_decode to find first valid JSON object starting with {
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char == '{':
            try:
                obj, _ = decoder.raw_decode(text, i)
                return obj
            except json.JSONDecodeError:
                continue

    # Last resort: try the whole text
    return json.loads(text)


def append_raw_results(output_path: Path, results: list[dict], chunk_ids_map: dict) -> None:
    """Append successful results to raw output file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "a", encoding="utf-8") as f:
        for result in results:
            if not result["success"]:
                continue
            record = {
                "window_id": result["window_id"],
                "chunk_ids": chunk_ids_map.get(result["window_id"], []),
                "output": result["output"],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def save_error(errors_dir: Path, batch_num: int, error_data: dict) -> None:
    """Save error information with unique filename."""
    errors_dir.mkdir(parents=True, exist_ok=True)
    unique_id = uuid.uuid4().hex[:8]
    error_file = errors_dir / f"batch_{batch_num:03d}_{unique_id}.json"
    error_data["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(error_file, "w", encoding="utf-8") as f:
        json.dump(error_data, f, indent=2, ensure_ascii=False)


def _extract_numeric_key(chunk_id: str) -> tuple[str, int]:
    """Extract numeric sorting key from an ID like 'FR123' or 'SC_00001'."""
    match = re.match(r'^([^0-9]*)(\d+)', chunk_id)
    if match:
        prefix, num = match.groups()
        return (prefix, int(num))
    return (chunk_id, 0)


_HEADER_FOOTER_FIELDS = {"sc_id", "chunk_type", "chunk_ids"}


def _strip_header_footer_metadata(sc: dict) -> dict:
    """Strip metadata fields from page_header and page_footer chunks."""
    chunk_type = sc.get("chunk_type", "")
    if chunk_type in ("page_header", "page_footer"):
        return {k: v for k, v in sc.items() if k in _HEADER_FOOTER_FIELDS}
    return sc


def deduplicate_outputs(raw_records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Deduplicate semantic chunks and micro_units with globally unique IDs."""
    seen_chunk_ids: dict[tuple, tuple[str, str, dict]] = {}

    for record in reversed(raw_records):
        window_id = record.get("window_id", "")
        output = record.get("output", {})

        for sc in reversed(output.get("semantic_chunks", [])):
            key = tuple(sorted(sc.get("chunk_ids", [])))
            if key and key not in seen_chunk_ids:
                old_sc_id = sc.get("sc_id", "")
                seen_chunk_ids[key] = (window_id, old_sc_id, sc)

    sorted_items = sorted(seen_chunk_ids.items(),
                          key=lambda item: _extract_numeric_key(item[1][2].get("chunk_ids", [""])[0]))

    semantic_chunks = []
    sc_id_mapping: dict[tuple[str, str], str] = {}

    for i, (chunk_ids_key, (window_id, old_sc_id, sc)) in enumerate(sorted_items, start=1):
        new_sc_id = f"SC_{i:05d}"
        sc_copy = sc.copy()
        sc_copy["sc_id"] = new_sc_id
        sc_copy = _strip_header_footer_metadata(sc_copy)
        semantic_chunks.append(sc_copy)

        if old_sc_id:
            sc_id_mapping[(window_id, old_sc_id)] = new_sc_id

    all_micro_units: list[tuple[str, dict]] = []

    for record in raw_records:
        window_id = record.get("window_id", "")
        output = record.get("output", {})

        for mu in output.get("micro_units", []):
            referenced_scs = mu.get("semantic_chunks", [])
            if all((window_id, sc_id) in sc_id_mapping for sc_id in referenced_scs):
                all_micro_units.append((window_id, mu))

    seen_mu_keys: dict[frozenset, tuple[str, dict]] = {}

    for window_id, mu in reversed(all_micro_units):
        referenced_scs = mu.get("semantic_chunks", [])
        new_refs = tuple(sorted(sc_id_mapping[(window_id, sc_id)] for sc_id in referenced_scs))
        key = frozenset(new_refs)

        if key not in seen_mu_keys:
            seen_mu_keys[key] = (window_id, mu)

    micro_units = []
    sorted_mu_items = sorted(seen_mu_keys.items(),
                             key=lambda item: min(_extract_numeric_key(sc_id) for sc_id in item[0]))

    for i, (_, (window_id, mu)) in enumerate(sorted_mu_items, start=1):
        mu_copy = mu.copy()
        mu_copy["unit_id"] = f"MU_{i:05d}"
        old_refs = mu.get("semantic_chunks", [])
        mu_copy["semantic_chunks"] = [sc_id_mapping[(window_id, sc_id)] for sc_id in old_refs]
        micro_units.append(mu_copy)

    return semantic_chunks, micro_units


def write_final_outputs(
    sc_path: Path,
    mu_path: Path,
    semantic_chunks: list[dict],
    micro_units: list[dict],
) -> None:
    """Write deduplicated outputs to final JSON files."""
    sc_path.parent.mkdir(parents=True, exist_ok=True)
    mu_path.parent.mkdir(parents=True, exist_ok=True)

    with open(sc_path, "w", encoding="utf-8") as f:
        json.dump(semantic_chunks, f, ensure_ascii=False, indent=2)

    with open(mu_path, "w", encoding="utf-8") as f:
        json.dump(micro_units, f, ensure_ascii=False, indent=2)


def process_sequential(
    client: LLMClient,
    windows: list[dict],
    system_prompt: str,
    checkpoint_path: Path,
    output_raw_path: Path,
    errors_dir: Path,
    max_tokens: int,
    resume: bool = False,
    resume_cmd: str | None = None,
) -> None:
    """Process windows sequentially (for providers without batch API)."""
    total_windows = len(windows)
    print(f"Total windows: {total_windows} (sequential processing)")

    # Load or initialize checkpoint
    checkpoint = load_checkpoint(checkpoint_path) if resume else {
        "total_batches": 1,
        "completed_batches": [],
        "completed_windows": [],
        "batch_ids": {},
    }
    if resume_cmd:
        checkpoint["resume_command"] = resume_cmd
    completed_windows = set(checkpoint.get("completed_windows", []))

    chunk_ids_map = {w["window_id"]: w["chunk_ids"] for w in windows}

    for i, window in enumerate(windows):
        window_id = window["window_id"]

        if window_id in completed_windows:
            print(f"[{i+1}/{total_windows}] {window_id}: Already complete, skipping")
            continue

        print(f"[{i+1}/{total_windows}] {window_id}: Processing {len(window['chunks'])} chunks...")

        chunks_jsonl = "\n".join(json.dumps(c, ensure_ascii=False) for c in window["chunks"])

        try:
            start_time = time.time()
            raw_text = client.complete(system_prompt, chunks_jsonl, max_tokens)
            elapsed = time.time() - start_time

            output = extract_json_from_response(raw_text)

            # Save result
            results = [{
                "window_id": window_id,
                "success": True,
                "output": output,
            }]
            append_raw_results(output_raw_path, results, chunk_ids_map)

            # Update checkpoint
            completed_windows.add(window_id)
            checkpoint["completed_windows"] = list(completed_windows)
            save_checkpoint(checkpoint_path, checkpoint)

            print(f"[{i+1}/{total_windows}] {window_id}: Complete ({elapsed:.1f}s)")

        except Exception as e:
            print(f"[{i+1}/{total_windows}] {window_id}: Error - {e}")
            save_error(errors_dir, i, {
                "window_id": window_id,
                "error": str(e),
            })

        # Rate limiting delay between requests
        if i < total_windows - 1:
            time.sleep(1)

    # Mark batch as complete
    checkpoint["completed_batches"] = [0]
    save_checkpoint(checkpoint_path, checkpoint)
    print(f"\nCompleted {len(completed_windows)}/{total_windows} windows")


def process_batches(
    client: LLMClient,
    windows: list[dict],
    system_prompt: str,
    checkpoint_path: Path,
    output_raw_path: Path,
    errors_dir: Path,
    requests_per_batch: int,
    max_tokens: int,
    poll_interval: int,
    poll_timeout: int,
    dry_run: bool = False,
    resume: bool = False,
    resume_cmd: str | None = None,
) -> None:
    """Process all windows in batches with checkpointing (Claude Batch API)."""
    batches = []
    for i in range(0, len(windows), requests_per_batch):
        batches.append(windows[i:i + requests_per_batch])

    total_batches = len(batches)
    print(f"Total windows: {len(windows)}, split into {total_batches} batches")

    checkpoint = load_checkpoint(checkpoint_path) if resume else {
        "total_batches": total_batches,
        "completed_batches": [],
        "batch_ids": {},
    }
    checkpoint["total_batches"] = total_batches
    if resume_cmd:
        checkpoint["resume_command"] = resume_cmd

    chunk_ids_map = {w["window_id"]: w["chunk_ids"] for w in windows}

    if dry_run:
        print("\n=== DRY RUN MODE ===")
        for i, batch in enumerate(batches):
            print(f"Batch {i}/{total_batches}: {len(batch)} windows")
            for w in batch[:3]:
                print(f"  - {w['window_id']}: chunks {w['chunk_ids'][0]}..{w['chunk_ids'][-1]}")
            if len(batch) > 3:
                print(f"  ... and {len(batch) - 3} more")
        return

    for batch_num, batch_windows in enumerate(batches):
        if batch_num in checkpoint["completed_batches"]:
            print(f"Batch {batch_num + 1}/{total_batches}: Already complete, skipping")
            continue

        existing_batch_id = checkpoint["batch_ids"].get(str(batch_num))
        if existing_batch_id:
            print(f"\nBatch {batch_num + 1}/{total_batches}: Resuming existing batch {existing_batch_id}")
            batch_id = existing_batch_id
        else:
            print(f"\nBatch {batch_num + 1}/{total_batches}: Preparing {len(batch_windows)} requests...")

            requests = [
                build_batch_request(w, system_prompt, client.model, max_tokens)
                for w in batch_windows
            ]

            print(f"Batch {batch_num + 1}/{total_batches}: Submitting...")
            try:
                batch_id = client.submit_batch(requests)
                checkpoint["batch_ids"][str(batch_num)] = batch_id
                save_checkpoint(checkpoint_path, checkpoint)
                print(f"Batch {batch_num + 1}/{total_batches}: Submitted as {batch_id}")
            except Exception as e:
                if client.batch_type == "openai" and batch_num == 0 and not existing_batch_id:
                    raise BatchNotSupportedError(
                        f"OpenAI-style batch API unavailable for provider={client.provider}: {e}"
                    ) from e
                print(f"Batch {batch_num + 1}/{total_batches}: Submit failed: {e}")
                save_error(errors_dir, batch_num, {"error": str(e), "stage": "submit"})
                continue

        print(f"Batch {batch_num + 1}/{total_batches}: Polling...")
        start_time = time.time()
        try:
            client.poll_batch(batch_id, poll_interval, poll_timeout)
            elapsed = time.time() - start_time
            print(f"Batch {batch_num + 1}/{total_batches}: Complete after {elapsed:.0f}s")
        except (BatchTimeoutError, BatchFailedError) as e:
            print(f"Batch {batch_num + 1}/{total_batches}: Poll failed: {e}")
            save_error(errors_dir, batch_num, {"error": str(e), "stage": "poll", "batch_id": batch_id})
            continue

        print(f"Batch {batch_num + 1}/{total_batches}: Retrieving results...")
        try:
            results = client.retrieve_batch_results(batch_id)
            successes = sum(1 for r in results if r["success"])
            failures = len(results) - successes
            print(f"Batch {batch_num + 1}/{total_batches}: {successes} succeeded, {failures} failed")

            for r in results:
                if not r["success"]:
                    save_error(errors_dir, batch_num, {
                        "window_id": r["window_id"],
                        "error": r.get("error"),
                        "raw_output": r.get("raw_output"),
                    })

            append_raw_results(output_raw_path, results, chunk_ids_map)

        except Exception as e:
            print(f"Batch {batch_num + 1}/{total_batches}: Retrieve failed: {e}")
            save_error(errors_dir, batch_num, {"error": str(e), "stage": "retrieve", "batch_id": batch_id})
            continue

        checkpoint["completed_batches"].append(batch_num)
        save_checkpoint(checkpoint_path, checkpoint)

        progress = len(checkpoint["completed_batches"]) / total_batches * 100
        print(f"Checkpoint saved. Progress: {len(checkpoint['completed_batches'])}/{total_batches} batches ({progress:.0f}%)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Process chunks with LLM API")
    parser.add_argument("--provider", choices=["claude", "nebius", "openai"], default="claude",
                        help="LLM provider to use (default: claude)")
    parser.add_argument("--model", type=str, default=None,
                        help="Override default model for the provider")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--dry-run", action="store_true", help="Show windows without submitting")
    parser.add_argument("--batch-size", type=int, default=CONFIG["requests_per_batch"],
                        help="Requests per batch (Claude only)")
    parser.add_argument("--no-batch", action="store_true",
                        help="Force sequential processing (skip batch API even if supported)")
    parser.add_argument("--dedupe-only", action="store_true",
                        help="Only run deduplication on existing raw output")
    parser.add_argument("--base-path", type=Path, default=None,
                        help="Base path for all files (default: script directory)")
    parser.add_argument("--indices-file", type=Path, default=None,
                        help="Use index-based windows from this file (overrides sliding window)")
    args = parser.parse_args()

    base_path = args.base_path or Path(__file__).parent

    # Determine model name and create output folder
    model_name = args.model or PROVIDER_CONFIG[args.provider]["model"]
    # Sanitize model name for folder (replace / with -)
    model_safe = model_name.replace("/", "-")
    output_dir = base_path / f"output-{args.provider}-{model_safe}"

    # Paths
    input_path = base_path / CONFIG["input_file"]
    prompt_path = base_path / CONFIG["prompt_file"]
    output_raw_path = output_dir / "processed_chunks_raw.jsonl"
    output_path = output_dir / "processed_chunks.jsonl"
    micro_units_path = output_dir / "micro_units.jsonl"
    checkpoint_path = output_dir / ".checkpoint.json"
    errors_dir = output_dir / "errors"

    # Dedupe-only mode
    if args.dedupe_only:
        print(f"Running deduplication only on {output_dir}...")
        raw_records = load_chunks(output_raw_path)
        semantic_chunks, micro_units = deduplicate_outputs(raw_records)
        write_final_outputs(output_path, micro_units_path, semantic_chunks, micro_units)
        print(f"Wrote {len(semantic_chunks)} semantic chunks to {output_path}")
        print(f"Wrote {len(micro_units)} micro units to {micro_units_path}")
        return 0

    # Load inputs
    print(f"Provider: {args.provider}")
    print(f"Model: {model_name}")
    print(f"Output dir: {output_dir}")
    print(f"Loading chunks from {input_path}...")
    chunks = load_chunks(input_path)
    print(f"Loaded {len(chunks)} chunks")

    print(f"Loading prompt from {prompt_path}...")
    system_prompt = prompt_path.read_text(encoding="utf-8")

    # Generate windows
    if args.indices_file:
        print(f"Loading indices from {args.indices_file}...")
        indices_path = base_path / args.indices_file if not args.indices_file.is_absolute() else args.indices_file
        indices = load_indices(indices_path)
        print(f"Loaded {len(indices)} index ranges")
        windows = generate_windows_from_indices(chunks, indices)
        print(f"Generated {len(windows)} windows from indices")
    else:
        print(f"Generating windows (size={CONFIG['window_size']}, overlap={CONFIG['window_overlap']})...")
        windows = generate_windows(chunks, CONFIG["window_size"], CONFIG["window_overlap"])
        print(f"Generated {len(windows)} windows")

    if args.dry_run:
        print("\n=== DRY RUN MODE ===")
        for i, w in enumerate(windows[:10]):
            print(f"  - {w['window_id']}: {len(w['chunks'])} chunks ({w['chunk_ids'][0]}..{w['chunk_ids'][-1]})")
        if len(windows) > 10:
            print(f"  ... and {len(windows) - 10} more windows")
        return 0

    # Build resume command and save to checkpoint
    resume_args = [sys.executable, str(Path(__file__).resolve()),
                   "--provider", args.provider, "--model", model_name]
    if args.base_path:
        resume_args += ["--base-path", str(args.base_path)]
    if args.indices_file:
        resume_args += ["--indices-file", str(args.indices_file)]
    if args.batch_size != CONFIG["requests_per_batch"]:
        resume_args += ["--batch-size", str(args.batch_size)]
    if args.no_batch:
        resume_args.append("--no-batch")
    resume_args.append("--resume")
    resume_cmd = shlex.join(resume_args)

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize client
    client = LLMClient(args.provider, args.model)

    # Process based on provider capabilities
    if client.supports_batch and not args.no_batch:
        try:
            process_batches(
                client=client,
                windows=windows,
                system_prompt=system_prompt,
                checkpoint_path=checkpoint_path,
                output_raw_path=output_raw_path,
                errors_dir=errors_dir,
                requests_per_batch=args.batch_size,
                max_tokens=CONFIG["max_tokens"],
                poll_interval=CONFIG["poll_interval"],
                poll_timeout=CONFIG["poll_timeout"],
                resume=args.resume,
                resume_cmd=resume_cmd,
            )
        except BatchNotSupportedError as e:
            print(f"\nBatch API not available ({e})")
            print("Falling back to sequential processing...\n")
            process_sequential(
                client=client,
                windows=windows,
                system_prompt=system_prompt,
                checkpoint_path=checkpoint_path,
                output_raw_path=output_raw_path,
                errors_dir=errors_dir,
                max_tokens=CONFIG["max_tokens"],
                resume=args.resume,
                resume_cmd=resume_cmd,
            )
    else:
        process_sequential(
            client=client,
            windows=windows,
            system_prompt=system_prompt,
            checkpoint_path=checkpoint_path,
            output_raw_path=output_raw_path,
            errors_dir=errors_dir,
            max_tokens=CONFIG["max_tokens"],
            resume=args.resume,
            resume_cmd=resume_cmd,
        )

    # Final deduplication
    if output_raw_path.exists():
        print("\nRunning final deduplication...")
        raw_records = load_chunks(output_raw_path)
        semantic_chunks, micro_units = deduplicate_outputs(raw_records)
        write_final_outputs(output_path, micro_units_path, semantic_chunks, micro_units)
        print(f"Wrote {len(semantic_chunks)} semantic chunks to {output_path}")
        print(f"Wrote {len(micro_units)} micro units to {micro_units_path}")
        print("\nDone!")
    else:
        print("\nNo raw output file found - no processing completed successfully.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
