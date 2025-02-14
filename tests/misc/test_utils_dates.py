import os
import sys

sys.path.insert(1, os.path.join(sys.path[0], "../.."))

import datetime
import numpy
import pytest

from opteryx.utils import dates

# fmt:off
DATE_TESTS = [
        ("NOT A DATE", None),
        ("2021001011", None),
        ("2021-02-21", datetime.datetime(2021,2,21)),
        ("2021-02-21T", None),
        ("2021-01-11 12:00", datetime.datetime(2021,1,11,12,0)),
        ("2021-01-11 12:00+0100", datetime.datetime(2021,1,11,12,0)),
        ("2021-01-11 12:00Z", datetime.datetime(2021,1,11,12,0)),
        ("2021-01-11T12:00", datetime.datetime(2021,1,11,12,0)),
        ("2021-01-11T12:00Z", datetime.datetime(2021,1,11,12,0)),
        ("2020-10-01 18:05:20", datetime.datetime(2020,10,1,18,5,20)),
        ("2020-10-01T18:05:20", datetime.datetime(2020,10,1,18,5,20)),
        ("2020-10-01T18:05:20+0100", datetime.datetime(2020,10,1,18,5,20)),
        ("1999-12-31 23:59:59.9", datetime.datetime(1999,12,31,23,59,59)),
        ("1999-12-31 23:59:59.9999", datetime.datetime(1999,12,31,23,59,59)),
        ("1999-12-31T23:59:59.9999", datetime.datetime(1999,12,31,23,59,59)),
        ("1999-12-31T23:59:59.9999Z", datetime.datetime(1999,12,31,23,59,59)),
        ("1999-12-31T23:59:59.999999", datetime.datetime(1999,12,31,23,59,59)),
        ("1999-12-31T23:59:59.999999+0800", datetime.datetime(1999,12,31,23,59,59)),
        ("1999-12-31T23:59:59.99999999", datetime.datetime(1999,12,31,23,59,59)),

        (numpy.datetime64('2021-02-21'), datetime.datetime(2021, 2, 21)),  # Numpy datetime64 to datetime
        (numpy.datetime64('2021-02-21T12:00:00'), datetime.datetime(2021, 2, 21, 12, 0)),  # Numpy datetime64 with time to datetime
        (numpy.int64(1585699200), datetime.datetime(2020, 4, 1, 0, 0)),  # Unix timestamp as numpy int64 to datetime
        (1585699200, datetime.datetime(2020, 4, 1, 0, 0)),  # Unix timestamp as int to datetime
        (1585699200.0, datetime.datetime(2020, 4, 1, 0, 0)),  # Unix timestamp as float to datetime
        (datetime.date(2021, 2, 21), datetime.datetime(2021, 2, 21)),  # Python date to datetime
        (numpy.datetime64('2021-02-21T12:00:00Z'), datetime.datetime(2021, 2, 21, 12, 0)),  # Numpy datetime64 with time and timezone (ignored) to datetime
        (numpy.int64(1585699200), datetime.datetime(2020, 4, 1, 0, 0)),  # Unix timestamp as numpy int64 to datetime (repeated to ensure cache performance)
        (datetime.datetime(2021, 2, 21, 12, 0), datetime.datetime(2021, 2, 21, 12, 0)),  # Python datetime to datetime (no conversion)
        ("2021-02-30", None),  # Invalid date to None
        (1613918723, datetime.datetime(2021, 2, 21, 14, 45, 23)),  # Unix timestamp (seconds since epoch)
        (1613918723.5678, datetime.datetime(2021, 2, 21, 14, 45, 23)),  # Unix timestamp with fractional seconds
        (numpy.datetime64('2021-02-21'), datetime.datetime(2021, 2, 21)),  # numpy datetime64 with date only
        (numpy.datetime64('2021-02-21T15:32:03'), datetime.datetime(2021, 2, 21, 15, 32, 3)),  # numpy datetime64 with date and time
        (numpy.datetime64('2021-02-21T15:32:03.5678'), datetime.datetime(2021, 2, 21, 15, 32, 3)),  # numpy datetime64 with fractional seconds
        (datetime.datetime(2021, 2, 21, 15, 32, 3), datetime.datetime(2021, 2, 21, 15, 32, 3)),  # datetime object
        (datetime.date(2021, 2, 21), datetime.datetime(2021, 2, 21)),  # date object
        (numpy.datetime64('2021-02-21T00:00:00.000000000Z'), datetime.datetime(2021, 2, 21, 0, 0)),  # numpy datetime64 with Z timezone
        (numpy.datetime64('2021-02-21T00:00:00.000000000+0000'), datetime.datetime(2021, 2, 21, 0, 0)),  # numpy datetime64 with +0000 timezone
        (numpy.datetime64('2021-02-21T00:00:00.000000000-0000'), datetime.datetime(2021, 2, 21, 0, 0)),  # numpy datetime64 with -0000 timezone

        ("2021/02/21", None),  # Wrong separators
        ("2021-13-01", None),  # Invalid month
        ("2021-02-30", None),  # Invalid day
        ("2021-02-21T24:00", None),  # Invalid hour
        ("2021-02-21T12:60", None),  # Invalid minute
        ("2021-02-21T12:00:60", None),  # Invalid second
        ("2021-02-21T1200:00", None),  # No separator between date and time
    ]
# fmt:on


@pytest.mark.parametrize("string, expect", DATE_TESTS)
def test_date_parser(string, expect):
    assert dates.parse_iso(string) == expect, f"{string}  {dates.parse_iso(string)}  {expect}"


if __name__ == "__main__":  # pragma: no cover
    print(f"RUNNING BATTERY OF {len(DATE_TESTS)} DATE TESTS")
    for date_string, date_date in DATE_TESTS:
        print(str(date_string).ljust(33), date_date)
        test_date_parser(date_string, date_date)
    print("✅ okay")
