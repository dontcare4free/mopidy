from __future__ import unicode_literals

import logging
import signal
import sys
import thread
import threading
import traceback

from pykka import ActorDeadError
from pykka.registry import ActorRegistry

from mopidy import exceptions


logger = logging.getLogger('mopidy.utils.process')


SIGNALS = dict(
    (k, v) for v, k in signal.__dict__.iteritems()
    if v.startswith('SIG') and not v.startswith('SIG_'))


def exit_process():
    logger.debug('Interrupting main...')
    thread.interrupt_main()
    logger.debug('Interrupted main')


def exit_handler(signum, frame):
    """A :mod:`signal` handler which will exit the program on signal."""
    logger.info('Got %s signal', SIGNALS[signum])
    exit_process()


def stop_actors_by_class(klass):
    actors = ActorRegistry.get_by_class(klass)
    logger.debug('Stopping %d instance(s) of %s', len(actors), klass.__name__)
    for actor in actors:
        actor.stop()


def stop_remaining_actors():
    num_actors = len(ActorRegistry.get_all())
    while num_actors:
        logger.error(
            'There are actor threads still running, this is probably a bug')
        logger.debug(
            'Seeing %d actor and %d non-actor thread(s): %s',
            num_actors, threading.active_count() - num_actors,
            ', '.join([t.name for t in threading.enumerate()]))
        logger.debug('Stopping %d actor(s)...', num_actors)
        ActorRegistry.stop_all()
        num_actors = len(ActorRegistry.get_all())
    logger.debug('All actors stopped.')


class BaseThread(threading.Thread):
    def __init__(self):
        super(BaseThread, self).__init__()
        # No thread should block process from exiting
        self.daemon = True

    def run(self):
        logger.debug('%s: Starting thread', self.name)
        try:
            self.run_inside_try()
        except KeyboardInterrupt:
            logger.info('Interrupted by user')
        except exceptions.SettingsError as e:
            logger.error(e.message)
        except ImportError as e:
            logger.error(e)
        except ActorDeadError as e:
            logger.warning(e)
        except Exception as e:
            logger.exception(e)
        logger.debug('%s: Exiting thread', self.name)

    def run_inside_try(self):
        raise NotImplementedError


class DebugThread(threading.Thread):
    daemon = True
    name = 'DebugThread'

    event = threading.Event()

    def handler(self, signum, frame):
        logger.info('Got %s signal', SIGNALS[signum])
        self.event.set()

    def run(self):
        while True:
            self.event.wait()
            threads = dict((t.ident, t.name) for t in threading.enumerate())

            for ident, frame in sys._current_frames().items():
                if self.ident != ident:
                    stack = ''.join(traceback.format_stack(frame))
                    logger.debug(
                        'Current state of %s (%s):\n%s',
                        threads[ident], ident, stack)
                del frame

            self.event.clear()
