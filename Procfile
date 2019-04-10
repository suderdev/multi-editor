web: gunicorn --worker-class flask_sockets.worker --workers 2 --certfile=internal.crt --keyfile=internal.key --log-file=- main:app
