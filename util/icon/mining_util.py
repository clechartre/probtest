"""Module for mining of ICON logs and update into
 Kibana stack monitoring application."""

import logging
import os
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import List, Optional, Set

# Third-party
from elasticsearch import BadRequestError, Elasticsearch

# Create logger FIXME setup logger file somewhere!
logging.basicConfig(encoding="utf-8", level=logging.DEBUG)
logger = logging.getLogger(__file__)

timing_start_regex = r"(?: +L? ?[a-zA-Z_.]+)"
timing_element_regex = r"(?:\[?\d+[.msh]?\d*s?\]? +)"
timing_regex = timing_start_regex + " +" + timing_element_regex + "{6,20} *(?!.)"
header_regex = r"name +.*calls +t_min +min rank.*"
date_format = "%a %d %b %Y %I:%M:%S %p %Z"
date_pattern = r"\b\w{3} \d{2} \w{3} \d{4} \d{2}:\d{2}:\d{2} [APM]{2} \w{4}\b"
index = "icon"


@dataclass
class MatchResultsICON:
    name: List[str] = field(default_factory=list)
    calls: List[int] = field(default_factory=list)
    t_min: List[float] = field(default_factory=list)
    min_rank: List[int] = field(default_factory=list)
    t_avg: List[float] = field(default_factory=list)
    t_max: List[float] = field(default_factory=list)
    max_rank: List[int] = field(default_factory=list)
    total_min: List[float] = field(default_factory=list)
    total_min_rank: List[int] = field(default_factory=list)
    total_max: List[float] = field(default_factory=list)
    total_max_rank: List[int] = field(default_factory=list)
    total_avg: List[float] = field(default_factory=list)
    pe: Optional[List[float]] = field(default_factory=list)

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

    Raises:
        FileNotFoundError: If the log file does not exist.
        PermissionError: If the log file cannot be accessed due to permission errors.
        IOError: If the log file is not readable or other IO related errors occur.
    """
    if not os.path.exists(file_path):
        logger.error("File not found: %s", file_path)
        raise FileNotFoundError(f"File not found: {file_path}")

    if not os.access(file_path, os.R_OK):
        logger.error("File not readable: %s", file_path)
        raise PermissionError(f"File not readable: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except PermissionError as e:
        logger.error("Permission denied: %s", e)
        raise
    except IOError as e:
        logger.error("IOError when reading file: %s", e)
        raise


def get_experiment_name(full_file: str) -> str:
    """Mine the experiment name for the log.

    Args:
        full_file (str): log content

    Returns:
        str: experiment name

    """
    experiment_regex = r"SLURM_JOB_NAME=(.*)"
    match = re.search(experiment_regex, full_file)
    if match:
        experiment_name = match.group(1)
        return experiment_name.strip()
    else:
        return ""


def is_number_with_s(element: str):
    """Identify whether the element is a time or a word.
    We'll remove the s only if the element represents time


    Args:
        element (str)): element of the log file string

    Returns:
        bool: whether we filter the element or not
    """

    return bool(re.match(r"^\d+(\.\d+)?\(s\)$", element))


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

    # Filter out unwanted elements
    elements = [
        elem
        for elem in elements
        if not (is_number_with_s(elem) or elem in [" ", "#", ""])
    ]

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
    all_header_lines = [i for i, e in enumerate(log_file) if re.search(header_regex, e)]
    # Filter out unwanted tables
    header_lines = []
    for line_index in all_header_lines:
        actual_line = log_file[line_index]
        processed_header = process_line(actual_line)
        if len(processed_header) >= 12:  # Only keep headers of length 12 or more
            header_lines.append(line_index)

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
        # Filter lines that have the same length as the maximum length
        new_lines = []
        for line in processed_lines:
            # Nb of values in the dataclass
            if len(line) == 13 or len(line) == 12:
                new_lines.append(line)
            else:
                logging.info(f"Removed line for line: {line} ")

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
        date_objects = datetime.strftime(now, date_format)

    return date_objects


def line_to_dataclass(line: list) -> MatchResultsICON:
    """Store line information in dataclass.

    Args:
        line (list): A list containing the values extracted from a log line.

    Returns:
        MatchResultsICON: Information stored into a dataclass.

    """
    results_dataclass = MatchResultsICON()
    attribute_names = [field.name for field in fields(MatchResultsICON)]

    for i, value in enumerate(line):
        if isinstance(value, str) and value.endswith("s"):
            if value[:-1].replace(".", "", 1).isdigit():
                value = float(value[:-1])
            else:
                # Handle the case where the format is like '2m30s' for 2 minutes and 30 seconds
                match = re.search(r"(\d+)m(\d+)s", value)
                if match:
                    minutes, seconds = match.groups()
                    value = float(minutes) * 60 + float(seconds)

        try:
            value = float(value) if not isinstance(value, float) else value

            if value < 0:
                value = abs(value)

            if value == 0:
                value = int(value)
        except ValueError:
            pass

        getattr(results_dataclass, attribute_names[i]).append(value)

    return results_dataclass


def update_kibana(es: Elasticsearch, result_dict: dict):
    """Update automatically the summary into kibana.

    Args:
        es (Elasticsearch): connection to elastic search service
        summary (dict): summary statistics to ingest

    """
    es.index(index="icon", document=result_dict)


def get_already_mined_dirs(log_file_path: str) -> Set[str]:
    """Read the log file and get a set of already mined directories."""
    if not os.path.exists(log_file_path):
        open(log_file_path, "w").close()

    # Read the existing log file and collect the mined directories
    with open(log_file_path, "r") as file:
        mined_dirs = {line.strip() for line in file}

    return mined_dirs


def add_mined_dir(log_file_path: str, directory_path: str) -> None:
    """Add a newly mined directory to the log file."""
    with open(log_file_path, "a") as file:
        file.write(directory_path + "\n")


def log_mining(directory_path: str, es: Elasticsearch, log_file_path: str) -> None:
    """Process file into Kibana compatible format.

    Args:
        file_path (str): path to log file

    Returns:
        result_dict (dict): table information into ingestable format

    """
    logger.info("Processing files in directory: %s", directory_path)

    # Get the set of already mined directories
    mined_dirs = get_already_mined_dirs(log_file_path)

    for root, dirs, files in os.walk(directory_path):
        # Check if the current directory has been mined
        if root in mined_dirs:
            continue

        for filename in files:
            if filename.startswith("LOG."):
                logger.info("Processing file: %s", filename)
                file_path = os.path.join(root, filename)

                # Mine file
                try:
                    full_file = read_logfile(file_path)
                except (FileNotFoundError, PermissionError, IOError) as e:
                    logger.error("Could not read file, %s error", e)
                result = isolate_table(full_file, header_regex)
                if result is None:
                    logger.info("No result table found, exiting")
                    break
                tables = remove_formatting(result)

                # Process the time stamp
                all_dates = []
                all_dates.append(collect_time_stamp(full_file))

                # Sort and retrieve the latest date
                all_dates.sort()
                latest_date = all_dates[-1] if all_dates else None

                # Check if latest_date is a list, if so, take the first element
                if isinstance(latest_date, list):
                    latest_date = latest_date[0]

                if not isinstance(latest_date, datetime):
                    try:
                        latest_date = datetime.strptime(latest_date, date_format)
                    except ValueError as e:
                        logging.debug(f"Error converting latest_date to datetime: {e}")
                        latest_date = datetime.now()

                # Get the experiment name
                experiment_name = get_experiment_name(full_file)

                # Make the result dictionary
                for table in tables:
                    if table.lines[1:][0] == "wrt_output":
                        break
                    for line in table.lines[1:]:
                        results_dataclass = line_to_dataclass(line)
                        result_dict = asdict(results_dataclass)
                        result_dict["time_stamp"] = latest_date
                        result_dict["experiment"] = experiment_name
                        # Update onto monitoring stack
                        try:
                            update_kibana(es, result_dict)
                        except BadRequestError as e:
                            logging.error("Error %s skipping line %s", e, line)
                            continue

                # Add to log if file has been correctly processed
                add_mined_dir(log_file_path, root)
