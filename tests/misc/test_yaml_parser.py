import os
import sys

sys.path.insert(1, os.path.join(sys.path[0], "../.."))

from opteryx.config import parse_yaml


def test_parse_string():
    yaml_string = "name: John Doe"
    expected_output = {"name": "John Doe"}

    # Call the YAML parser function
    output = parse_yaml(yaml_string)

    assert output == expected_output, output


def test_parse_number():
    yaml_string = """
    age: 30
    height: 1.83
    ip: 10.10.10.10
    """
    expected_output = {"age": 30, "height": 1.83, "ip": "10.10.10.10"}

    # Call the YAML parser function
    output = parse_yaml(yaml_string)

    assert output == expected_output, output


def test_parse_list():
    yaml_string = "hobbies: [reading, writing, hiking]"
    expected_output = {"hobbies": ["reading", "writing", "hiking"]}

    # Call the YAML parser function
    output = parse_yaml(yaml_string)

    assert output == expected_output, output


def test_parse_comments_line():
    yaml_string = """
    # how old
    age: 30

    height: 1.83
    ip: 10.10.10.10
    """
    expected_output = {"age": 30, "height": 1.83, "ip": "10.10.10.10"}

    # Call the YAML parser function
    output = parse_yaml(yaml_string)

    assert output == expected_output, output


def test_parse_comments_inline():
    yaml_string = """
    age: 30     # how old
    height: 1.83
    ip: 10.10.10.10
    """
    expected_output = {"age": 30, "height": 1.83, "ip": "10.10.10.10"}

    # Call the YAML parser function
    output = parse_yaml(yaml_string)

    assert output == expected_output, output


def test_parse_nested_structure():
    yaml_string = """
    name: John Doe
    age: 30
    details:
        hobbies: [reading, writing, hiking]
        location: New York
        distance: 0.5
    friends:
        - billy
        - tony
    """
    expected_output = {
        "name": "John Doe",
        "age": 30,
        "details": {
            "hobbies": ["reading", "writing", "hiking"],
            "location": "New York",
            "distance": 0.5,
        },
        "friends": ["billy", "tony"],
    }

    # Call the YAML parser function
    output = parse_yaml(yaml_string)

    assert output == expected_output, output


if __name__ == "__main__":  # pragma: no cover
    from tests.tools import run_tests

    run_tests()
