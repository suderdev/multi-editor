FROM python:3.8-slim

ADD requirements.txt /app/

WORKDIR /app

RUN pip install -r requirements.txt

ADD Procfile /app/
ADD main.py /app/

EXPOSE 5000:5000

CMD ["honcho", "start"]
