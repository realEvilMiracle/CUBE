FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /bot

RUN pip install --no-cache-dir --upgrade pip

COPY bot/requirements.txt /bot/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ /bot

CMD ["python", "main.py"]

