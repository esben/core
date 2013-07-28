import sys
import os
import multiprocessing
import signal


class NamedPipe(object):

    def __init__(self, task, name):
        tmpdir = task.meta().get('T')
        path = os.path.join(tmpdir, name)
        if os.path.exists(path):
            os.remove(path)
        dir = os.path.dirname(path)
        if not os.path.exists(dir):
            os.makedirs(dir)
        os.mkfifo(path)
        self.path = path

    def open(self, mode):
        assert mode in ('r', 'w')
        return open(self.path, mode)


class TaskProcess(multiprocessing.Process):

    def __init__(self, task):
        self.task = task
        self.stdin = NamedPipe(task, 'stdin')
        self.stdout = NamedPipe(task, 'stdout')
        self.stderr = NamedPipe(task, 'stderr')
        super(TaskProcess, self).__init__()
        return

    def start(self):
        super(TaskProcess, self).start()
        stdin = self.stdin.open('w')
        stdout = self.stdout.open('r')
        stderr = self.stderr.open('r')
        return stdin, stdout, stderr

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

    def run(self):
        os.setsid()
        print "TaskProcess.run task=%s pid=%d"%(self.task, os.getpid())
        stdin = self.stdin.open('r')
        os.dup2(stdin.fileno(), sys.stdin.fileno())
        stdout = self.stdout.open('w')
        os.dup2(stdout.fileno(), sys.stdout.fileno())
        stderr = self.stderr.open('w')
        os.dup2(stderr.fileno(), sys.stderr.fileno())
        if self.task.run():
            return 0
        else:
            return 1
