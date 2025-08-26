FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p reviews # ensure reviews folder exists

EXPOSE 5000

#CMD ["python", "lithub.py"]
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "lithub:app"]
