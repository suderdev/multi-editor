import os
import threading
import time

import docker
import flask
import flask_sockets
import requests
import websocket

from flask_dance.contrib.github import github
from flask_dance.contrib.github import make_github_blueprint

from raven.contrib import flask as sentry_flask

SENTRY_DSN = os.environ.get('SENTRY_DSN', None)


app = flask.Flask(__name__)

if SENTRY_DSN:
    sentry = sentry_flask.Sentry(app, dsn=SENTRY_DSN)

app.config['PREFERRED_URL_SCHEME'] = 'https'

app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'secret')
app.config['FLASK_ENV'] = os.environ.get('FLASK_ENV', 'production')

app.config['GITHUB_OAUTH_CLIENT_ID'] = \
    os.environ.get('GITHUB_OAUTH_CLIENT_ID')
app.config['GITHUB_OAUTH_CLIENT_SECRET'] = \
    os.environ.get('GITHUB_OAUTH_CLIENT_SECRET')

router = flask.Blueprint('router', __name__)
ws = flask.Blueprint('ws', __name__)
oauth = make_github_blueprint()


@ws.route('/services')
def services(ext):
    assert flask.session['user_id']
    assert flask.session['port']
    assert flask.session['ip']

    port = flask.session['port']
    ip = flask.session['ip']
    app.logger.info('Forwarding port %s:%s' % (ip, str(port)))

    int = websocket.WebSocketApp('ws://%s:3000/services' % ip)

    def on_message(ws, message):
        app.logger.debug('Forward to client: %s' % str(message))
        ext.send(message)

    def forward():
        while not ext.closed:
            message = ext.receive()
            app.logger.debug('Forward to service: %s' % str(message))
            int.send(message)

    forwarder = threading.Thread(target=forward)

    def on_open(ws):
        forwarder.start()
        app.logger.info('Started forwarding data')

    def on_close(ws):
        ext.disconnect()
        app.logger.info('Stopped forwarding data')

    int.on_message = on_message
    int.on_open = on_open
    int.on_close = on_close

    int.run_forever()


client = docker.from_env()


def get_containers(user):
    return client.containers.list(filters={'label': 'user=%s' % user})


def get_port(container):
    ports = container.attrs['NetworkSettings']['Ports']
    return ports['3000/tcp'][0]['HostPort']


def get_ip(container):
    ips = container.attrs['NetworkSettings']['Networks']
    return ips['bridge']['IPAddress']


@router.route('/')
@router.route('/<path:url>')
def index(url=''):
    if not github.authorized:
        app.logger.info('Not authorized, redirect to GitHub')
        return flask.redirect(flask.url_for('github.login'))

    resp = github.get('/user')
    if not resp.ok:
        app.logger.warn('Response about user not correct, redirect to GitHub')
        return flask.redirect(flask.url_for('github.login'))

    github_user_id = resp.json()['id']
    flask.session['user_id'] = github_user_id

    app.logger.info('User %s authorized via GitHub' % str(github_user_id))

    containers = get_containers(github_user_id)
    if not containers:
        app.logger.info('No editor for user %s, starting new' % github_user_id)
        client.containers.run(image='theiaide/theia-python:latest',
                              auto_remove=True,
                              detach=True,
                              ports={'3000/tcp': None},
                              network='bridge',
                              labels={'user': str(github_user_id)})
        time.sleep(3)
        containers = get_containers(github_user_id)

    port = get_port(containers[0])
    ip = get_ip(containers[0])
    flask.session['port'] = port
    flask.session['ip'] = ip
    app.logger.info('Proxying port %s:%s' % (ip, str(port)))

    req = requests.get('http://%s:3000/%s' % (ip, url))
    return flask.Response(req, content_type=req.headers['content-type'])


app.register_blueprint(oauth, url_prefix='/login')
app.register_blueprint(router)

sockets = flask_sockets.Sockets(app)
sockets.register_blueprint(ws)
