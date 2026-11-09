FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY . .
RUN DEBUG=1 python manage.py collectstatic --noinput
RUN useradd --create-home dqtech && chown -R dqtech:dqtech /app
USER dqtech
CMD ["gunicorn","config.wsgi:application","--bind","0.0.0.0:8000","--workers","3"]
