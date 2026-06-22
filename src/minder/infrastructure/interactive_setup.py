"""Interactive setup to choose LLM models at boot up."""

import json
import logging
import sys
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from minder.config import Settings

logger = logging.getLogger(__name__)

def _is_size_under_10b(tags: list[str]) -> bool:
    for t in tags:
        if t.startswith("size:"):
            size_str = t.split(":")[1].lower()
            if size_str.endswith("b"):
                try:
                    size_val = float(size_str[:-1])
                    if size_val < 10.0:
                        return True
                except ValueError:
                    pass
    return False

def run_interactive_model_setup(config: "Settings") -> None:
    minder_dir = Path.home() / ".minder"
    config_file = minder_dir / "model_config.json"
    if config_file.exists():
        return

    if not sys.stdin.isatty():
        # Headless mode fallback
        logger.info("Headless mode detected. Setting default LLM model to google/gemma-4-E2B-it-qat-q4_0-gguf")
        minder_dir.mkdir(parents=True, exist_ok=True)
        config_data = {
            "llama_cpp_model_repo": "google/gemma-4-E2B-it-qat-q4_0-gguf",
            "llama_cpp_model_file": "gemma-4-E2B_q4_0-it.gguf"
        }
        with open(config_file, "w", encoding="utf-8") as file_out:
            json.dump(config_data, file_out, indent=2)
        config.llm.llama_cpp_model_repo = config_data["llama_cpp_model_repo"]
        config.llm.llama_cpp_model_file = config_data["llama_cpp_model_file"]
        return

    print("=== MINDER LLM MODEL SETUP ===")
    print("Fetching recommended GGUF models under 10B from HuggingFace...")

    try:
        url = "https://huggingface.co/api/models?search=gguf&sort=downloads&limit=100"
        req = urllib.request.Request(url, headers={"User-Agent": "Minder-Setup"})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"Failed to fetch models from HuggingFace: {e}")
        return

    recommended_models = []
    for m in data:
        tags = m.get("tags", [])
        if _is_size_under_10b(tags):
            recommended_models.append(m)
        if len(recommended_models) >= 15:
            break

    if not recommended_models:
        print("No suitable models found. Using default.")
        return

    print("\nSelect a model to download and use:")
    for i, model in enumerate(recommended_models, start=1):
        print(f"{i}. {model['id']}")

    while True:
        try:
            choice = input(f"Enter a number (1-{len(recommended_models)}) or 0 to skip: ").strip()
            if not choice:
                continue
            choice_idx = int(choice)
            if choice_idx == 0:
                print("Skipping model setup.")
                return
            if 1 <= choice_idx <= len(recommended_models):
                selected_model = recommended_models[choice_idx - 1]
                break
            else:
                print("Invalid number.")
        except ValueError:
            print("Please enter a valid number.")

    repo_id = selected_model["id"]
    print(f"\nFetching available GGUF files for {repo_id}...")
    
    try:
        tree_url = f"https://huggingface.co/api/models/{repo_id}/tree/main"
        req2 = urllib.request.Request(tree_url, headers={"User-Agent": "Minder-Setup"})
        with urllib.request.urlopen(req2) as response2:
            files_data = json.loads(response2.read().decode("utf-8"))
    except Exception as e:
        print(f"Failed to fetch files: {e}")
        return

    gguf_files = [f["path"] for f in files_data if f.get("type") == "file" and f.get("path", "").endswith(".gguf")]
    
    if not gguf_files:
        print(f"No .gguf files found in {repo_id}. Using default.")
        return

    print("\nSelect a quantization file:")
    for i, f in enumerate(gguf_files, start=1):
        print(f"{i}. {f}")

    while True:
        try:
            choice2 = input(f"Enter a number (1-{len(gguf_files)}) or 0 to skip: ").strip()
            if not choice2:
                continue
            choice_idx2 = int(choice2)
            if choice_idx2 == 0:
                print("Skipping file selection.")
                return
            if 1 <= choice_idx2 <= len(gguf_files):
                selected_file = gguf_files[choice_idx2 - 1]
                break
            else:
                print("Invalid number.")
        except ValueError:
            print("Please enter a valid number.")

    print(f"\nConfiguring Minder to use: {repo_id} ({selected_file})")
    
    minder_dir.mkdir(parents=True, exist_ok=True)
    config_data = {
        "llama_cpp_model_repo": repo_id,
        "llama_cpp_model_file": selected_file
    }
    with open(config_file, "w", encoding="utf-8") as file_out:
        json.dump(config_data, file_out, indent=2)
    
    config.llm.llama_cpp_model_repo = repo_id
    config.llm.llama_cpp_model_file = selected_file
    print("Configuration saved successfully!\n")
