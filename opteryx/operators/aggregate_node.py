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

This performs aggregations, both of grouped and non-grouped data.

This is a greedy operator - it consumes all the data before responding.

This is built around the pyarrow table grouping functionality.
"""
import time
from typing import Iterable

import numpy
import pyarrow

from opteryx.exceptions import SqlError
from opteryx.exceptions import UnsupportedSyntaxError
from opteryx.managers.expression import NodeType
from opteryx.managers.expression import evaluate_and_append
from opteryx.managers.expression import format_expression
from opteryx.managers.expression import get_all_nodes_of_type
from opteryx.models import QueryProperties
from opteryx.operators import BasePlanNode

COUNT_STAR: str = "COUNT(*)"

# use the aggregators from pyarrow
AGGREGATORS = {
    "ALL": "all",
    "ANY": "any",
    "APPROXIMATE_MEDIAN": "approximate_median",
    "ARRAY_AGG": "hash_list",
    "COUNT": "count",  # counts only non nulls
    "COUNT_DISTINCT": "count_distinct",
    "DISTINCT": "distinct",  # fated
    "LIST": "hash_list",  # fated
    "MAX": "max",
    "MAXIMUM": "max",  # alias
    "MEAN": "mean",
    "AVG": "mean",  # alias
    "AVERAGE": "mean",  # alias
    "MIN": "min",
    "MINIMUM": "min",  # alias
    "MIN_MAX": "min_max",
    "ONE": "hash_one",
    "ANY_VALUE": "hash_one",
    "PRODUCT": "product",
    "STDDEV": "stddev",
    "SUM": "sum",
    "VARIANCE": "variance",
}


def _is_count_star(aggregates):
    """
    Is the SELECT clause `SELECT COUNT(*)` with no GROUP BY
    """
    if len(aggregates) != 1:
        return False
    if aggregates[0].value != "COUNT":
        return False
    if aggregates[0].parameters[0].node_type != NodeType.WILDCARD:
        return False
    return True


def _count_star(morsel_promise, column_name):
    count = sum(morsel.num_rows for morsel in morsel_promise.execute())
    table = pyarrow.Table.from_pylist([{column_name: count}])
    yield table


def project(tables, column_names):
    for table in tables:
        row_count = table.num_rows
        if len(column_names) > 0:
            yield table.select(dict.fromkeys(column_names))
        else:
            # if we can't find the column, add a placeholder column
            yield pyarrow.Table.from_pydict({"*": numpy.full(row_count, 1, dtype=numpy.int8)})


def build_aggregations(aggregators):
    column_map = {}
    aggs = []

    if not isinstance(aggregators, list):
        aggregators = [aggregators]

    for root in aggregators:
        for aggregator in get_all_nodes_of_type(root, select_nodes=(NodeType.AGGREGATOR,)):
            field_node = aggregator.parameters[0]
            count_options = None

            if field_node.node_type == NodeType.WILDCARD:
                field_name = "*"
                # count * counts nulls
                count_options = pyarrow.compute.CountOptions(mode="all")
            elif field_node.node_type == NodeType.IDENTIFIER:
                field_name = field_node.schema_column.identity
            elif field_node.node_type == NodeType.LITERAL:
                field_name = str(field_node.value)
            else:
                display_name = field_node.query_column
                raise SqlError(
                    f"Invalid identifier or literal provided in aggregator function `{display_name}`"
                )
            function = AGGREGATORS.get(aggregator.value)
            if aggregator.value == "ARRAY_AGG":
                # if the array agg is distinct, base off that function instead
                if aggregator.parameters[1]:
                    function = "distinct"
            aggs.append((field_name, function, count_options))
            column_map[aggregator.schema_column.identity] = f"{field_name}_{function}".replace(
                "_hash_", "_"
            )

    return column_map, aggs


def _non_group_aggregates(aggregates, table):
    """
    If we're not doing a group by, we're just doing aggregations, the pyarrow
    functionality for aggregate doesn't work. So we do the calculation, it's
    relatively straightforward as it's the entire table we're summarizing.
    """

    result = {}

    for aggregate in aggregates:
        if aggregate.node_type in (NodeType.AGGREGATOR,):
            column_node = aggregate.parameters[0]
            if column_node.node_type == NodeType.LITERAL:
                raw_column_values = numpy.full(table.num_rows, column_node.value)
            elif (
                aggregate.value == "COUNT"
                and aggregate.parameters[0].node_type == NodeType.WILDCARD
            ):
                result["COUNT(*)"] = table.num_rows
                continue
            else:
                raw_column_values = table[column_node.schema_column.identity].to_numpy()
            aggregate_function_name = AGGREGATORS[aggregate.value]
            # this maps a string which is the function name to that function on the
            # pyarrow.compute module
            if not hasattr(pyarrow.compute, aggregate_function_name):
                raise UnsupportedSyntaxError(
                    f"Aggregate `{aggregate.value}` can only be used with GROUP BY"
                )
            aggregate_function = getattr(pyarrow.compute, aggregate_function_name)
            aggregate_column_value = aggregate_function(raw_column_values).as_py()
            result[aggregate.schema_column.identity] = aggregate_column_value

    return pyarrow.Table.from_pylist([result])


def extract_evaluations(aggregates):
    # extract any inner evaluations, like the IIF in SUM(IIF(x, 1, 0))

    all_evaluatable_nodes = get_all_nodes_of_type(
        aggregates,
        select_nodes=(
            NodeType.FUNCTION,
            NodeType.BINARY_OPERATOR,
            NodeType.COMPARISON_OPERATOR,
            NodeType.LITERAL,
        ),
    )

    evaluatable_nodes = []
    for node in all_evaluatable_nodes:
        aggregators = get_all_nodes_of_type(node, select_nodes=(NodeType.AGGREGATOR,))
        if len(aggregators) == 0:
            evaluatable_nodes.append(node)

    return evaluatable_nodes


class AggregateNode(BasePlanNode):
    def __init__(self, properties: QueryProperties, **config):
        super().__init__(properties=properties)

        self.aggregates = config.get("aggregates", [])

        # we're going to preload some of the evaluation

        # get all the columns anywhere in the aggregates
        all_identifiers = [
            node.schema_column.identity
            for node in get_all_nodes_of_type(self.aggregates, select_nodes=(NodeType.IDENTIFIER,))
        ]
        self.all_identifiers = list(dict.fromkeys(all_identifiers))

        # Get any functions we need to execute before aggregating
        self.evaluatable_nodes = extract_evaluations(self.aggregates)

        self.column_map, self.aggregate_functions = build_aggregations(self.aggregates)

    @property
    def config(self):  # pragma: no cover
        return str(self.aggregates)

    @property
    def greedy(self):  # pragma: no cover
        return True

    @property
    def name(self):  # pragma: no cover
        return "Aggregation"

    def execute(self) -> Iterable:
        if len(self._producers) != 1:  # pragma: no cover
            raise SqlError(f"{self.name} on expects a single producer")

        morsels = self._producers[0]  # type:ignore
        if isinstance(morsels, pyarrow.Table):
            morsels = (morsels,)

        if _is_count_star(self.aggregates):
            yield from _count_star(
                morsel_promise=morsels, column_name=self.aggregates[0].schema_column.identity
            )
            return

        # merge all the morsels together into one table, selecting only the columns
        # we're pretty sure we're going to use - this will fail for datasets
        # larger than memory
        table = pyarrow.concat_tables(
            project(morsels.execute(), self.all_identifiers), promote=True
        )

        # Allow grouping by functions by evaluating them first
        start_time = time.time_ns()
        table = evaluate_and_append(self.evaluatable_nodes, table)

        # Add a "*" column, this is an int because when a bool it miscounts
        if "*" not in table.column_names:
            table = table.append_column(
                "*", [numpy.full(shape=table.num_rows, fill_value=1, dtype=numpy.int8)]
            )
        self.statistics.time_evaluating += time.time_ns() - start_time

        start_time = time.time_ns()

        # we're not a group_by - we're aggregating without grouping
        aggregates = _non_group_aggregates(self.aggregates, table)
        del table

        # do the secondary activities for ARRAY_AGG
        for node in get_all_nodes_of_type(self.aggregates, select_nodes=(NodeType.AGGREGATOR,)):
            if node.value == "ARRAY_AGG":
                _, _, order, limit = node.parameters
                if order or limit:
                    # rip the column out of the table
                    column_name = self.column_map[format_expression(node)]
                    column_def = groups.field(column_name)  # this is used
                    column = groups.column(column_name).to_pylist()
                    groups = groups.drop([column_name])
                    # order
                    if order:
                        pass
                    if limit:
                        column = [c[:limit] for c in column]
                    # put the new column into the table
                    groups = groups.append_column(column_def, [column])

        # name the aggregate fields and add them to the Columns data
        aggregates = aggregates.select(list(self.column_map.keys()))
        #        aggregates = aggregates.rename_columns(list(self.column_map.keys()))

        self.statistics.time_aggregating += time.time_ns() - start_time

        yield aggregates
