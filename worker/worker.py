#!/usr/bin/python
from __future__ import print_function, absolute_import

import json
import multiprocessing
import os
import platform
import signal
import sys
import time
import traceback
import uuid
from ConfigParser import SafeConfigParser
from optparse import OptionParser

from os.path import dirname as dn, abspath as ab
project_path = dn(dn(ab(__file__)))
sys.path.insert(0, project_path)

from worker import requests
from worker.games import run_games
from worker.updater import update

FAILURE_SLEEP_DURATION = 1800
NO_VERSION_SLEEP_DURATION = 5
CONNECTION_ERROR_SLEEP_DURATION = 10
NO_TASKS_SLEEP_DURATION = 10

WORKER_VERSION = 59
ALIVE = True

HTTP_TIMEOUT = 5.0
CONFIG_FILE_NAME = 'fishtest.cfg'

CONFIG_FILE_DEFAULTS = [
    ('login', 'username', ''),
    ('login', 'password', ''),
    ('parameters', 'host', 'tests.stockfishchess.org'),
    ('parameters', 'port', '80'),
    ('parameters', 'concurrency', '3')
]

TESTS_HOST = 'tests.stockfishchess.org'


def setup_config_file(config_file):
    """
    Read config file, fill default settings if they are not present
    :param config_file: configuration file name
    :return: SafeConfigParser object that read
    """
    config = SafeConfigParser()
    config.read(config_file)
    defaults_added = False

    for section, key, value in CONFIG_FILE_DEFAULTS:
        if not config.has_section(section):
            config.add_section(section)
            defaults_added = True
        if not config.has_option(section, key):
            config.set(section, key, value)
            defaults_added = True

    if defaults_added:
        with open(config_file, 'w') as f:
            config.write(f)

    return config


def on_sigint(signal, frame):
    """
    Sigint handler
    """
    global ALIVE
    ALIVE = False
    raise Exception('Terminated by signal')


def worker(worker_info, password, remote):
    global ALIVE

    payload = {
        'worker_info': worker_info,
        'password': password,
    }

    try:
        req = requests.post('%s/api/request_version' % remote, data=json.dumps(payload),
                            headers={'Content-type': 'application/json'}, timeout=HTTP_TIMEOUT)
        req = json.loads(req.text)

        if 'version' not in req:
            print('Incorrect username/password')
            time.sleep(NO_VERSION_SLEEP_DURATION)
            sys.exit(1)

        if req['version'] > WORKER_VERSION:
            print('Updating worker version to %d' % (req['version']))
            update()

        req = requests.post('%s/api/request_task' % remote, data=json.dumps(payload),
                            headers={'Content-type': 'application/json'}, timeout=HTTP_TIMEOUT)
        req = json.loads(req.text)
    except:
        sys.stderr.write('Exception accessing host:\n')
        traceback.print_exc()
        time.sleep(CONNECTION_ERROR_SLEEP_DURATION)
        return

    if 'error' in req:
        raise Exception('Error from remote: %s' % (req['error']))

    # No tasks ready for us yet, just wait...
    if 'task_waiting' in req:
        print('No tasks available at this time, waiting...')
        time.sleep(NO_TASKS_SLEEP_DURATION)
        return

    success = True
    run, task_id = req['run'], req['task_id']

    try:
        run_games(worker_info, password, remote, run, task_id)
    except:
        sys.stderr.write('\nException running games:\n')
        traceback.print_exc()
        success = False
    finally:
        payload = {
            'username': worker_info['username'],
            'password': password,
            'run_id': str(run['_id']),
            'task_id': task_id
        }
        try:
            requests.post('%s/api/failed_task' % remote, data=json.dumps(payload),
                          headers={'Content-type': 'application/json'}, timeout=HTTP_TIMEOUT)
        except:
            pass
        sys.stderr.write('Task exited\n')

    return success


def main():
    signal.signal(signal.SIGINT, on_sigint)
    signal.signal(signal.SIGTERM, on_sigint)

    config = setup_config_file(CONFIG_FILE_NAME)
    parser = OptionParser()
    parser.add_option('-n', '--host', dest='host', default=config.get('parameters', 'host'))
    parser.add_option('-p', '--port', dest='port', default=config.get('parameters', 'port'))
    parser.add_option('-c', '--concurrency', type=int, dest='concurrency',
                      default=config.get('parameters', 'concurrency'))
    (options, args) = parser.parse_args()

    if len(args) != 2:
        # Try to read parameters from the the config file
        username = config.get('login', 'username')
        password = config.get('login', 'password', raw=True)
        if username and password:
            args.extend([username, password])
        else:
            sys.stderr.write('%s [username] [password]\n' % (sys.argv[0]))
            sys.exit(1)

    # Write command line parameters to the config file
    config.set('login', 'username', args[0])
    config.set('login', 'password', args[1])
    config.set('parameters', 'host', options.host)
    config.set('parameters', 'port', options.port)
    config.set('parameters', 'concurrency', str(options.concurrency))
    with open(CONFIG_FILE_NAME, 'w') as f:
        config.write(f)

    remote = 'http://%s:%s' % (options.host, options.port)
    print('Worker version %d connecting to %s' % (WORKER_VERSION, remote))

    try:
        cpu_count = min(options.concurrency, multiprocessing.cpu_count() - 1)
    except:
        cpu_count = options.concurrency

    if cpu_count <= 0:
        sys.stderr.write('Not enough CPUs to run fishtest (it requires at least two)\n')
        sys.exit(1)

    uname = platform.uname()
    worker_info = {
        'uname': '%s %s' % (uname[0], uname[2]),
        'architecture': platform.architecture(),
        'concurrency': cpu_count,
        'username': args[0],
        'version': WORKER_VERSION,
        'unique_key': str(uuid.uuid4()),
    }

    success = True
    global ALIVE
    while ALIVE:
        if not success:
            time.sleep(FAILURE_SLEEP_DURATION)
        success = worker(worker_info, args[1], remote)


if __name__ == '__main__':
    main()
