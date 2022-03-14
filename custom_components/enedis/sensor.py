"""Sensor for power energy."""
import logging

from homeassistant.components.sensor import (
    DEVICE_CLASS_ENERGY,
    STATE_CLASS_TOTAL_INCREASING,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import ENERGY_KILO_WATT_HOUR
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CONSUMPTION, CONF_PDL, COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensors."""
    datas = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = datas[COORDINATOR]
    pdl = datas[CONF_PDL]
    entities = []
    if config_entry.options.get(CONF_CONSUMPTION) is True:
        entities.append(PowerSensor(coordinator, pdl))
    async_add_entities(entities)


class PowerSensor(CoordinatorEntity, SensorEntity):
    """Sensor return power."""

    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_state_class = STATE_CLASS_TOTAL_INCREASING

    def __init__(self, coordinator, pdl):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self.pdl = pdl

    @property
    def unique_id(self):
        """Unique_id."""
        return f"{self.pdl}_consumption_summary"

    @property
    def name(self):
        """Unique_id."""
        return f"Consumption summary ({self.pdl})"

    @property
    def native_value(self):
        """Max power."""
        value = int(self.coordinator.data.get("consumption"))
        return float(value)

    @property
    def device_info(self):
        """Return the device info."""
        return {"identifiers": {(DOMAIN, self.pdl)}}

    @property
    def extra_state_attributes(self):
        """Extra attributes."""
        attributes = {
            "offpeak hours": self.coordinator.data["contracts"].get("offpeak_hours"),
            "last activation date": self.coordinator.data["contracts"].get(
                "last_activation_date"
            ),
            "last tariff changedate": self.coordinator.data["contracts"].get(
                "last_distribution_tariff_change_date"
            ),
        }
        return attributes
