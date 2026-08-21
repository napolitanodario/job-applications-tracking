#!/usr/bin/env python3
"""
Colab-side inference script.

Loads Qwen2.5-7B-Instruct in 4-bit, caches weights on Google Drive, and prints
a JSON array of extraction objects to stdout. Designed to run only on Colab.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HF_HOME = "/content/drive/MyDrive/jobtrack/huggingface"
MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
MAX_NEW_TOKENS = 512

SYSTEM_PROMPT = """You extract job-application facts from a single email.
Return ONLY one JSON object (no markdown fences, no commentary).
Use only information present in the email. Never invent fields.
If a value is not stated, use null.
Do not use placeholders such as N/A, unknown, or not specified.

JSON schema:
{
  "relevant": boolean,
  "company": string|null,
  "position_title": string|null,
  "is_internship": boolean|null,
  "location": string|null,
  "contract_type": string|null,
  "applied_on": string|null,
  "event_type": "confirmation"|"rejection"|"invitation"|"other_job"|null,
  "event_on": string|null,
  "next_steps": string|null,
  "notes": string|null
}

Rules:
- relevant is true only if the email is about a job application, interview, assessment, offer, or rejection.
- confirmation: application received / submitted acknowledgment.
- rejection: candidate not moving forward.
- invitation: interview, assessment, take-home, or other next hiring step. Put the named steps in next_steps.
- other_job: recruiting-related but not the above.
- Dates must be ISO YYYY-MM-DD when a clear date is present; otherwise null.
- notes: short factual extras from the email only; null if none.
"""


def ensure_packages() -> None:
    pkgs = ["transformers", "accelerate", "bitsandbytes", "sentencepiece"]
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", *pkgs],
        stdout=subprocess.DEVNULL,
    )


def load_model():
    os.environ["HF_HOME"] = HF_HOME
    Path(HF_HOME).mkdir(parents=True, exist_ok=True)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    quant = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=quant,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()
    return tokenizer, model


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"No JSON object in model output: {text[:500]}")
    return json.loads(text[start : end + 1])


def infer_one(tokenizer, model, message: dict[str, str]) -> dict[str, Any]:
    import torch

    user = (
        f"From: {message.get('from_header', '')}\n"
        f"Subject: {message.get('subject', '')}\n"
        f"Date: {message.get('date_header', '')}\n\n"
        f"{message.get('body', '')}"
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            temperature=None,
            top_p=None,
        )
    generated = output_ids[0][inputs["input_ids"].shape[-1] :]
    text = tokenizer.decode(generated, skip_special_tokens=True)
    try:
        data = extract_json_object(text)
    except Exception:
        data = {
            "relevant": False,
            "company": None,
            "position_title": None,
            "is_internship": None,
            "location": None,
            "contract_type": None,
            "applied_on": None,
            "event_type": None,
            "event_on": None,
            "next_steps": None,
            "notes": None,
        }
    data["message_id"] = message.get("message_id", "")
    data["thread_id"] = message.get("thread_id", "")
    return data


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: infer_colab.py /content/batch.json", file=sys.stderr)
        return 1

    batch_path = Path(sys.argv[1])
    payload = json.loads(batch_path.read_text(encoding="utf-8"))
    messages = payload.get("messages") or []

    ensure_packages()
    tokenizer, model = load_model()

    results = [infer_one(tokenizer, model, msg) for msg in messages]
    # Single-line JSON array for the worker parser.
    print(json.dumps(results, ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
