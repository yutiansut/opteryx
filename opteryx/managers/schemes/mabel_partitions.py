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

import datetime
from typing import Callable
from typing import List
from typing import Optional

from opteryx.managers.schemes import BasePartitionScheme


def _extract_part_from_path(path, prefix):
    """Extract the part of the path starting with a specific prefix"""
    for part in path.split("/"):
        if part.startswith(prefix):
            return part


def _extract_as_at(path):
    return _extract_part_from_path(path, "as_at_")


def _extract_by(path):
    return _extract_part_from_path(path, "by_")


def _safe_get_next_element(lst, item):
    """get the element from a list which follows a given element"""
    try:
        index = lst.index(item)
        return lst[index + 1]
    except IndexError:
        return None


_is_complete = lambda blobs, as_at: any(blob for blob in blobs if as_at + "/frame.complete" in blob)
_is_invalid = lambda blobs, as_at: any(blob for blob in blobs if as_at + "/frame.ignore" in blob)


class MabelPartitionScheme(BasePartitionScheme):
    """
    Handle reading data using the Mabel partition scheme.
    """

    def get_blobs_in_partition(
        self,
        *,
        start_date: Optional[datetime.datetime],
        end_date: Optional[datetime.datetime],
        blob_list_getter: Callable,
        prefix: str,
    ) -> List[str]:
        """filter the blobs acording to the chosen scheme"""

        def _inner(*, timestamp):
            year = timestamp.year
            month = timestamp.month
            day = timestamp.day
            hour = timestamp.hour

            date_path = f"{prefix}/year_{year:04d}/month_{month:02d}/day_{day:02d}"

            # Call your method to get the list of blob names
            blob_names = blob_list_getter(prefix=date_path)

            if len({_extract_by(blob) for blob in blob_names} - {"by_hour", None}) > 0:
                from opteryx.exceptions import UnsupportedSegementationError

                raise UnsupportedSegementationError(dataset=prefix)

            # Filter for the specific hour, if hour folders exist - prefer by_hour segements
            if any(f"/by_hour/hour={hour:02d}/" in blob_name for blob_name in blob_names):
                blob_names = [
                    blob_name
                    for blob_name in blob_names
                    if f"/by_hour/hour={hour:02d}/" in blob_name
                ]

            as_at = None
            as_ats = sorted({_extract_as_at(blob) for blob in blob_names if "as_at_" in blob})

            # Keep popping from as_ats until a valid frame is found
            while as_ats:
                as_at = as_ats.pop()
                if _is_complete(blob_names, as_at) and not _is_invalid(blob_names, as_at):
                    break
                else:
                    blob_names = [blob for blob in blob_names if as_at not in blob]
                as_at = None

            if as_at:
                yield from (blob for blob in blob_names if as_at in blob)

            yield from blob_names

        start_date = start_date or datetime.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_date = end_date or datetime.datetime.utcnow().replace(
            hour=23, minute=59, second=0, microsecond=0
        )

        seen = set()
        for segment_timeslice in self.hourly_timestamps(start_date, end_date):
            blobs = _inner(timestamp=segment_timeslice)
            for blob_name in sorted(set(blobs).difference(seen)):
                yield blob_name
                seen.add(blob_name)
