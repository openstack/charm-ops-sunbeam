# Copyright 2021, Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import subprocess
import textwrap
import time
import typing
import weakref

from ops import model
from ops import pebble
import uuid

import logging


logger = logging.getLogger(__name__)

# Unknown return code is a large negative number outside the usual range of a
# process exit code
RETURN_CODE_UNKNOWN = -1000


class ContainerProcess(object):
    """A process that has finished running.

    This is returned by an invocation to run()

    :param container: the container the process was running in
    :type container: model.Container
    :param process_name: the name of the process the container is running as
    :type process_name: str
    :param tmp_dir: the dir containing the location of process files
    :type tmp_dir: str
    """
    def __init__(self, container: model.Container, process_name: str,
                 tmp_dir: str):
        self.container = weakref.proxy(container)
        self.process_name = process_name
        self._returncode = RETURN_CODE_UNKNOWN
        self.tmp_dir = tmp_dir
        self.stdout_file = f'{tmp_dir}/{process_name}.stdout'
        self.stderr_file = f'{tmp_dir}/{process_name}.stderr'
        self._env = dict()
        self.env_file = f'{tmp_dir}/{process_name}.env'
        self.rc_file = f'{tmp_dir}/{process_name}.rc'
        self._cleaned = False

    @property
    def stdout(self) -> typing.Union[typing.BinaryIO, typing.TextIO]:
        return self.container.pull(f'{self.stdout_file}')

    @property
    def stderr(self) -> typing.Union[typing.BinaryIO, typing.TextIO]:
        return self.container.pull(f'{self.stderr_file}')

    @property
    def env(self) -> typing.Dict[str, str]:
        if self._env:
            return self._env

        with self.container.pull(f'{self.env_file}') as f:
            for env_vars in f.read().split(b'\n'):
                key_values = env_vars.split(b'=', 1)
                self._env[key_values[0]] = key_values[1]

        return self._env

    @property
    def returncode(self) -> int:
        if self._returncode == RETURN_CODE_UNKNOWN:
            self._returncode = self._get_returncode()
        return self._returncode

    def _get_returncode(self):
        """Reads the contents of the returncode file"""
        try:
            with self.container.pull(f'{self.rc_file}') as text:
                return int(text.read())
        except pebble.PathError:
            # If the rc file doesn't exist within the container, then the
            # process is either running or failed without capturing output
            return RETURN_CODE_UNKNOWN

    @property
    def completed(self) -> bool:
        return self._returncode != RETURN_CODE_UNKNOWN

    def check_returncode(self):
        """Raise CalledProcessError if the exit code is non-zero."""
        if self.returncode:
            stdout = None
            stderr = None
            try:
                stdout = self.stdout.read()
            except pebble.PathError:
                pass
            try:
                stderr = self.stderr.read()
            except pebble.PathError:
                pass
            raise CalledProcessError(self.returncode, self.process_name,
                                     stdout, stderr)

    def wait(self, timeout: int = 30) -> None:
        """Waits for the process to complete.

        Waits for the process to complete. If the process has not completed
        within the timeout specified, this method will raise a TimeoutExpired
        exception.

        :param timeout: the number of seconds to wait before timing out
        :type timeout: int
        """
        timeout_at = time.time() + timeout
        while not self.completed and time.time() < timeout_at:
            try:
                self._returncode = self._get_returncode()
                if self.completed:
                    return
                else:
                    time.sleep(0.2)
            except pebble.PathError:
                # This happens while the process is still running
                # Sleep a moment and try again
                time.sleep(0.2)

        raise TimeoutExpired(self.process_name, timeout)

    def cleanup(self) -> None:
        """Clean up process files left on the container.

        Attempts to cleanup the process artifacts left on the container. This
        will remove the directory containing the stdout, stderr, rc and env
        files generated.

        :raises pebble.PathError: when the path has already been cleand up.
        """
        if self._cleaned:
            return

        self.container.remove_path(f'{self.tmp_dir}', recursive=True)

    def __del__(self):
        """On destruction of this process, we'll attempt to clean up left over
        process files.
        """
        try:
            self.cleanup()
        except pebble.PathError:
            pass


class ContainerProcessError(Exception):
    """Base class for exceptions raised within this module."""
    pass


class CalledProcessError(ContainerProcessError):
    """Raised when an error occurs running a process in a container and
    the check=True has been passed to raise an error on failure.

    :param returncode: the exit code from the program
    :type returncode: int
    :param cmd: the command that was run
    :type cmd: str or list
    :param stdout: the output of the command on standard out
    :type stdout: str
    :param stderr: the output of the command on standard err
    :type stderr: str
    """
    def __init__(self, returncode: int, cmd: typing.Union[str, list],
                 stdout: str = None, stderr: str = None):
        self.returncode = returncode
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr


class TimeoutExpired(ContainerProcessError):
    """This exception is raised when the timeout expires while waiting for a
    container process.

    :param cmd: the command that was run
    :type cmd: list
    :param timeout: the configured timeout for the command
    :type timeout: int
    """
    def __init__(self, cmd: typing.Union[str, list], timeout: int):
        self.cmd = cmd
        self.timeout = timeout

    def __str__(self):
        return f"Command '{self.cmd}' timed out after {self.timeout} seconds"


def run(container: model.Container, args: typing.List[str],
        timeout: int = 30, check: bool = False,
        env: dict = None, service_name: str = None) -> ContainerProcess:
    """Run command with arguments in the specified container.

    Run a command in the specified container and returns a
    subprocess.CompletedProcess instance containing the command which
    was run (args), returncode, and stdout and stderr. When the check
    option is True and the process exits with a non-zero exit code, a
    CalledProcessError will be raised containing the cmd, returncode,
    stdout and stderr.

    :param container: the container to run the command in
    :type container: model.Container
    :param args: the command to run in the container
    :type args: str or list
    :param timeout: the timeout of the process in seconds
    :type timeout: int
    :param check: when True, raise an exception on a non-zero exit code
    :type check: bool
    :param env: environment variables to pass to the process
    :type env: dict
    :param service_name: name of the service
    :type service_name: str
    :returns: CompletedProcess the completed process
    :rtype: ContainerProcess
    """
    if not container:
        raise ValueError('container cannot be None')
    if not isinstance(container, model.Container):
        raise ValueError('container must be of type ops.model.Container, '
                         f'not of type {type(container)}')

    if isinstance(args, str):
        if service_name is None:
            service_name = args.split(' ')[0]
            service_name = service_name.split('/')[-1]
        cmdline = args
    elif isinstance(args, list):
        if service_name is None:
            service_name = args[0].split('/')[-1]
        cmdline = subprocess.list2cmdline(args)
    else:
        raise ValueError('args are expected to be a str or a list of str.'
                         f' Provided {type(args)}')

    tmp_dir = f'/tmp/{service_name}-{str(uuid.uuid4()).split("-")[0]}'
    process = ContainerProcess(container, service_name, tmp_dir)

    command = f"""\
    #!/bin/bash
    mkdir -p {tmp_dir}
    echo $(env) > {process.env_file}
    {cmdline} 2> {process.stderr_file} 1> {process.stdout_file}
    rc=$?
    echo $rc > {process.rc_file}
    exit $rc
    """
    command = textwrap.dedent(command)

    container.push(path=f'/tmp/{service_name}.sh', source=command,
                   encoding='utf-8', permissions=0o755)

    logger.debug(f'Adding layer for {service_name} to run command '
                 f'{cmdline}')
    container.add_layer('process_layer', {
        'summary': 'container process runner',
        'description': 'layer for running single-shot commands (kinda)',
        'services': {
            service_name: {
                'override': 'replace',
                'summary': cmdline,
                'command': f'/tmp/{service_name}.sh',
                'startup': 'disabled',
                'environment': env or {},
            }
        }
    }, combine=True)

    timeout_at = time.time() + timeout
    try:
        # Start the service which will run the command.
        logger.debug(f'Starting {service_name} via pebble')

        # TODO(wolsen) this is quite naughty, but the container object
        #  doesn't provide us access to the pebble layer to specify
        #  timeouts and such. Some commands may need a longer time to
        #  start, and as such I'm using the private internal reference
        #  in order to be able to specify the timeout itself.
        container._pebble.start_services([service_name],  # noqa
                                         timeout=float(timeout))
    except pebble.ChangeError:
        # Check to see if the command has timed out and if so, raise
        # the TimeoutExpired.
        if time.time() >= timeout_at:
            logger.error(f'Command {cmdline} could not start out after '
                         f'{timeout} seconds in container '
                         f'{container.name}')
            raise TimeoutExpired(args, timeout)

        # Note, this could be expected.
        logger.exception(f'Error running {service_name}')

    logger.debug('Waiting for process completion...')
    process.wait(timeout)

    # It appears that pebble services are still active after the command
    # has finished. Feels like a bug, but let's stop it.
    try:
        service = container.get_service(service_name)
        if service.is_running():
            container.stop(service_name)
    except pebble.ChangeError as e:
        # Eat the change error that might occur. This was a best effort
        # attempt to ensure the process is stopped
        logger.exception(f'Failed to stop service {service_name}', e)

    if check:
        process.check_returncode()
    return process


def call(container: model.Container, args: typing.Union[str, list],
         env: dict = None, timeout: int = 30) -> int:
    """Runs a command in the container.

    The command will run until the process completes (either normally or
    abnormally) or until the timeout expires.

    :param container: the container to run the command in
    :type container: model.Container
    :param args: arguments to pass to the commandline
    :type args: str or list of strings
    :param env: environment variables for the process
    :type env: dictionary of environment variables
    :param timeout: number of seconds the command should complete in before
                    timing out
    :type timeout: int
    :returns: the exit code of the process
    :rtype: int
    """
    return run(container, args, env=env, timeout=timeout).returncode


def check_call(container: model.Container, args: typing.Union[str, list],
               env: dict = None, timeout: int = 30,
               service_name: str = None) -> None:
    run(container, args, env=env, check=True, timeout=timeout,
        service_name=service_name)


def check_output(container: model.Container, args: typing.Union[str, list],
                 env: dict = None, timeout: int = 30,
                 service_name: str = None) -> str:
    process = run(container, args, env=env, check=True, timeout=timeout,
                  service_name=service_name)
    with process.stdout as stdout:
        return stdout.read()
