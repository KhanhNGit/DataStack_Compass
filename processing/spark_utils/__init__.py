"""DataStack Compass — Spark utilities package."""

try:
    from processing.spark_utils.session import get_spark_session
    __all__ = ["get_spark_session"]
except ImportError:
    __all__ = []
