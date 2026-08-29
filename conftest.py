import sys
from pathlib import Path

# Добавляем backend в PYTHONPATH чтобы работали импорты вида `from backend.src...`
sys.path.insert(0, str(Path(__file__).parent / "backend"))
