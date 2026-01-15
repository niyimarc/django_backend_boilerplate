from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
import math

class PlanPagination(PageNumberPagination):
    page_size = 10  # default number of plans per page
    page_size_query_param = "page_size"  # allow ?page_size=20
    max_page_size = 100  # prevent abuse

class SubscriptionPagination(PageNumberPagination):
    """
    Custom pagination for subscriptions.
    Returns a clean structure with count, total pages, next, previous, and results.
    """
    page_size = 5  # default per page
    page_size_query_param = "page_size"
    max_page_size = 50

    def get_paginated_response(self, data):
        total_pages = math.ceil(self.page.paginator.count / self.get_page_size(self.request))
        current_page = self.page.number

        return Response({
            "count": self.page.paginator.count,
            "page": current_page,
            "pages": total_pages,
            "next": current_page + 1 if self.page.has_next() else None,
            "previous": current_page - 1 if self.page.has_previous() else None,
            "results": data,
        })