FROM python:3.11-slim

WORKDIR /app

# Install system deps for psycopg binary
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

# Copy project files and install
COPY pyproject.toml .
COPY src/ src/

# Optional: golden eval tasks
COPY tests/golden/ tests/golden/

RUN pip install --no-cache-dir .

ENV PYTHONUTF8=1
EXPOSE 8050

CMD ["python", "-m", "uvicorn", "src.serve:app", "--host", "0.0.0.0", "--port", "8050"]
