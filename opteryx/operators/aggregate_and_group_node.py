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
Grouping Node

This is a SQL Query Execution Plan Node.

This is the grouping node, it is always followed by the aggregation node, but
the aggregation node doesn't need the grouping node.


"""
import time
from typing import Iterable

import numpy
import pyarrow
from orso.types import OrsoTypes

from opteryx.exceptions import SqlError
from opteryx.managers.expression import NodeType
from opteryx.managers.expression import evaluate_and_append
from opteryx.managers.expression import get_all_nodes_of_type
from opteryx.models import QueryProperties
from opteryx.operators import BasePlanNode
from opteryx.operators.aggregate_node import build_aggregations
from opteryx.operators.aggregate_node import extract_evaluations
from opteryx.operators.aggregate_node import project


class AggregateAndGroupNode(BasePlanNode):
    def __init__(self, properties: QueryProperties, **config):
        super().__init__(properties=properties)
        self.groups = list(config["groups"])
        self.aggregates = list(config["aggregates"])
        projection = list(config["projection"])

        # we're going to preload some of the evaluation

        # Replace offset based GROUP BYs with their column
        self.groups = [
            group
            if not (group.node_type == NodeType.LITERAL and group.type == OrsoTypes.INTEGER)
            else projection[group.value - 1]
            for group in self.groups
        ]

        # get all the columns anywhere in the groups or aggregates
        all_identifiers = [
            node.schema_column.identity
            for node in get_all_nodes_of_type(
                self.groups + self.aggregates, select_nodes=(NodeType.IDENTIFIER,)
            )
        ]
        self.all_identifiers = list(dict.fromkeys(all_identifiers))

        # Get any functions we need to execute before aggregating
        self.evaluatable_nodes = extract_evaluations(self.aggregates)

        # get the aggregated groupings and functions
        self.group_by_columns = list({node.schema_column.identity for node in self.groups})
        self.column_map, self.aggregate_functions = build_aggregations(self.aggregates)

    @property
    def config(self):  # pragma: no cover
        return str(self._aggregates)

    @property
    def greedy(self):  # pragma: no cover
        return True

    @property
    def name(self):  # pragma: no cover
        return "Group"

    def execute(self) -> Iterable:
        if len(self._producers) != 1:  # pragma: no cover
            raise SqlError(f"{self.name} on expects a single producer")

        morsels = self._producers[0]  # type:ignore

        # merge all the morsels together into one table, selecting only the columns
        # we're pretty sure we're going to use - this will fail for datasets
        # larger than memory
        table = pyarrow.concat_tables(
            project(morsels.execute(), self.all_identifiers), promote=True
        )

        # Allow grouping by functions by evaluating them first
        start_time = time.time_ns()
        table = evaluate_and_append(self.evaluatable_nodes, table)
        table = evaluate_and_append(self.groups, table)

        # Add a "*" column, this is an int because when a bool it miscounts
        if "*" not in table.column_names:
            table = table.append_column(
                "*", [numpy.full(shape=table.num_rows, fill_value=1, dtype=numpy.int8)]
            )
        self.statistics.time_evaluating += time.time_ns() - start_time

        start_time = time.time_ns()

        # do the group by and aggregates
        table = table.combine_chunks()
        groups = table.group_by(self.group_by_columns)
        groups = groups.aggregate(self.aggregate_functions)

        # project to the desired column names from the pyarrow names
        groups = groups.select(list(self.column_map.values()) + self.group_by_columns)
        groups = groups.rename_columns(list(self.column_map.keys()) + self.group_by_columns)

        self.statistics.time_fgrouping += time.time_ns() - start_time

        yield groups
