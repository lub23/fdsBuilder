"""Dialog classes split from the historical ui.dialogs module."""

from .opening_dialog import OpeningDialog
from .combustible_dialog import CombustibleDialog
from .fire_compartment_dialog import FireCompartmentDialog
from .category_generate_dialog import CategoryGenerateDialog
from .combustible_selection_dialog import CombustibleSelectionDialog
from .facility_combustible_overview_dialog import FacilityCombustibleOverviewDialog

__all__ = [
    "OpeningDialog",
    "CombustibleDialog",
    "FireCompartmentDialog",
    "CategoryGenerateDialog",
    "CombustibleSelectionDialog",
    "FacilityCombustibleOverviewDialog",
]
