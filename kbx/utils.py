import hashlib
import json
from pathlib import Path

HASH_FILE = 'file_hashes.json'


def calculate_file_hash(path: Path) -> str:
    """Calculate the SHA-256 hash of the file."""
    hasher = hashlib.sha256()
    with open(path, 'rb') as file:
        buffer = file.read()
        hasher.update(buffer)
    return hasher.hexdigest()


def load_hashes() -> dict:
    """Load the hashes from the hash file."""
    if Path(HASH_FILE).exists():
        with open(HASH_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_hashes(hashes: dict) -> None:
    """Save the hashes to the hash file."""
    with open(HASH_FILE, 'w') as f:
        json.dump(hashes, f, indent=4)


def has_file_changed(path: Path) -> bool:
    """Check if the file content has changed."""
    stored_hashes = load_hashes()
    current_hash = calculate_file_hash(path)
    if stored_hashes.get(str(path)) != current_hash:
        stored_hashes[str(path)] = current_hash
        save_hashes(stored_hashes)
        return True
    return False
