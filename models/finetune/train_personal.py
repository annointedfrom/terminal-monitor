"""
Personal ops-brain fine-tune.
Trains on ALL pairs in training_seed.jsonl (your own data, not sanitized).
Output: models/checkpoints/personal/
"""

import json
import pathlib
import sys

import torch
from datasets import Dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
)
from trl import SFTTrainer

BASE_MODEL = "meta-llama/Llama-3.2-3B-Instruct"
SEED_PATH = pathlib.Path(__file__).parent.parent / "training_seed.jsonl"
OUT_DIR = pathlib.Path(__file__).parent.parent / "checkpoints" / "personal"


def load_pairs(path: pathlib.Path) -> list[dict]:
    pairs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def format_prompt(pair: dict) -> str:
    return (
        f"<|system|>You are an ops assistant monitoring a local machine.</s>\n"
        f"<|user|>{pair['instruction']}</s>\n"
        f"<|assistant|>{pair['output']}</s>"
    )


def main() -> None:
    if not SEED_PATH.exists():
        print(f"Seed file not found: {SEED_PATH}", file=sys.stderr)
        sys.exit(1)

    pairs = load_pairs(SEED_PATH)
    print(f"Loaded {len(pairs)} training pairs")

    dataset = Dataset.from_list([{"text": format_prompt(p)} for p in pairs])

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    lora_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(OUT_DIR),
        num_train_epochs=5,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        bf16=True,
        logging_steps=5,
        save_strategy="epoch",
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        args=training_args,
        dataset_text_field="text",
        max_seq_length=512,
    )

    trainer.train()
    trainer.save_model(str(OUT_DIR / "final"))
    tokenizer.save_pretrained(str(OUT_DIR / "final"))
    print(f"Saved to {OUT_DIR / 'final'}")


if __name__ == "__main__":
    main()
