FROM heuesta-app:compatible-6ed8255
WORKDIR /shared-mail
COPY --chown=1000:1000 ops/shared-mail/ /shared-mail/
ENV SHARED_MAIL_CONFIG=/run/secrets/shared-mail.json
ENV HOME=/tmp
ENTRYPOINT []
CMD ["gunicorn", "service:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--worker-class", "gthread", "--threads", "4", "--timeout", "45", "--access-logfile", "/dev/null", "--error-logfile", "-"]
