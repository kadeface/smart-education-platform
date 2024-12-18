from .views import (
    exam_list_view,
    exam_statistics_view,
    get_exam_statistics,
    export_statistics
)
from .client import (
    client_exam_list,
    client_exam_detail,
    view_statistics_result

)
__all__ = [
    'exam_list_view',
    'exam_statistics_view',
    'get_exam_statistics',
    'export_statistics'
]