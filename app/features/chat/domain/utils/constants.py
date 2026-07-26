# Ширина колонок таблицы из оригинального файла (в EMU).
# Используются при создании нового файла; при дописывании в существующий
# таблица уже имеет правильные размеры.
import re

_COLUMN_WIDTHS_EMU = (535305, 1947545, 6991350)
_FONT_NAME = "Times New Roman"
_FONT_SIZE_PT = 14.0  # 177800 EMU == 14pt

QUESTION_PATTERN = re.compile(r"^\s*(?:вопрос\s*)?(\d{1,4})\s*[.)\-:]\s*(.+)?$", re.IGNORECASE)
ANSWER_MARKER_PATTERN = re.compile(r"^\s*ответ\s*[:\-]?\s*(.*)$", re.IGNORECASE)
