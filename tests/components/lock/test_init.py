"""The tests for the lock component."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from homeassistant.components.lock import (
    ATTR_CODE,
    CONF_DEFAULT_CODE,
    STATE_JAMMED,
    STATE_LOCKED,
    STATE_LOCKING,
    STATE_UNLOCKED,
    STATE_UNLOCKING,
    LockEntity,
    LockEntityFeature,
)
from homeassistant.core import HomeAssistant
import homeassistant.helpers.entity_registry as er
from homeassistant.setup import async_setup_component

from tests.testing_config.custom_components.test.lock import MockLock


class MockLockEntity(LockEntity):
    """Mock lock to use in tests."""

    def __init__(
        self,
        code_format: str | None = None,
        lock_option_default_code: str = "",
        supported_features: LockEntityFeature = LockEntityFeature(0),
    ) -> None:
        """Initialize mock lock entity."""
        self._attr_supported_features = supported_features
        self.calls_lock = MagicMock()
        self.calls_unlock = MagicMock()
        self.calls_open = MagicMock()
        if code_format is not None:
            self._attr_code_format = code_format
        self._lock_option_default_code = lock_option_default_code

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        self.calls_lock(kwargs)
        self._attr_is_locking = False
        self._attr_is_locked = True

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        self.calls_unlock(kwargs)
        self._attr_is_unlocking = False
        self._attr_is_locked = False

    async def async_open(self, **kwargs: Any) -> None:
        """Open the door latch."""
        self.calls_open(kwargs)


async def test_lock_default(hass: HomeAssistant) -> None:
    """Test lock entity with defaults."""
    lock = MockLockEntity()
    lock.hass = hass

    assert lock.code_format is None
    assert lock.state is None


async def test_lock_states(hass: HomeAssistant) -> None:
    """Test lock entity states."""

    lock = MockLockEntity()
    lock.hass = hass

    assert lock.state is None

    lock._attr_is_locking = True
    assert lock.is_locking
    assert lock.state == STATE_LOCKING

    await lock.async_handle_lock_service()
    assert lock.is_locked
    assert lock.state == STATE_LOCKED

    lock._attr_is_unlocking = True
    assert lock.is_unlocking
    assert lock.state == STATE_UNLOCKING

    await lock.async_handle_unlock_service()
    assert not lock.is_locked
    assert lock.state == STATE_UNLOCKED

    lock._attr_is_jammed = True
    assert lock.is_jammed
    assert lock.state == STATE_JAMMED
    assert not lock.is_locked


async def test_set_default_code_option(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    enable_custom_integrations: None,
) -> None:
    """Test default code stored in the registry."""

    entry = entity_registry.async_get_or_create("lock", "test", "very_unique")
    await hass.async_block_till_done()

    platform = getattr(hass.components, "test.lock")
    platform.init(empty=True)
    platform.ENTITIES["lock1"] = platform.MockLock(
        name="Test",
        code_format=r"^\d{4}$",
        supported_features=LockEntityFeature.OPEN,
        unique_id="very_unique",
    )

    assert await async_setup_component(hass, "lock", {"lock": {"platform": "test"}})
    await hass.async_block_till_done()

    entity0: MockLock = platform.ENTITIES["lock1"]
    entity_registry.async_update_entity_options(
        entry.entity_id, "lock", {CONF_DEFAULT_CODE: "1234"}
    )
    await hass.async_block_till_done()

    assert entity0._lock_option_default_code == "1234"


async def test_default_code_option_update(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    enable_custom_integrations: None,
) -> None:
    """Test default code stored in the registry is updated."""

    entry = entity_registry.async_get_or_create("lock", "test", "very_unique")
    await hass.async_block_till_done()

    platform = getattr(hass.components, "test.lock")
    platform.init(empty=True)

    # Pre-register entities
    entry = entity_registry.async_get_or_create("lock", "test", "very_unique")
    entity_registry.async_update_entity_options(
        entry.entity_id,
        "lock",
        {
            "default_code": "5432",
        },
    )
    platform.ENTITIES["lock1"] = platform.MockLock(
        name="Test",
        code_format=r"^\d{4}$",
        supported_features=LockEntityFeature.OPEN,
        unique_id="very_unique",
    )

    assert await async_setup_component(hass, "lock", {"lock": {"platform": "test"}})
    await hass.async_block_till_done()

    entity0: MockLock = platform.ENTITIES["lock1"]
    assert entity0._lock_option_default_code == "5432"

    entity_registry.async_update_entity_options(
        entry.entity_id, "lock", {CONF_DEFAULT_CODE: "1234"}
    )
    await hass.async_block_till_done()

    assert entity0._lock_option_default_code == "1234"


async def test_lock_open_with_code(hass: HomeAssistant) -> None:
    """Test lock entity with open service."""
    lock = MockLockEntity(
        code_format=r"^\d{4}$", supported_features=LockEntityFeature.OPEN
    )
    lock.hass = hass

    assert lock.state_attributes == {"code_format": r"^\d{4}$"}

    with pytest.raises(ValueError):
        await lock.async_handle_open_service()
    with pytest.raises(ValueError):
        await lock.async_handle_open_service(code="")
    with pytest.raises(ValueError):
        await lock.async_handle_open_service(code="HELLO")
    await lock.async_handle_open_service(code="1234")
    assert lock.calls_open.call_count == 1


async def test_lock_lock_with_code(hass: HomeAssistant) -> None:
    """Test lock entity with open service."""
    lock = MockLockEntity(code_format=r"^\d{4}$")
    lock.hass = hass

    await lock.async_handle_unlock_service(code="1234")
    assert not lock.is_locked

    with pytest.raises(ValueError):
        await lock.async_handle_lock_service()
    with pytest.raises(ValueError):
        await lock.async_handle_lock_service(code="")
    with pytest.raises(ValueError):
        await lock.async_handle_lock_service(code="HELLO")
    await lock.async_handle_lock_service(code="1234")
    assert lock.is_locked


async def test_lock_unlock_with_code(hass: HomeAssistant) -> None:
    """Test unlock entity with open service."""
    lock = MockLockEntity(code_format=r"^\d{4}$")
    lock.hass = hass

    await lock.async_handle_lock_service(code="1234")
    assert lock.is_locked

    with pytest.raises(ValueError):
        await lock.async_handle_unlock_service()
    with pytest.raises(ValueError):
        await lock.async_handle_unlock_service(code="")
    with pytest.raises(ValueError):
        await lock.async_handle_unlock_service(code="HELLO")
    await lock.async_handle_unlock_service(code="1234")
    assert not lock.is_locked


async def test_lock_with_illegal_code(hass: HomeAssistant) -> None:
    """Test lock entity with default code that does not match the code format."""
    lock = MockLockEntity(
        code_format=r"^\d{4}$",
        supported_features=LockEntityFeature.OPEN,
    )
    lock.hass = hass

    with pytest.raises(ValueError):
        await lock.async_handle_open_service(code="123456")
    with pytest.raises(ValueError):
        await lock.async_handle_lock_service(code="123456")
    with pytest.raises(ValueError):
        await lock.async_handle_unlock_service(code="123456")


async def test_lock_with_no_code(hass: HomeAssistant) -> None:
    """Test lock entity with default code that does not match the code format."""
    lock = MockLockEntity(
        supported_features=LockEntityFeature.OPEN,
    )
    lock.hass = hass

    await lock.async_handle_open_service()
    lock.calls_open.assert_called_with({})
    await lock.async_handle_lock_service()
    lock.calls_lock.assert_called_with({})
    await lock.async_handle_unlock_service()
    lock.calls_unlock.assert_called_with({})

    await lock.async_handle_open_service(code="")
    lock.calls_open.assert_called_with({})
    await lock.async_handle_lock_service(code="")
    lock.calls_lock.assert_called_with({})
    await lock.async_handle_unlock_service(code="")
    lock.calls_unlock.assert_called_with({})


async def test_lock_with_default_code(hass: HomeAssistant) -> None:
    """Test lock entity with default code."""
    lock = MockLockEntity(
        code_format=r"^\d{4}$",
        supported_features=LockEntityFeature.OPEN,
        lock_option_default_code="1234",
    )
    lock.hass = hass

    assert lock.state_attributes == {"code_format": r"^\d{4}$"}
    assert lock._lock_option_default_code == "1234"

    await lock.async_handle_open_service()
    lock.calls_open.assert_called_with({ATTR_CODE: "1234"})
    await lock.async_handle_lock_service()
    lock.calls_lock.assert_called_with({ATTR_CODE: "1234"})
    await lock.async_handle_unlock_service()
    lock.calls_unlock.assert_called_with({ATTR_CODE: "1234"})

    await lock.async_handle_open_service(code="")
    lock.calls_open.assert_called_with({ATTR_CODE: "1234"})
    await lock.async_handle_lock_service(code="")
    lock.calls_lock.assert_called_with({ATTR_CODE: "1234"})
    await lock.async_handle_unlock_service(code="")
    lock.calls_unlock.assert_called_with({ATTR_CODE: "1234"})


async def test_lock_with_provided_and_default_code(hass: HomeAssistant) -> None:
    """Test lock entity with provided code when default code is set."""
    lock = MockLockEntity(
        code_format=r"^\d{4}$",
        supported_features=LockEntityFeature.OPEN,
        lock_option_default_code="1234",
    )
    lock.hass = hass

    await lock.async_handle_open_service(code="4321")
    lock.calls_open.assert_called_with({ATTR_CODE: "4321"})
    await lock.async_handle_lock_service(code="4321")
    lock.calls_lock.assert_called_with({ATTR_CODE: "4321"})
    await lock.async_handle_unlock_service(code="4321")
    lock.calls_unlock.assert_called_with({ATTR_CODE: "4321"})


async def test_lock_with_illegal_default_code(hass: HomeAssistant) -> None:
    """Test lock entity with default code that does not match the code format."""
    lock = MockLockEntity(
        code_format=r"^\d{4}$",
        supported_features=LockEntityFeature.OPEN,
        lock_option_default_code="123456",
    )
    lock.hass = hass

    assert lock.state_attributes == {"code_format": r"^\d{4}$"}
    assert lock._lock_option_default_code == "123456"

    with pytest.raises(ValueError):
        await lock.async_handle_open_service()
    with pytest.raises(ValueError):
        await lock.async_handle_lock_service()
    with pytest.raises(ValueError):
        await lock.async_handle_unlock_service()
