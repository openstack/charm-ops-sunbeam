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

import logging
from contextlib import contextmanager

from ops.model import BlockedStatus

logger = logging.getLogger(__name__)


class GuardException(Exception):
    pass


class BlockedException(Exception):
    pass


@contextmanager
def guard(charm: 'CharmBase',
          section: str,
          handle_exception: bool = True,
          log_traceback: bool = True,
          **__):
    """Context manager to handle errors and bailing out of an event/hook.
    The nature of Juju is that all the information may not be available to run
    a set of actions.  This context manager allows a section of code to be
    'guarded' so that it can be bailed at any time.

    It also handles errors which can be interpreted as a Block rather than the
    charm going into error.

    :param charm: the charm class (so that unit status can be set)
    :param section: the name of the section (for debugging/info purposes)
    :handle_exception: whether to handle the exception to a BlockedStatus()
    :log_traceback: whether to log the traceback for debugging purposes.
    :raises: Exception if handle_exception is False
    """
    logger.info("Entering guarded section: '%s'", section)
    try:
        yield
        logging.info("Completed guarded section fully: '%s'", section)
    except GuardException as e:
        logger.info("Guarded Section: Early exit from '%s' due to '%s'.",
                    section, str(e))
    except BlockedException as e:
        logger.warning(
            "Charm is blocked in section '%s' due to '%s'", section, str(e))
        charm.unit.status = BlockedStatus(e.msg)
    except Exception as e:
        # something else went wrong
        if handle_exception:
            logging.error("Exception raised in secion '%s': %s",
                          section, str(e))
            if log_traceback:
                import traceback
                logging.error(traceback.format_exc())
                charm.unit.status = BlockedStatus(
                    "Error in charm (see logs): {}".format(str(e)))
            return
        raise
