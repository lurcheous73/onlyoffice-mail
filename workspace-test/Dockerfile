# Legacy client fixture only; requires a separate disposable KVM guest.
FROM onlyoffice/communityserver:12.8.0.1971@sha256:d98c14df79b35117e94d7511f2cc519555259e03da7fd9453e8b46d72d80a746
COPY workspace-test/ /opt/ws-test/
RUN python3 /opt/ws-test/patch_bootstrap.py
ENTRYPOINT ["bash", "/opt/ws-test/entrypoint.sh"]
