from importlib import import_module
from .constants import SUBSCRIPTIONS

# Built-in hard fallback in case key is missing in constants
_HARD_DEFAULTS = {
    "PERIOD_FUNC": "subscriptions.periods.monthly_or_yearly",
}

def get_setting(key: str, default=None):
    if default is None:
        default = _HARD_DEFAULTS.get(key)
    return SUBSCRIPTIONS.get(key, default)

def load_callable(path_or_callable):
    if callable(path_or_callable):
        return path_or_callable
    module_path, func_name = path_or_callable.rsplit(".", 1)
    return getattr(import_module(module_path), func_name)

def get_period_func():
    return load_callable(get_setting("PERIOD_FUNC"))
