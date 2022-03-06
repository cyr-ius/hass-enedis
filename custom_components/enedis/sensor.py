"""Sensor for power energy."""
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    DEVICE_CLASS_ENERGY,
    STATE_CLASS_TOTAL_INCREASING,
)
from homeassistant.const import ENERGY_KILO_WATT_HOUR
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensors."""
    datas = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = datas[COORDINATOR]
    entity = PowerSensor(coordinator)
    async_add_entities([entity], True)


class PowerSensor(CoordinatorEntity, SensorEntity):
    """Get Max power."""

    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_state_class = STATE_CLASS_TOTAL_INCREASING

    def __init__(self, coordinator):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self.pdl = self.coordinator.data["pdl"]

    @property
    def unique_id(self):
        """Unique_id."""
        return f"{self.pdl}_max_power"

    @property
    def name(self):
        """Unique_id."""
        return f"Total consumption power ({self.pdl})"

    @property
    def native_value(self):
        """Max power."""
        return float(self.coordinator.data.get("total_power"))

    @property
    def device_info(self):
        """Return the device info."""
        return {"identifiers": {(DOMAIN, self.pdl)}}
