import importlib
import pkgutil


# Load every module to trigger their registrations.
def load_all_extensions():
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{module_name}")


load_all_extensions()
