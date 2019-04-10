FROM python:3

ADD requirements.txt /app/

WORKDIR /app

RUN pip install -r requirements.txt

ADD Procfile /app/
ADD main.py /app/
ADD .env /app/
ADD internal.key /app/
ADD internal.crt /app/

EXPOSE 5000:5000

CMD ["honcho", "start"]