FROM python:3.11-slim

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip -i ${PIP_INDEX_URL} --trusted-host ${PIP_TRUSTED_HOST} \
    && pip install -r /app/requirements.txt -i ${PIP_INDEX_URL} --trusted-host ${PIP_TRUSTED_HOST}

COPY . /app

EXPOSE 8000

CMD ["python", "start_server.py", "--config", "config.ini", "--host", "0.0.0.0", "--port", "8000"]
