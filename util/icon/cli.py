"""Command line interface of ICON log mining and update to Kibana."""

# Standard library
from typing import Any

# Third-party
import click
from elasticsearch import Elasticsearch

# First-party
from mining_util import log_mining


@click.command()
@click.option(
    "--directory_path",
    "-d",
    required=False,
    type=click.Path(exists=True),
    help="The path to the directory containing summary files.",
)
@click.option(
    "--password",
    "-p",
    required=True,
    help="The password to connect to Elasticsearch",
)
def main(directory_path: Any, password: str):
    """CLI for processing summary files in a directory."""
    es = Elasticsearch(
        "https://elastic.mch.eck.cscs.ch:9200",
        basic_auth=("elastic", password),
    )

    log_mining(directory_path, es)


if __name__ == "__main__":
    main()
