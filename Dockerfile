FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY mvp/requirements.txt /app/mvp/requirements.txt
RUN pip install --no-cache-dir -r /app/mvp/requirements.txt \
    && groupadd --gid 10001 vafa \
    && useradd --uid 10001 --gid vafa --no-create-home vafa

COPY mvp/api /app/mvp/api
COPY mvp/engine /app/mvp/engine
COPY mvp/data /app/mvp/data
COPY landing/index.html /app/landing/index.html

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/', timeout=3); assert json.load(response)['status'] == 'ok'"

CMD ["python", "-m", "uvicorn", "mvp.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
