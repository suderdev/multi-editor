import os
import pathlib
import threading
import time

import docker
import flask
import flask_sockets
import requests
import websocket

from flask_dance import consumer

from raven.contrib import flask as sentry_flask

APP_PATH = os.environ.get('APP_PATH',
                          os.path.dirname(os.path.abspath(__file__)))

SENTRY_DSN = os.environ.get('SENTRY_DSN', None)


app = flask.Flask(__name__)

if SENTRY_DSN:
    sentry = sentry_flask.Sentry(app, dsn=SENTRY_DSN)

app.config['PREFERRED_URL_SCHEME'] = 'https'

app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'secret')
app.config['FLASK_ENV'] = os.environ.get('FLASK_ENV', 'production')

router = flask.Blueprint('router', __name__)
ws = flask.Blueprint('ws', __name__)
oauth = consumer.OAuth2ConsumerBlueprint(
    "oauth", __name__,
    client_id=os.environ.get('OAUTH_CLIENT_ID'),
    client_secret=os.environ.get('OAUTH_CLIENT_SECRET'),
    base_url=os.environ.get('OAUTH_BASE_URL'),
    token_url=os.environ.get('OAUTH_TOKEN_URL'),
    authorization_url=os.environ.get('OAUTH_AUTHORIZATION_URL'),
)


@ws.route('/services')
def services(ext):
    assert flask.session['user_login']
    assert flask.session['user_id']
    assert flask.session['ip']

    user_login = flask.session['user_login']
    ip = flask.session['ip']
    app.logger.info('Forwarder for %s to %s' %
                    (str(user_login), str(ip)))

    int = websocket.WebSocketApp('ws://%s:3000/services' % ip)

    def on_message(ws, message):
        app.logger.debug('Forward from service %s: %s' %
                         (str(ip), str(message)))
        ext.send(message)

    def forward():
        while not ext.closed:
            message = ext.receive()
            app.logger.debug('Forward to service %s: %s' %
                             (str(ip), str(message)))
            int.send(message)

    forwarder = threading.Thread(target=forward)

    def on_open(ws):
        forwarder.start()
        app.logger.info('Started forwarding data '
                        'for user %s for service %s' %
                        (str(user_login), str(ip)))

    def on_close(ws):
        ext.disconnect()
        app.logger.info('Stopped forwarding data '
                        'for user %s for service %s' %
                        (str(user_login), str(ip)))

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
    if not oauth.authorized:
        app.logger.info('Not authorized, redirecting')
        return flask.redirect(flask.url_for('oauth.login'))

    resp = oauth.session.get(os.environ.get('OAUTH_USER_URL'))

    if not resp.ok:
        app.logger.warn('Response about user incorrect, redirecting')
        return flask.redirect(flask.url_for('oauth.login'))

    github_user_id = resp.json()['id']
    github_user_login = resp.json()['login']
    flask.session['user_id'] = github_user_id
    flask.session['user_login'] = github_user_login

    app.logger.debug('User %s authorized via GitHub' % str(github_user_login))

    user_path = '%s/users/user_%s_%s' % (APP_PATH,
                                         str(github_user_id),
                                         str(github_user_login))
    pathlib.Path(user_path).touch()

    containers = get_containers(github_user_id)
    if not containers:
        app.logger.info('No editor for user %s, starting new' %
                        str(github_user_login))
        space_dir = ('%s/spaces/user_%s' %
                     (APP_PATH, github_user_id))
        try:
            os.mkdir(space_dir)
        except FileExistsError:
            app.logger.warning('Space dir for user %s exists, reusing it' %
                               str(github_user_login))
        client.containers.run(image='editor:latest',
                              name='user_%s' % str(github_user_id),
                              auto_remove=True,
                              detach=True,
                              ports={'3000/tcp': None},
                              network='bridge',
                              volumes={space_dir: {'bind': '/home/project',
                                                   'mode': 'rw'}},
                              labels={'user': str(github_user_id)})
        time.sleep(3)
        containers = get_containers(github_user_id)

    port = get_port(containers[0])
    ip = get_ip(containers[0])
    flask.session['port'] = port
    flask.session['ip'] = ip
    app.logger.debug('Proxying for user %s URL /%s to %s' %
                     (str(github_user_login), str(url), str(ip)))

    req = requests.get('http://%s:3000/%s' % (ip, url))
    return flask.Response(req, content_type=req.headers['content-type'])


app.register_blueprint(oauth, url_prefix='/login')
app.register_blueprint(router)

sockets = flask_sockets.Sockets(app)
sockets.register_blueprint(ws)
