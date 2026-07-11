#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Compatibility exports for dialog classes.

The concrete implementations live in ``ui.dialog_windows`` so each dialog can be
maintained independently while existing imports such as ``from ui.dialogs import
CombustibleSelectionDialog`` keep working.
"""

from ui.dialog_windows import (
    CategoryGenerateDialog,
    CombustibleDialog,
    CombustibleSelectionDialog,
    FacilityCombustibleOverviewDialog,
    FireCompartmentDialog,
    OpeningDialog,
)

__all__ = [
    "OpeningDialog",
    "CombustibleDialog",
    "FireCompartmentDialog",
    "CategoryGenerateDialog",
    "CombustibleSelectionDialog",
    "FacilityCombustibleOverviewDialog",
]
