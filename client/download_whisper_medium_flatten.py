from huggingface_hub import snapshot_download
import os

# 1. Define where the REAL files will go (flat folder)
# We avoid the .cache/huggingface structure entirely to stop the symlink logic
model_destination = "/root/.cache/huggingface/whisper_medium_flat"

print("Starting flat download (no symlinks)...")
snapshot_download(
    repo_id="Systran/faster-whisper-medium",
    local_dir=model_destination,
    local_dir_use_symlinks=False,  # <--- THIS IS THE MAGIC KEY
    revision="main"
)
print(f"Model downloaded to {model_destination}")