""" Testing suite for the text mining and update to kibana script."""

# Standard library
import contextlib
import logging
import unittest
from dataclasses import dataclass
from datetime import datetime
from unittest import mock

# Third-party
import pytest
from elasticsearch import Elasticsearch

from util.icon.mining_util import (
    MatchResultsICON,
    collect_time_stamp,
    line_to_dataclass,
    log_mining,
    process_line,
    read_logfile,
    remove_formatting,
)


class MockTable:
    def __init__(self, lines):
        self.lines = lines


@dataclass
class MockMatchResultIcon:
    name = ["name1", "name2"]
    calls = [37, 4]


# Define a context manager to temporarily disable logging
@contextlib.contextmanager
def disabled_logging():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture
def setup_text_file(request, tmp_path):
    content = request.param
    file_path = tmp_path / "test_file.txt"
    with open(file_path, "w") as f:
        f.write(content)
    return file_path


class TestReadFile:
    @pytest.mark.parametrize(
        "setup_text_file, expected_content",
        [
            ("This is some test content.", "This is some test content."),
            ("Another line of text.", "Another line of text."),
        ],
        indirect=["setup_text_file"],
    )
    def test_read_file(self, setup_text_file, expected_content: str):
        with disabled_logging():
            result = read_logfile(setup_text_file)
            assert result == expected_content

    def test_read_file_nonexistent(self):
        with disabled_logging():
            with pytest.raises(FileNotFoundError):
                read_logfile("nonexistent_path.txt")


class TestProcessLine:
    @pytest.mark.parametrize(
        "line, expected_process_line",
        [
            ("some test content", ["some", "test", "content"]),
            ("1.85674s      18", ["1.85674", "18"]),
            ("some-test-content", ["some", "test", "content"]),
            ("some/test/content", ["some/test/content"]),
            ("Lsome test content", ["some", "test", "content"]),
        ],
    )
    def test_process_line(self, line, expected_process_line: list):
        with disabled_logging():
            processed_line = process_line(line)
            assert processed_line == expected_process_line


class TestRemoveFormatting:
    @mock.patch("util.icon.mining_util.process_line")
    @pytest.mark.parametrize(
        "tables, mocked_processed_lines, expected_output",
        [
            (
                [MockTable(["test1   ", "test2   ", "   test3"])],
                [["test1"], ["test2"], ["test3"]],
                [MockTable([["test1"], ["test2"], ["test3"]])],
            ),
        ],
    )
    def test_remove_formatting(
        self, mock_process_line, tables, mocked_processed_lines, expected_output
    ):
        mock_process_line.side_effect = mocked_processed_lines

        result = remove_formatting(tables)
        for r, e in zip(result, expected_output):
            assert r.lines == e.lines


date_format = "%a %d %b %Y %I:%M:%S %p %Z"
date_pattern = r"\b\w{3} \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2} [APM]{2} \w{4}\b"


class testCollectTimeStamp:
    @pytest.mark.parametrize(
        "line, expected_time_stamp",
        [
            ("some test content", datetime.now().strftime(date_format)),
            ("Sun 15 Oct 2023 01:18:54 PM CEST", datetime(2023, 10, 15, 13, 18, 54)),
            ("15/10/23 01:18:54", datetime.now().strftime(date_format)),
        ],
        indirect=["setup_text_file"],
    )
    def test_collect_time_stamp(self, line: str, expected_time_stamp: datetime):
        with disabled_logging():
            processed_time_stamp = collect_time_stamp(line)
            assert processed_time_stamp == expected_time_stamp


class TestLineToDataClass:
    @pytest.mark.parametrize(
        "line, expected_dataclass",
        [
            (
                [
                    "name1",
                    "1",
                    "2",
                    "3",
                    "4",
                    "5",
                    "6",
                    "7",
                    "8",
                    "9",
                    "10",
                    "11",
                    "12",
                ],
                MatchResultsICON(
                    ["name1"],
                    [1],
                    [2],
                    [3],
                    [4],
                    [5],
                    [6],
                    [7],
                    [8],
                    [9],
                    [10],
                    [11],
                    [12],
                ),
            ),
            (
                [
                    "name2",
                    "14",
                    "hello",
                    "15",
                    "16",
                    "17",
                    "18",
                    "19",
                    "20",
                    "21",
                    "22",
                    "23",
                    "24",
                ],
                MatchResultsICON(
                    ["name2"],
                    [14],
                    ["hello"],
                    [15],
                    [16],
                    [17],
                    [18],
                    [19],
                    [20],
                    [21],
                    [22],
                    [23],
                    [24],
                ),
            ),
            (["1.0", "2.0"], MatchResultsICON()),  # Incorrect number of items in line.
        ],
    )
    def test_line_to_dataclass(self, line, expected_dataclass):
        result = line_to_dataclass(line)
        assert result == expected_dataclass


class TestLogging(unittest.TestCase):
    def setUp(self):
        self.mock_es = mock.MagicMock(spec=Elasticsearch)

    def test_log_mining_calls_update_kibana(self):
        with disabled_logging():
            with mock.patch(
                "os.listdir", return_value=["LOG.sample_file_content.txt"]
            ), mock.patch("os.path.join", return_value="LOG.file"), mock.patch(
                "util.icon.mining_util.read_logfile", return_value="sample_file_content"
            ), mock.patch(
                "util.icon.mining_util.isolate_table",
                return_value=[MockTable(["sample_line1", "sample_line2"])],
            ), mock.patch(
                "util.icon.mining_util.remove_formatting",
                return_value=[MockTable(["sample_line1", "sample_line2"])],
            ), mock.patch(
                "util.icon.mining_util.collect_time_stamp",
                return_value=["2023/10/01 00:00:00"],
            ), mock.patch(
                "util.icon.mining_util.line_to_dataclass",
                return_value=MockMatchResultIcon(),
            ), mock.patch(
                "util.icon.mining_util.asdict",
                return_value={"names": "name1", "calls": "call1"},
            ), mock.patch(
                "util.icon.mining_util.Elasticsearch", return_value=self.mock_es
            ):
                directory_path = "/directory/path"
                log_mining(directory_path, self.mock_es)
                # Check if update_kibana was called.
                self.mock_es.index.assert_called()
