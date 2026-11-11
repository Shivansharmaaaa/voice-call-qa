from .flow import check_coverage, check_early_exit, check_order
from .language import check_language
from .repeats import check_repeats
from .turns import check_latency, check_one_question

REGISTRY = {
    "coverage": check_coverage,
    "order": check_order,
    "early_exit": check_early_exit,
    "one_question": check_one_question,
    "repeats": check_repeats,
    "language": check_language,
    "latency": check_latency,
}
