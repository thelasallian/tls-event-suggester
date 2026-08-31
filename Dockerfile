FROM python:3.12-slim
WORKDIR /srv
RUN pip install --no-cache-dir fastapi uvicorn jinja2 python-multipart
COPY app ./app
COPY app/seed.json ./app/seed.json
WORKDIR /srv/app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
