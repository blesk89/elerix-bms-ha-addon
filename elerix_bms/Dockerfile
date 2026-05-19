FROM python:3.11-alpine

RUN pip install --no-cache-dir pyserial

COPY run.py /run.py
COPY elerix_bms.py /elerix_bms.py

CMD ["python3", "/run.py"]
