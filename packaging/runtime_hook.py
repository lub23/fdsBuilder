"""Environment initialisation executed before the packaged application."""

import os

# Ensure pyvistaqt chooses the same Qt binding as the application.  This must
# happen before either PyVistaQt or QtPy is imported.
os.environ.setdefault("QT_API", "pyside6")
