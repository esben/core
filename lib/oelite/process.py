import sys
import os
import multiprocessing
import signal
import time
import json
import oelite.util
from oelite.log import log


class NamedPipe(object):

    def __init__(self, path):
        if os.path.exists(path):
            os.remove(path)
        dir = os.path.dirname(path)
        if not os.path.exists(dir):
            os.makedirs(dir)
        os.mkfifo(path)
        self.path = path

    def __del__(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def open(self, mode):
        assert mode in ('r', 'w')
        return open(self.path, mode, 1)


class LogFeedback(object):

    LEVELS = ('debug', 'info', 'warning', 'error', 'critical')

    def __init__(self, level, msg):
        if not level in self.LEVELS:
            raise ValueError(level)
        self.level = level
        if not msg.has_key('val'):
            raise ValueError(msg)
        self.msg = msg['val']
        # FIXME: get time part of log feedback messages


class ProgressFeedback(object):

    def __init__(self, percent):
        if percent < 0 or percent > 100:
            raise ValueError(percent)
        self.percent = percent


class FeedbackSender(object):

    def __init__(self, fifo):
        assert isinstance(fifo, NamedPipe)
        self.fifo = fifo.open('w')

    def send(self, msg_type, feedback):
        feedback['msg'] = msg_type
        feedback['time'] = time.time()
        self.fifo.write(json.dumps(feedback) + '\n')

    def progress(self, val):
        self.send('progress', {'val': val})

    def debug(self, val):
        self.send('debug', {'val': val})

    def info(self, val):
        self.send('info', {'val': val})

    def warning(self, val):
        self.send('warning', {'val': val})

    def error(self, val):
        self.send('error', {'val': val})

    def critical(self, val):
        self.send('critical', {'val': val})


class FeedbackReceiver(object):

    _msg_types = ('progress', 'debug', 'info', 'warning', 'error', 'critical')

    def __init__(self, fifo):
        self.fifo = fifo.open('r')

    def fileno(self):
        return self.fifo.fileno()

    def __iter__(self):
        return self

    def next(self):
        while True:
            line = self.fifo.readline()
            if line == '': # EOF
                raise StopIteration()
            line = line.strip()
            if not line:
                continue # skip blank lines
            msg = self.parse_message(line)
            if msg:
                return msg

    def receive(self):
        try:
            return self.next()
        except StopIteration:
            return

    def parse_message(self, line):
        try:
            feedback = json.loads(line)
        except ValueError as e:
            log.warning("invalid process feedback message: %r", feedback)
            return
        if isinstance(feedback, basestring):
            return LogFeedback('debug', feedback)
        elif isinstance(feedback, int):
            try:
                return ProgressFeedback(feedback)
            except ValueError:
                log.warning("invalid progress integer message: %d", feedback)
                return
        if isinstance(feedback, dict):
            if not (feedback.has_key('msg') and
                    feedback['msg'] in self._msg_types):
                log.warning("invalid process feedback message: %r", feedback)
                return
            msg_type = feedback.pop('msg')
            if msg_type == 'progress':
                if not feedback.has_key('val'):
                    log.warning("invalid process feedback message: %r",
                                feedback)
                    return
                return ProgressFeedback(feedback['val'])
            if msg_type in LogFeedback.LEVELS:
                if not feedback.has_key('val'):
                    log.warning("invalid process feedback message: %r",
                                feedback)
                    return
                return LogFeedback(msg_type, feedback)


class PythonProcess(multiprocessing.Process):

    def __init__(self, stdout=None, ipc=None, setsid=False, **kwargs):
        self.stdout = stdout
        if ipc:
            self.ipc = NamedPipe(ipc)
        else:
            self.ipc = None
        self.setsid = setsid
        super(PythonProcess, self).__init__(**kwargs)
        return

    def start(self):
        """Start child process"""
        super(PythonProcess, self).start()
        if self.stdout:
            oelite.util.touch(self.stdout, makedirs=True)
            stdout = open(self.stdout, 'r')
        else:
            stdout = None
        if self.ipc:
            feedback = FeedbackReceiver(self.ipc)
        else:
            feedback = None
        return (stdout, feedback)

    def run(self):
        """The method run in the child process"""
        #log.debug("PythonProcess started pid=%d", os.getpid())
        if self.setsid:
            os.setsid()
        if self.stdout:
            stdout = open(self.stdout, 'w', 1)
        else:
            stdout = open(os.devnull, 'w')
        os.dup2(stdout.fileno(), sys.stdout.fileno())
        os.dup2(stdout.fileno(), sys.stderr.fileno())
        if self.ipc:
            self.feedback = FeedbackSender(self.ipc)
        return super(PythonProcess, self).run()


class TaskProcess(PythonProcess):

    def __init__(self, task, logfile=None):
        if not logfile:
            logfile = os.path.join(task.meta().get('T'), task.name + '.log')
        super(TaskProcess, self).__init__(stdout=logfile, target=task.run)
        return

    def stop(self, timeout=1):
        if not self.is_alive():
            return
        os.kill(self.pid, signal.SIGINT)
        try:
            # wait 1 second for task process to shut down
            self.join(timeout)
        except:
            self.terminate()
        return


# and add a class for doing something like pool, but with support for progress
# information, fx. when parsing recipes, a count of how many recipes have been
# parsed of how many is printed.  constructor should set number of workers.
# the pool.map like method should take the target function, a list/iterator,
# and optionally fixed args and kwargs to give to all function calls.


# new class
#
# for non-task multiprocessing, like oe-lite parsing and other python
# functions.
#
# the function being "run" must be allowed to print out on stdout and stderr,
# and this should go to an output file, which the parent process then can
# either ignore and remove when done, print out to stdout (probably not a good
# idea if running in parallel), or ignore while running, and in case the
# function fails, print out all or part of the output file, and leave entire
# output file for debugging purpose.
#
# a different communication "stream" must be supported from child process to
# parent.  This should be a simple JSON/text syntax, so that the same
# mechanism can be used independent of the language used in the child.  The
# stream should support:
#  + (debug)/info/warning/error/fatal messages from child to parent, although
#  + progress information
#
# {"log": "debug", "message": "foobar", "time": "1380991668.191745"}
# {"log": "info", "message": "foobar", "time": "1380991668.191745"}
# {"log": "warning", "message": "foobar", "time": "1380991668.191745"}
# {"log": "error", "message": "foobar", "time": "1380991668.191745"}
# {"log": "critical", "message": "foobar", "time": "1380991668.191745"}
# {"progress": "0%"}
# {"progress": "2/7"}
# {"progress": "0.13"}
#
# should we use multiprocessing.Pool also?  does reuse of pool worker
# processes risk contaminating the result?  ie, is the namespace for a worker
# process pristine for each job?
#
#
