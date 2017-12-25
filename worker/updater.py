from __future__ import absolute_import

import os
import shutil
import sys

from distutils.dir_util import copy_tree
from zipfile import ZipFile

import requests

WORKER_URL = 'https://github.com/glinscott/fishtest/archive/master.zip'


def restart(worker_dir):
    """
    Restart the worker, using the same arguments
    """
    args = sys.argv[:]
    args.insert(0, sys.executable)
    if sys.platform == 'win32':
        args = ['"%s"' % arg for arg in args]

    os.chdir(worker_dir)
    os.execv(sys.executable, args)  # This does not return !


def update():
    worker_dir = os.path.dirname(os.path.realpath(__file__))
    fishtest_dir = os.path.dirname(worker_dir)
    update_dir = os.path.join(fishtest_dir, 'update')

    if not os.path.exists(update_dir):
        os.makedirs(update_dir)

    worker_zip = os.path.join(update_dir, 'wk.zip')
    resp = requests.get(WORKER_URL, stream=True)
    with open(worker_zip, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=1024):
            f.write(chunk)

    zip_file = ZipFile(worker_zip)
    zip_file.extractall(update_dir)
    zip_file.close()

    prefix = os.path.commonprefix([n.filename for n in zip_file.infolist()])
    new_worker_dir = os.path.join(prefix, 'worker')
    old_worker_dir = os.path.join(fishtest_dir, 'old_worker')

    shutil.move(worker_dir, old_worker_dir)
    shutil.move(new_worker_dir, worker_dir)

    shutil.rmtree(old_worker_dir)
    shutil.rmtree(update_dir)

    restart(worker_dir)
