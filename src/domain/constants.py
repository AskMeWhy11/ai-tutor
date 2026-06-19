"""Доменные константы.

Здесь живут значения, которые на стадии Среза 1 захардкожены, а в Срезе 2
будут вычитываться из кейсов/конфигурации.
"""

from __future__ import annotations

# Верхняя граница вопросов в TRAINING_QUIZ.
# В TRAINING_QUIZ через LLM решение о завершении принимает QuizDirector
# (см. ctx.quiz_target_questions). Константа служит safety-net на случай,
# если LLM «забудет» эмитить done.
TRAINING_QUIZ_QUESTIONS: int = 99
