#!/usr/bin/python
# -*- coding: utf-8 -*-

# thumbor imaging service
# https://github.com/thumbor/thumbor/wiki

# Licensed under the MIT license:
# http://www.opensource.org/licenses/mit-license
# Copyright (c) 2011 globo.com thumbor@googlegroups.com

import os
from os.path import dirname, exists, abspath, getmtime
from uuid import uuid4
import hashlib
from shutil import move
from datetime import datetime

import pytz
import tornado.gen

from thumbor.lifecycle import Events


def plug_into_lifecycle():
    Events.subscribe(Events.Imaging.after_parsing_arguments, on_after_parsing_argument)
    Events.subscribe(Events.Imaging.after_finish_request, on_after_finish_request)

    Events.subscribe(Events.Imaging.before_loading_source_image, on_before_loading_source_image)
    Events.subscribe(Events.Imaging.after_loading_source_image, on_after_loading_source_image)


def path_on_filesystem(path):
    digest = hashlib.sha1(path.encode('utf-8')).hexdigest()
    return "%s/%s/%s" % (
        '/tmp/thumbor/storage',
        # self.context.config.FILE_STORAGE_ROOT_PATH.rstrip('/'),
        digest[:2],
        digest[2:]
    )


def ensure_dir(path):
    if not exists(path):
        try:
            os.makedirs(path)
        except OSError as err:
            # FILE ALREADY EXISTS = 17
            if err.errno != 17:
                raise


def validate_path(path):
    return abspath(path).startswith('/tmp/thumbor/storage')


def is_expired(path):
    # expire_in_seconds = self.context.config.get('RESULT_STORAGE_EXPIRATION_SECONDS', None)
    expire_in_seconds = 60

    if expire_in_seconds is None or expire_in_seconds == 0:
        return False

    timediff = datetime.now() - datetime.fromtimestamp(getmtime(path))
    return timediff.seconds > expire_in_seconds


@tornado.gen.coroutine
def on_after_parsing_argument(sender, request, details):
    request_parameters = details.request_parameters

    should_store = details.config.RESULT_STORAGE_STORES_UNSAFE or not details.request_parameters.unsafe
    if not should_store:
        return

    file_abspath = path_on_filesystem(request_parameters.url)
    if not validate_path(file_abspath):
        return

    if not exists(file_abspath) or is_expired(file_abspath):
        return

    with open(file_abspath, 'rb') as f:
        details.transformed_image = f.read()

    details.headers['Last-Modified'] = datetime.fromtimestamp(getmtime(file_abspath)).replace(tzinfo=pytz.utc)


@tornado.gen.coroutine
def on_before_loading_source_image(sender, request, details):
    request_parameters = details.request_parameters
    file_abspath = path_on_filesystem(request_parameters.image_url)
    if not exists(file_abspath):
        return

    with open(file_abspath, 'rb') as f:
        details.source_image = f.read()


@tornado.gen.coroutine
def on_after_loading_source_image(sender, request, details):
    request_parameters = details.request_parameters
    if details.source_image is None:
        return

    file_abspath = path_on_filesystem(request_parameters.image_url)
    temp_abspath = "%s.%s" % (file_abspath, str(uuid4()).replace('-', ''))
    file_dir_abspath = dirname(file_abspath)

    ensure_dir(file_dir_abspath)

    with open(temp_abspath, 'wb') as _file:
        _file.write(details.source_image)

    move(temp_abspath, file_abspath)

    return


@tornado.gen.coroutine
def on_after_finish_request(sender, request, details):
    request_parameters = details.request_parameters
    if details.status_code != 200 or details.transformed_image is None:
        return

    should_store = details.config.RESULT_STORAGE_STORES_UNSAFE or not details.request_parameters.unsafe
    if not should_store:
        return

    file_abspath = path_on_filesystem(request_parameters.url)
    temp_abspath = "%s.%s" % (file_abspath, str(uuid4()).replace('-', ''))
    file_dir_abspath = dirname(file_abspath)

    ensure_dir(file_dir_abspath)

    with open(temp_abspath, 'wb') as _file:
        _file.write(details.transformed_image)

    move(temp_abspath, file_abspath)

    return