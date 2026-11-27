ARG PROMETHEUS_VERSION=latest
FROM prom/prometheus:${PROMETHEUS_VERSION} AS upstream
FROM python:3.13-slim
COPY --from=upstream /bin/prometheus /bin/promtool /usr/local/bin/
RUN mkdir /config /prometheus && chown 65534:65534 /config /prometheus
COPY manager.py default.yml /app/
USER 65534:65534
EXPOSE 9090 9091
ENTRYPOINT ["python","/app/manager.py"]
