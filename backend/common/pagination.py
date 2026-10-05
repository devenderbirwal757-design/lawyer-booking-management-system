from __future__ import annotations

from collections import OrderedDict
from typing import Any

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """Page-number pagination with a hard cap on page size (plan §4)."""

    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data: Any) -> Response:
        page = self.page
        assert page is not None  # set by paginate_queryset before this is called
        request = self.request
        page_size = self.get_page_size(request) if request is not None else self.page_size
        return Response(
            OrderedDict(
                [
                    ("count", page.paginator.count),
                    ("page", page.number),
                    ("page_size", page_size),
                    ("num_pages", page.paginator.num_pages),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )


class CompactPagination(StandardPagination):
    """Compact page size for small admin lookup lists."""

    page_size = 25
    max_page_size = 50
