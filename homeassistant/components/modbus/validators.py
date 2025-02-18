"""Validate Modbus configuration."""
from __future__ import annotations

from collections import namedtuple
import logging
import struct
from typing import Any

import voluptuous as vol

from homeassistant.const import (
    CONF_ADDRESS,
    CONF_COMMAND_OFF,
    CONF_COMMAND_ON,
    CONF_COUNT,
    CONF_HOST,
    CONF_NAME,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    CONF_STRUCTURE,
    CONF_TIMEOUT,
    CONF_TYPE,
)

from .const import (
    CONF_DATA_TYPE,
    CONF_DEVICE_ADDRESS,
    CONF_FAN_MODE_REGISTER,
    CONF_FAN_MODE_VALUES,
    CONF_HVAC_MODE_REGISTER,
    CONF_INPUT_TYPE,
    CONF_SLAVE_COUNT,
    CONF_SWAP,
    CONF_SWAP_BYTE,
    CONF_SWAP_WORD,
    CONF_SWAP_WORD_BYTE,
    CONF_TARGET_TEMP,
    CONF_VIRTUAL_COUNT,
    CONF_WRITE_TYPE,
    DEFAULT_HUB,
    DEFAULT_SCAN_INTERVAL,
    PLATFORMS,
    SERIAL,
    DataType,
)

_LOGGER = logging.getLogger(__name__)

ENTRY = namedtuple(
    "ENTRY",
    [
        "struct_id",
        "register_count",
        "validate_parm",
    ],
)


ILLEGAL = "I"
OPTIONAL = "O"
DEMANDED = "D"

PARM_IS_LEGAL = namedtuple(
    "PARM_IS_LEGAL",
    [
        "count",
        "structure",
        "slave_count",
        "swap_byte",
        "swap_word",
    ],
)
DEFAULT_STRUCT_FORMAT = {
    DataType.INT16: ENTRY(
        "h", 1, PARM_IS_LEGAL(ILLEGAL, ILLEGAL, OPTIONAL, OPTIONAL, ILLEGAL)
    ),
    DataType.UINT16: ENTRY(
        "H", 1, PARM_IS_LEGAL(ILLEGAL, ILLEGAL, OPTIONAL, OPTIONAL, ILLEGAL)
    ),
    DataType.FLOAT16: ENTRY(
        "e", 1, PARM_IS_LEGAL(ILLEGAL, ILLEGAL, OPTIONAL, OPTIONAL, ILLEGAL)
    ),
    DataType.INT32: ENTRY(
        "i", 2, PARM_IS_LEGAL(ILLEGAL, ILLEGAL, OPTIONAL, OPTIONAL, OPTIONAL)
    ),
    DataType.UINT32: ENTRY(
        "I", 2, PARM_IS_LEGAL(ILLEGAL, ILLEGAL, OPTIONAL, OPTIONAL, OPTIONAL)
    ),
    DataType.FLOAT32: ENTRY(
        "f", 2, PARM_IS_LEGAL(ILLEGAL, ILLEGAL, OPTIONAL, OPTIONAL, OPTIONAL)
    ),
    DataType.INT64: ENTRY(
        "q", 4, PARM_IS_LEGAL(ILLEGAL, ILLEGAL, OPTIONAL, OPTIONAL, OPTIONAL)
    ),
    DataType.UINT64: ENTRY(
        "Q", 4, PARM_IS_LEGAL(ILLEGAL, ILLEGAL, OPTIONAL, OPTIONAL, OPTIONAL)
    ),
    DataType.FLOAT64: ENTRY(
        "d", 4, PARM_IS_LEGAL(ILLEGAL, ILLEGAL, OPTIONAL, OPTIONAL, OPTIONAL)
    ),
    DataType.STRING: ENTRY(
        "s", 0, PARM_IS_LEGAL(DEMANDED, ILLEGAL, ILLEGAL, OPTIONAL, ILLEGAL)
    ),
    DataType.CUSTOM: ENTRY(
        "?", 0, PARM_IS_LEGAL(DEMANDED, DEMANDED, ILLEGAL, ILLEGAL, ILLEGAL)
    ),
}


def struct_validator(config: dict[str, Any]) -> dict[str, Any]:
    """Sensor schema validator."""

    name = config[CONF_NAME]
    data_type = config[CONF_DATA_TYPE]
    if data_type == "int":
        data_type = config[CONF_DATA_TYPE] = DataType.INT16
    count = config.get(CONF_COUNT, None)
    structure = config.get(CONF_STRUCTURE, None)
    slave_count = config.get(CONF_SLAVE_COUNT, config.get(CONF_VIRTUAL_COUNT))
    validator = DEFAULT_STRUCT_FORMAT[data_type].validate_parm
    swap_type = config.get(CONF_SWAP)
    for entry in (
        (count, validator.count, CONF_COUNT),
        (structure, validator.structure, CONF_STRUCTURE),
        (
            slave_count,
            validator.slave_count,
            f"{CONF_VIRTUAL_COUNT} / {CONF_SLAVE_COUNT}",
        ),
    ):
        if entry[0] is None:
            if entry[1] == DEMANDED:
                error = f"{name}: `{entry[2]}:` missing, demanded with `{CONF_DATA_TYPE}: {data_type}`"
                raise vol.Invalid(error)
        elif entry[1] == ILLEGAL:
            error = (
                f"{name}: `{entry[2]}:` illegal with `{CONF_DATA_TYPE}: {data_type}`"
            )
            raise vol.Invalid(error)

    if swap_type:
        swap_type_validator = {
            CONF_SWAP_BYTE: validator.swap_byte,
            CONF_SWAP_WORD: validator.swap_word,
            CONF_SWAP_WORD_BYTE: validator.swap_word,
        }[swap_type]
        if swap_type_validator == ILLEGAL:
            error = f"{name}: `{CONF_SWAP}:{swap_type}` illegal with `{CONF_DATA_TYPE}: {data_type}`"
            raise vol.Invalid(error)
    if config[CONF_DATA_TYPE] == DataType.CUSTOM:
        try:
            size = struct.calcsize(structure)
        except struct.error as err:
            raise vol.Invalid(
                f"{name}: error in structure format --> {str(err)}"
            ) from err
        bytecount = count * 2
        if bytecount != size:
            raise vol.Invalid(
                f"{name}: Size of structure is {size} bytes but `{CONF_COUNT}: {count}` is {bytecount} bytes"
            )
    else:
        if data_type != DataType.STRING:
            config[CONF_COUNT] = DEFAULT_STRUCT_FORMAT[data_type].register_count
        if slave_count:
            structure = (
                f">{slave_count + 1}{DEFAULT_STRUCT_FORMAT[data_type].struct_id}"
            )
        else:
            structure = f">{DEFAULT_STRUCT_FORMAT[data_type].struct_id}"
    return {
        **config,
        CONF_STRUCTURE: structure,
        CONF_SWAP: swap_type,
    }


def number_validator(value: Any) -> int | float:
    """Coerce a value to number without losing precision."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value

    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError) as err:
        raise vol.Invalid(f"invalid number {value}") from err


def nan_validator(value: Any) -> int:
    """Convert nan string to number (can be hex string or int)."""
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        return int(value, 16)
    except (TypeError, ValueError) as err:
        raise vol.Invalid(f"invalid number {value}") from err


def scan_interval_validator(config: dict) -> dict:
    """Control scan_interval."""
    for hub in config:
        minimum_scan_interval = DEFAULT_SCAN_INTERVAL
        for component, conf_key in PLATFORMS:
            if conf_key not in hub:
                continue

            for entry in hub[conf_key]:
                scan_interval = entry.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                if scan_interval == 0:
                    continue
                if scan_interval < 5:
                    _LOGGER.warning(
                        (
                            "%s %s scan_interval(%d) is lower than 5 seconds, "
                            "which may cause Home Assistant stability issues"
                        ),
                        component,
                        entry.get(CONF_NAME),
                        scan_interval,
                    )
                entry[CONF_SCAN_INTERVAL] = scan_interval
                minimum_scan_interval = min(scan_interval, minimum_scan_interval)
        if (
            CONF_TIMEOUT in hub
            and hub[CONF_TIMEOUT] > minimum_scan_interval - 1
            and minimum_scan_interval > 1
        ):
            _LOGGER.warning(
                "Modbus %s timeout(%d) is adjusted(%d) due to scan_interval",
                hub.get(CONF_NAME, ""),
                hub[CONF_TIMEOUT],
                minimum_scan_interval - 1,
            )
            hub[CONF_TIMEOUT] = minimum_scan_interval - 1
    return config


def duplicate_entity_validator(config: dict) -> dict:
    """Control scan_interval."""
    for hub_index, hub in enumerate(config):
        for component, conf_key in PLATFORMS:
            if conf_key not in hub:
                continue
            names: set[str] = set()
            errors: list[int] = []
            addresses: set[str] = set()
            for index, entry in enumerate(hub[conf_key]):
                name = entry[CONF_NAME]
                addr = str(entry[CONF_ADDRESS])
                if CONF_INPUT_TYPE in entry:
                    addr += "_" + str(entry[CONF_INPUT_TYPE])
                elif CONF_WRITE_TYPE in entry:
                    addr += "_" + str(entry[CONF_WRITE_TYPE])
                if CONF_COMMAND_ON in entry:
                    addr += "_" + str(entry[CONF_COMMAND_ON])
                if CONF_COMMAND_OFF in entry:
                    addr += "_" + str(entry[CONF_COMMAND_OFF])
                inx = entry.get(CONF_SLAVE, None) or entry.get(CONF_DEVICE_ADDRESS, 0)
                addr += "_" + str(inx)
                entry_addrs: set[str] = set()
                entry_addrs.add(addr)

                if CONF_TARGET_TEMP in entry:
                    a = str(entry[CONF_TARGET_TEMP])
                    a += "_" + str(inx)
                    entry_addrs.add(a)
                if CONF_HVAC_MODE_REGISTER in entry:
                    a = str(entry[CONF_HVAC_MODE_REGISTER][CONF_ADDRESS])
                    a += "_" + str(inx)
                    entry_addrs.add(a)
                if CONF_FAN_MODE_REGISTER in entry:
                    a = str(entry[CONF_FAN_MODE_REGISTER][CONF_ADDRESS])
                    a += "_" + str(inx)
                    entry_addrs.add(a)

                dup_addrs = entry_addrs.intersection(addresses)

                if len(dup_addrs) > 0:
                    for addr in dup_addrs:
                        err = (
                            f"Modbus {component}/{name} address {addr} is duplicate, second"
                            " entry not loaded!"
                        )
                        _LOGGER.warning(err)
                    errors.append(index)
                elif name in names:
                    err = (
                        f"Modbus {component}/{name}  is duplicate, second entry not"
                        " loaded!"
                    )
                    _LOGGER.warning(err)
                    errors.append(index)
                else:
                    names.add(name)
                    addresses.update(entry_addrs)

            for i in reversed(errors):
                del config[hub_index][conf_key][i]
    return config


def duplicate_modbus_validator(config: list) -> list:
    """Control modbus connection for duplicates."""
    hosts: set[str] = set()
    names: set[str] = set()
    errors = []
    for index, hub in enumerate(config):
        name = hub.get(CONF_NAME, DEFAULT_HUB)
        if hub[CONF_TYPE] == SERIAL:
            host = hub[CONF_PORT]
        else:
            host = f"{hub[CONF_HOST]}_{hub[CONF_PORT]}"
        if host in hosts:
            err = f"Modbus {name} contains duplicate host/port {host}, not loaded!"
            _LOGGER.warning(err)
            errors.append(index)
        elif name in names:
            err = f"Modbus {name} is duplicate, second entry not loaded!"
            _LOGGER.warning(err)
            errors.append(index)
        else:
            hosts.add(host)
            names.add(name)

    for i in reversed(errors):
        del config[i]
    return config


def duplicate_fan_mode_validator(config: dict[str, Any]) -> dict:
    """Control modbus climate fan mode values for duplicates."""
    fan_modes: set[int] = set()
    errors = []
    for key, value in config[CONF_FAN_MODE_VALUES].items():
        if value in fan_modes:
            wrn = f"Modbus fan mode {key} has a duplicate value {value}, not loaded, values must be unique!"
            _LOGGER.warning(wrn)
            errors.append(key)
        else:
            fan_modes.add(value)

    for key in reversed(errors):
        del config[CONF_FAN_MODE_VALUES][key]
    return config
