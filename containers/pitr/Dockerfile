FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY pitr.py /app/

RUN chmod +x /app/pitr.py

ENTRYPOINT ["python3", "/app/pitr.py"]
