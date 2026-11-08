#!/usr/bin/env python
"""Django entry point for the Supernova Search admin/UI deployment."""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "supernova_site.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
