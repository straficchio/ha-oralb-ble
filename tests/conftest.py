"""Load the pure protocol modules and enable HA custom component tests."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "oralb_ble"
PKG = "oralb_ble_test"

pkg = types.ModuleType(PKG)
pkg.__path__ = [str(COMPONENT)]
sys.modules[PKG] = pkg

for name in ("const", "protocol"):
    spec = importlib.util.spec_from_file_location(f"{PKG}.{name}", COMPONENT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{PKG}.{name}"] = module
    spec.loader.exec_module(module)

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    yield
