FROM python:3.12-alpine3.22

ARG APP_VERSION=HEAD
LABEL org.opencontainers.image.version=$APP_VERSION

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check -r /tmp/requirements.txt

COPY . .

RUN addgroup -S app && adduser -S app -G app && chown -R app:app /app

COPY scripts/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 7999

USER app

ENTRYPOINT ["/entrypoint.sh"]
