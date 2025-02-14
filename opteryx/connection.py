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

"""
This module provides a PEP-249 familiar interface for interacting with mabel data
stores, it is not compliant with the standard:
https://www.python.org/dev/peps/pep-0249/
"""
import datetime
import time
import typing
from dataclasses import dataclass
from dataclasses import field
from uuid import uuid4

import pyarrow
from orso import DataFrame
from orso import converters
from orso.tools import random_int

from opteryx import config
from opteryx import utils
from opteryx.exceptions import CursorInvalidStateError
from opteryx.exceptions import MissingSqlStatement
from opteryx.exceptions import PermissionsError
from opteryx.managers.kvstores import BaseKeyValueStore
from opteryx.shared import QueryStatistics
from opteryx.shared.rolling_log import RollingLog
from opteryx.shared.variables import SystemVariables
from opteryx.shared.variables import VariableOwner

CURSOR_NOT_RUN: str = "Cursor must be in an executed state"
PROFILE_LOCATION = config.PROFILE_LOCATION
ENGINE_VERSION = config.ENGINE_VERSION

HistoryItem = typing.Tuple[str, bool, datetime.datetime]

rolling_log = None
if PROFILE_LOCATION:
    rolling_log = RollingLog(PROFILE_LOCATION + ".log", 50, 1024 * 1024)


@dataclass
class ConnectionContext:
    connection_id: int = field(init=False)
    connected_at: datetime.datetime = field(init=False)
    user: str = None
    schema: str = None
    variables: dict = field(init=False)
    history: typing.List[HistoryItem] = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "connection_id", random_int())
        object.__setattr__(self, "connected_at", datetime.datetime.utcnow())
        object.__setattr__(self, "history", [])
        object.__setattr__(self, "variables", SystemVariables.copy(VariableOwner.USER))


class Connection:
    """
    A connection
    """

    def __init__(
        self,
        *,
        cache: typing.Union[BaseKeyValueStore, None] = None,
        permissions: typing.Union[typing.Iterable, None] = None,
        **kwargs,
    ):
        """
        A virtual connection to the Opteryx query engine.
        """
        self.cache = cache
        self._kwargs = kwargs

        self.context = ConnectionContext()

        # check the permissions we've been given are valid permissions
        from opteryx.constants.permissions import PERMISSIONS

        if permissions is None:
            permissions = PERMISSIONS
        permissions = set(permissions)
        if permissions.intersection(PERMISSIONS) == set():
            raise PermissionsError("No valid permissions presented.")
        if not permissions.issubset(PERMISSIONS):
            raise PermissionsError(
                f"Invalid permissions presented - {PERMISSIONS.difference(permissions)}"
            )
        self.permissions = permissions

    def cursor(self):
        """return a cursor object"""
        return Cursor(self)

    def close(self):
        """exists for interface compatibility only"""

    def commit(self):
        """exists for interface compatibility only"""

    def rollback(self):
        """exists for interface compatibility only"""
        # return AttributeError as per https://peps.python.org/pep-0249/#id48
        raise AttributeError("Opteryx does not support transactions.")


class Cursor(DataFrame):
    def __init__(self, connection):
        self.arraysize = 1
        self._connection = connection
        self._query = None
        self._query_planner = None
        self._collected_stats = None
        self._plan = None
        self._qid = str(uuid4())
        self._statistics = QueryStatistics(self._qid)
        DataFrame.__init__(self, rows=[], schema=[])

    @property
    def query(self):
        return self._query

    @property
    def id(self):
        """The unique internal reference for this query"""
        return self._qid

    def _inner_execute(self, operation, params=None):
        from opteryx.components import query_planner

        if not operation:
            raise MissingSqlStatement("SQL statement not found")

        if self._query is not None:
            raise CursorInvalidStateError("Cursor can only be executed once")

        self._connection.context.history.append((operation, True, datetime.datetime.utcnow()))
        plans = query_planner(operation=operation, parameters=params, connection=self._connection)

        if rolling_log:
            rolling_log.append(operation)

        results = None
        for self._plan in plans:
            results = self._plan.execute()

        if results is not None:
            # we can't update tuples directly
            self._connection.context.history[-1] = tuple(
                True if i == 1 else value
                for i, value in enumerate(self._connection.context.history[-1])
            )
            return results

    def execute(self, operation, params=None):
        results = self._inner_execute(operation, params)
        if results is not None:
            self._rows, self._schema = converters.from_arrow(results)
            self._cursor = iter(self._rows)

    def execute_to_arrow(self, operation, params=None, limit=None):
        results = self._inner_execute(operation, params)
        if results is not None:
            if limit is not None:
                results = utils.arrow.limit_records(results, limit)
        return pyarrow.concat_tables(results, promote=True)

    @property
    def stats(self):
        """execution statistics"""
        if self._statistics.end_time == 0:  # pragma: no cover
            self._statistics.end_time = time.time_ns()
        return self._statistics.as_dict()

    @property
    def messages(self) -> list:
        """list of run-time warnings"""
        return self._statistics.messages

    def close(self):
        """close the connection"""
        self._connection.close()
