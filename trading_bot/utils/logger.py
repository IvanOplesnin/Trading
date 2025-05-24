import functools
import inspect
import logging
from logging.handlers import RotatingFileHandler

FORMAT = '[%(asctime)s:%(name)s-:%(levelname)s] - %(message)s'
formatter = logging.Formatter(FORMAT)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.DEBUG)

# file_handler = RotatingFileHandler(
#     'logs/logs.log', mode='a', maxBytes=10 * 1024 * 1024, backupCount=15
# )
# file_handler.setFormatter(formatter)
# file_handler.setLevel(logging.DEBUG)

logging.basicConfig(level=logging.DEBUG, handlers=[stream_handler])
logger = logging.getLogger(__name__)


def log(func):
    """
    Универсальный декоратор: логирует вызов, результат, время выполнения
    и исключения для sync/async функций.
    """
    is_coro = inspect.iscoroutinefunction(func)

    @functools.wraps(func)
    async def _async_wrapper(*args, **kwargs):
        name = func.__name__
        params = []
        if args:
            params.append(f"args={args}")
        if kwargs:
            params.append(f"kwargs={kwargs}")
        params = ", ".join(params) or "no parameters"
        logger.info(f"→ {name}({params}) [async] старт")
        try:
            result = await func(*args, **kwargs)
        except Exception:
            logger.exception(f"✕ {name} вызвала исключение")
            raise
        else:
            logger.info(f"✓ {name} завершила работу -> {result}")
            return result

    @functools.wraps(func)
    def _sync_wrapper(*args, **kwargs):
        name = func.__name__
        params = []
        if args:
            params.append(f"args={args}")
        if kwargs:
            params.append(f"kwargs={kwargs}")
        params = ", ".join(params) or "no parameters"
        logger.info(f"→ {name}({params}) старт")
        try:
            result = func(*args, **kwargs)
        except Exception:
            logger.exception(f"✕ {name} вызвала исключение")
            raise
        else:
            logger.info(f"✓ {name} завершила работу -> {result}")
            return result

    return _async_wrapper if is_coro else _sync_wrapper


