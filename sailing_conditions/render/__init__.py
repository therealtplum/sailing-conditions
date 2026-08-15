"""Renderers. One report, several audiences.

Every renderer is a pure function of a :class:`~sailing_conditions.models.Report`.
None of them fetch, score, or mutate anything — which is why they are
trivial to test and why adding a new output format never touches the model.
"""

from . import html, jsonout, slack
from .console import render_day, render_report, render_summary

__all__ = [
    "html",
    "jsonout",
    "render_day",
    "render_report",
    "render_summary",
    "slack",
]
