"""
fine_tune_leya.py
Фаза 5 — Скрипт для дообучения (LoRA) модели Лея на твоих диалогах

Как использовать:
1. Собирай свои диалоги с Леей (можно логировать в файл)
2. Запускай этот скрипт периодически
3. Модель становится более "твоей"

Требования:
pip install peft transformers datasets accelerate bitsandbytes

Пример запуска:
python scripts/fine_tune_leya.py --data_path my_dialogs.jsonl --output_dir ./leya_finetuned
"""

import argparse
import json
import os
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
import torch

def load_dialogs(file_path: str):
    """Загружает диалоги в формате JSONL (каждая строка — один диалог)."""
    conversations = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            # Ожидаемый формат: {"user": "...", "assistant": "..."}
            if "user" in data and "assistant" in data:
                conversations.append({
                    "text": f"Пользователь: {data['user']}\nЛея: {data['assistant']}"
                })
    return Dataset.from_list(conversations)

def fine_tune(model_name: str, data_path: str, output_dir: str, epochs: int = 3):
    print(f"Загрузка модели {model_name}...")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        load_in_4bit=True,
        torch_dtype=torch.float16,
        device_map="auto"
    )

    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM"
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    dataset = load_dialogs(data_path)

    def tokenize_function(examples):
        return tokenizer(examples["text"], truncation=True, max_length=1024, padding="max_length")

    tokenized_dataset = dataset.map(tokenize_function, batched=True, remove_columns=["text"])

    training_args = TrainingArguments(
        output_dir=output_dir,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        num_train_epochs=epochs,
        learning_rate=2e-4,
        fp16=True,
        logging_steps=10,
        save_strategy="epoch",
        report_to="none"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_dataset,
    )

    print("Начинаем fine-tuning...")
    trainer.train()

    print(f"Сохраняем модель в {output_dir}...")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print("Готово! Модель дообучена под тебя.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_name", type=str, default="Qwen/Qwen2.5-14B-Instruct")
    parser.add_argument("--data_path", type=str, required=True, help="Путь к JSONL файлу с диалогами")
    parser.add_argument("--output_dir", type=str, default="./leya_finetuned")
    parser.add_argument("--epochs", type=int, default=3)

    args = parser.parse_args()

    fine_tune(
        model_name=args.model_name,
        data_path=args.data_path,
        output_dir=args.output_dir,
        epochs=args.epochs
    )