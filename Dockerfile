# Backend image for docker-compose.local.yml (CPU only; the model runs in the separate ollama service).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir waitress==3.0.2 cryptography sqlite-vec==0.1.9 tzdata
# runtime/ must be 0700: apex.kernel.memory.Ledger refuses a group/world-accessible data folder.
RUN useradd -m apex \
 && install -d -o apex -g apex -m 0700 /etc/apex /app/runtime
WORKDIR /app
COPY --chown=apex:apex core ./core
COPY --chown=apex:apex scripts ./scripts
USER apex
EXPOSE 8000
CMD ["python", "-B", "scripts/serve_container.py"]
