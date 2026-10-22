"""Unit tests of the logging configuration."""

import logging

import pytest

from access_it.common.log import setup_logging


@pytest.fixture(autouse=True)
def restore_logging():
    """Restore the configuration of the root logger after each test."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_messages_have_time_level_and_module(capsys):
    setup_logging()
    logging.getLogger("access_it.etl.extract.races").warning("3 page(s) skipped")
    line = capsys.readouterr().out.strip()
    assert line.endswith("WARNING access_it.etl.extract.races: 3 page(s) skipped")
    assert line[:4].isdigit()  # starts with the date


def test_setup_twice_does_not_duplicate_lines(capsys):
    setup_logging()
    setup_logging()
    logging.getLogger("access_it").info("once")
    assert capsys.readouterr().out.count("once") == 1


def test_debug_messages_are_hidden_by_default(capsys):
    setup_logging()
    logging.getLogger("access_it").debug("details")
    assert capsys.readouterr().out == ""
