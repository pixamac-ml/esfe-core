from django.apps import AppConfig
import importlib
import pkgutil


class BlogConfig(AppConfig):
    name = "blog"

    def ready(self):
        import ui.components

        def recursive_import(package):
            for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
                full_name = f"{package.__name__}.{module_name}"
                module = importlib.import_module(full_name)
                if is_pkg:
                    recursive_import(module)

        recursive_import(ui.components)
