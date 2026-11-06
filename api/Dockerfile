FROM python:3.14-alpine3.23@sha256:0cdfadc8472de8f74a5d3c6e5e49d1b3f059f36cd01a0a0d4015cb1cb89df436
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apk upgrade --no-cache && apk add --no-cache ca-certificates \
 && addgroup -g 5000 mailapi \
 && adduser -D -H -h /nonexistent -u 5000 -G mailapi -s /sbin/nologin mailapi \
 && mkdir -p /opt/oo-api && apk info -v > /opt/oo-api/packages.txt
COPY api/requirements.lock /opt/oo-api/requirements.lock
RUN python3 -m pip install --no-cache-dir --require-hashes -r /opt/oo-api/requirements.lock \
 && python3 -m pip check \
 && python3 -m pip uninstall -y pip
COPY api/ /opt/oo-api/
RUN chmod -R a+rX /opt/oo-api && mkdir /dkim && chown 5000:5000 /dkim
WORKDIR /opt/oo-api
USER 5000:5000
EXPOSE 8081
CMD ["python3", "server.py"]
