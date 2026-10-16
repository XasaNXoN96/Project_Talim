#!/usr/bin/env python
"""Django command-line utility for the Mirzacho‘l tumani Xalq ta’limi bo‘limi backend."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django is not installed. Activate the virtualenv: "
            "source backend/.venv/bin/activate (see backend/README.md)."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
