FROM debian:13-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pymysql python3-requests python3-argon2 python3-flask python3-cryptography python3-dkim openssl ca-certificates && apt-get clean
COPY api/ /opt/tests/api/
COPY mail/auth.py /opt/tests/auth.py
COPY api/common.py /opt/tests/common.py
COPY tests/ /opt/tests/
COPY docs/oo-sql-contract.json /opt/tests/oo-sql-contract.json
WORKDIR /opt/tests
CMD ["python3", "integration.py"]
