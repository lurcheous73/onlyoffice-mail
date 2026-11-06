FROM oo-mailserver-api:dev
COPY --chown=5000:5000 migration/ /opt/oo-api/migration/
ENTRYPOINT ["python3", "/opt/oo-api/migration/backend_records.py"]
