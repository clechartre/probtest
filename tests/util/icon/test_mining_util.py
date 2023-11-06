""" Testing suite for the text mining and update to kibana script."""

# Standard library
import contextlib
import logging
import unittest
from dataclasses import asdict, dataclass
from datetime import datetime
from unittest import mock

# Third-party
import pytest
from elasticsearch import Elasticsearch

from util.icon.mining_util import (
    MatchResultsICON,
    collect_time_stamp,
    get_experiment_name,
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
            ("some-test-content", ["some", "test", "content"]),
            ("some/test/content", ["some/test/content"]),
            ("Lsome test content", ["some", "test", "content"]),
            ("some tests content", ["some", "tests", "content"]),
            ("some 1m37s contents", ["some", "1m37s", "contents"]),
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
                [
                    MockTable(
                        [
                            "test1   test2 test3 test4 test5 test6 test7 test8 test9   test10  test11  test12    test13"
                        ]
                    )
                ],
                [
                    ["test1"],
                    ["test2"],
                    ["test3"],
                    ["test4"],
                    ["test5"],
                    ["test6"],
                    ["test7"],
                    ["test8"],
                    ["test9"],
                    ["test10"],
                    ["test11"],
                    ["test12"],
                    ["test13"],
                ],
                [
                    MockTable(
                        [
                            ["test1"],
                            ["test2"],
                            ["test3"],
                            ["test4"],
                            ["test5"],
                            ["test6"],
                            ["test7"],
                            ["test8"],
                            ["test9"],
                            ["test10"],
                            ["test11"],
                            ["test12"],
                            ["test13"],
                        ]
                    )
                ],
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
                    "2.0",
                    "3",
                    "4.0",
                    "5.0",
                    "6",
                    "7.0",
                    "8",
                    "9.0",
                    "10",
                    "11.0",
                ],
                MatchResultsICON(
                    name=["name1"],
                    calls=[1],
                    t_min=[2.0],
                    min_rank=[3],
                    t_avg=[4.0],
                    t_max=[5.0],
                    max_rank=[6],
                    total_min=[7.0],
                    total_min_rank=[8],
                    total_max=[9.0],
                    total_max_rank=[10],
                    total_avg=[11.0],
                    pe=[],
                ),
            ),
            (
                [
                    "name2",
                    "12",
                    "13s",
                    "14",
                    "15m16s",
                    "17.0",
                    "18",
                    "19s",
                    "20",
                    "21.0",
                    "22",
                    "23.0",
                ],
                MatchResultsICON(
                    name=["name2"],
                    calls=[12],
                    t_min=[13.0],
                    min_rank=[14],
                    t_avg=[916.0],
                    t_max=[17.0],
                    max_rank=[18],
                    total_min=[19.0],
                    total_min_rank=[20],
                    total_max=[21.0],
                    total_max_rank=[22],
                    total_avg=[23.0],
                    pe=[],
                ),
            ),
            (
                ["1.0", "0.0", "2.0s"],
                MatchResultsICON(
                    name=[1.0],
                    calls=[0.0],
                    t_min=[2.0],
                    min_rank=[],
                    t_avg=[],
                    t_max=[],
                    max_rank=[],
                    total_min=[],
                    total_min_rank=[],
                    total_max=[],
                    total_max_rank=[],
                    total_avg=[],
                    pe=[],
                ),
            ),
        ],
    )
    def test_line_to_dataclass(self, line, expected_dataclass):
        result = line_to_dataclass(line)
        assert asdict(result) == asdict(
            expected_dataclass
        ), f"Expected {asdict(expected_dataclass)}, but got {asdict(result)}"


class TestLogging(unittest.TestCase):
    def setUp(self):
        self.mock_es = mock.MagicMock(spec=Elasticsearch)

    def test_log_mining_calls_update_kibana(self):
        mock_log_file_path = "/mocked/directory/mined_dirs.log"
        with disabled_logging():
            with mock.patch(
                "os.listdir", return_value=["LOG.sample_file_content.txt"]
            ), mock.patch(
                "util.icon.mining_util.get_already_mined_dirs", return_value=[""]
            ), mock.patch(
                "os.path.join", return_value="LOG.file"
            ), mock.patch(
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
                log_mining(directory_path, self.mock_es, mock_log_file_path)
                # Check if update_kibana was called.
                self.mock_es.index.assert_called()


# class TestExperimentName:
#     @pytest.mark.parametrize(
#         "full_file,expected",
#         [
#             (
#                 """
#     SLURMD_NODENAME=nid003161
#     SLURM_JOB_NAME=check.mch_bench_r19b08_kenda1.run
#     SLURM_JOB_UID=24103
#     """,
#                 "check.mch_bench_r19b08_kenda1.run",
#             ),
#             (
#                 """
#     SLURMD_NODENAME=nid003161
#     SLURM_JOB_UID=24103
#     """,
#                 "",
#             ),
#             (
#                 """
#     SLURMD_NODENAME=nid003161
#     SLURM_JOB_NAME=    check.mch_bench_r19b08_kenda1.run
#     SLURM_JOB_UID=24103
#     """,
#                 "check.mch_bench_r19b08_kenda1.run",
#             ),
#         ],
#     )
#     def test_get_experiment_name(full_file, expected):
#         exp = get_experiment_name(full_file)
#         assert exp == expected
