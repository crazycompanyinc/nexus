from __future__ import annotations

import pytest

from nexus.api.unified import UnifiedToolAPI
from nexus.core.db import NexusStore
from nexus.permissions.access import AccessControl
from nexus.plugins.manager import PluginManager


@pytest.fixture()
def hub():
    store = NexusStore()
    manager = PluginManager(store)
    api = UnifiedToolAPI(store, manager, AccessControl(store))
    manager.install_all_builtins()
    return store, manager, api
