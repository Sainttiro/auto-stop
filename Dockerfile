# Multi-stage build для оптимизации размера образа

# Stage 1: Builder
FROM python:3.12-slim as builder

WORKDIR /app

# Установка системных зависимостей для сборки
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Создание пользователя для запуска приложения (безопасность)
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data /app/logs && \
    chown -R appuser:appuser /app

# Копирование установленных пакетов из builder
COPY --from=builder /root/.local /home/appuser/.local

# Копирование исходного кода
COPY --chown=appuser:appuser . .

# Установка переменных окружения
ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Переключение на непривилегированного пользователя
USER appuser

# Healthcheck для мониторинга состояния контейнера
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Точка входа
CMD ["python3", "-m", "src.main"]
