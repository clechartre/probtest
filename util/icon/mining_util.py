"""Module for mining of ICON logs and update into
 Kibana stack monitoring application."""

import logging
import os
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import List

# Third-party
from elasticsearch import Elasticsearch

# Create logger FIXME setup logger file somewhere!
logging.basicConfig(encoding="utf-8", level=logging.DEBUG)
logger = logging.getLogger(__file__)

timing_start_regex = r"(?: +L? ?[a-zA-Z_.]+)"
timing_element_regex = r"(?:\[?\d+[.msh]?\d*s?\]? +)"
timing_regex = timing_start_regex + " +" + timing_element_regex + "{6,20} *(?!.)"
header_regex = r"name +.*calls.*"
date_format = "%a %d %b %Y %I:%M:%S %p %Z"
date_pattern = r"\b\w{3} \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2} [APM]{2} \w{4}\b"
index = "icon"


@dataclass
class MatchResultsICON:
    name: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    t_min: list = field(default_factory=list)
    min_rank: list = field(default_factory=list)
    t_avg: list = field(default_factory=list)
    t_max: list = field(default_factory=list)
    max_rank: list = field(default_factory=list)
    total_min: list = field(default_factory=list)
    total_min_rank: list = field(default_factory=list)
    total_max: list = field(default_factory=list)
    total_max_rank: list = field(default_factory=list)
    total_avg: list = field(default_factory=list)
    pe: list = field(default_factory=list)

    def __getitem__(self, key):
        return getattr(self, key)


class Table:
    def __init__(self, lines):
        # Remove white spaces at the beginning and end of each line
        self.lines = [line.strip() for line in lines]

    def __str__(self):
        return "\n".join(self.lines)


def read_logfile(file_path: str) -> str:
    """Read the summary log file.

    Args:
        file_path (str): path to file

    Returns:
        str: file as a string

    """
    if not os.path.exists(file_path):
        logger.error("File not found: %s", file_path)
        raise FileNotFoundError
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def process_line(line: str) -> list:
    """Remove white space and formatting in table line.

    Args:
        line (str):individual log file line

    Returns:
        list: line elements as list
    """
    # Replace multiple consecutive whitespaces with a single '-'
    line = re.sub(r"[\s]+", "-", line)

    if line.startswith("L"):
        line = line.lstrip("L-")

    # Split the line into list
    elements = line.split("-")

    # Remove the units (s) at the end of the element
    elements = [elem.rstrip("s") if elem.endswith("s") else elem for elem in elements]

    # Filter out unwanted elements
    elements = [elem for elem in elements if elem not in [" ", "(s)", "#", ""]]

    return elements


def isolate_table(full_file: str, header_regex: str) -> List[Table]:
    """Mine the table from the log.

    Args:
        full_file (str): log file as string
        header_regex (str): regular expression pattern for table header

    Raises:
        ValueError: no information table found

    Returns:
        List[Table]: list of all tables available in the log

    """
    # Split file into lines and remove empty ones
    log_file = [e for e in full_file.split("\n") if e]

    # Find header lines
    header_lines = [i for i, e in enumerate(log_file) if re.search(header_regex, e)]

    # find end line (footer)
    pattern = r"-" * 165
    footer_lines = [i for i, e in enumerate(log_file) if re.search(pattern, e)]

    if not header_lines or not footer_lines:
        logger.error("No headers or footers found in the log")
        return

    tables = []

    for i in range(len(header_lines)):
        start = header_lines[i]
        # Check if we have a corresponding footer for this header
        end = next((f for f in footer_lines if f > start), None)
        if end is None:
            continue

        # Append table without headers
        table = Table(log_file[start + 3 : end])
        tables.append(table)

        # Remove this footer so it won't be used again
        footer_lines.remove(end)

    return tables


def remove_formatting(tables: list) -> list:
    """Process table structure.

    Make the table machine readable by removing indents and
    white spaces.

    Args:
        tables (list): tables mined from the log

    Returns:
        list: comma-separated table values

    """
    for table in tables:
        processed_lines = [process_line(line) for line in table.lines]

        # Get the maximum length after processing
        max_length = max(len(line) for line in processed_lines)

        # Filter lines that have the same length as the maximum length
        new_lines = []
        for line in processed_lines:
            if len(line) == max_length:
                new_lines.append(line)
            else:
                logging.info("Removed line for value %s", {line[0]})

        table.lines = new_lines

    return tables


def collect_time_stamp(file: str) -> List[datetime]:
    """Extract date strings.

    Args:
        file (str): log file as string

    Returns:
        date_objects (list[datetime]): all dates recorded in the log

    """
    dates = re.findall(date_pattern, file)
    if dates:
        date_objects = [datetime.strptime(date, date_format) for date in dates]
    else:
        logger.debug("No date found in file, replacing with current time")
        now = datetime.now()
        date_objects = datetime.strptime(now, date_format)

    return date_objects


def line_to_dataclass(line: list) -> MatchResultsICON:
    """Store line information in dataclass.

    Args:
        tables (list): tables extracted from the log

    Returns:
        MatchResultsICON: ifnromation stored into a dataclass

    """
    results_dataclass = MatchResultsICON()
    # List of attribute names in the order they should be accessed
    attribute_names = [field.name for field in fields(MatchResultsICON)]

    # Check if the line has the right number of values for all attributes
    if len(line) == len(attribute_names):
        for i, attr_name in enumerate(attribute_names):
            try:
                value = float(line[i])
                getattr(results_dataclass, attr_name).append(value)
            except ValueError:
                getattr(results_dataclass, attr_name).append(line[i])
    # If not the right length, skip the line
    else:
        pass

    return results_dataclass


def update_kibana(es: Elasticsearch, result_dict: dict):
    """Update automatically the summary into kibana.

    Args:
        es (Elasticsearch): connection to elastic search service
        summary (dict): summary statistics to ingest

    """
    es.index(index="icon", document=result_dict)


def log_mining(directory_path: str, es: Elasticsearch) -> None:
    """Process file into Kibana compatible format.

    Args:
        file_path (str): path to log file

    Returns:
        result_dict (dict): table information into ingestable format

    """
    logger.info("Processing files in directory: %s", directory_path)

    for filename in os.listdir(directory_path):
        if filename.startswith("LOG."):
            logger.info("Processing file: %s", filename)

            file_path = os.path.join(directory_path, filename)

            # Mine file
            full_file = read_logfile(file_path)
            result = isolate_table(full_file, header_regex)
            tables = remove_formatting(result)

            # Process the time stamp
            all_dates = []
            all_dates.extend(collect_time_stamp(full_file))

            # Sort and retrieve the latest date
            all_dates.sort()
            latest_date = all_dates[-1] if all_dates else None

            # Make the result dictionary
            for table in tables:
                for line in table.lines[1:]:
                    results_dataclass = line_to_dataclass(line)
                    result_dict = asdict(results_dataclass)
                    result_dict["time_stamp"] = latest_date
                    # Update onto monitoring stack
                    update_kibana(es, result_dict)
