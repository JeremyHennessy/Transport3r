FROM python:3.12-slim

WORKDIR /app
COPY scripts/requirements-nationwide.txt /app/scripts/requirements-nationwide.txt
RUN pip install --no-cache-dir -r /app/scripts/requirements-nationwide.txt
COPY scripts /app/scripts
COPY data /app/data
RUN useradd --create-home --uid 10001 transport3r
ENV PYTHONPATH=/app/scripts EVIDENCE_HOST=0.0.0.0 PORT=8787
EXPOSE 8787
USER transport3r
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD ["python", "-c", "import json,os,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8787')+'/healthz',timeout=3))['status']=='ok'"]
CMD ["python", "/app/scripts/evidence_api.py"]
