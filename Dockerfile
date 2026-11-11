FROM python:3.13-alpine
WORKDIR /app
COPY pyproject.toml README.md ./
COPY watchseerr ./watchseerr
RUN pip install --no-cache-dir . && adduser -D -u 1000 watchseerr && mkdir /data && chown watchseerr /data
USER watchseerr
ENV WATCHSEERR_CONFIG=/config/watchseerr.toml STATE_DIRECTORY=/data
VOLUME /data
ENTRYPOINT ["watchseerr"]
CMD ["--daemon"]
