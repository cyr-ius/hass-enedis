"""Sensor for power energy."""
import logging

from homeassistant.components.sensor import (
    DEVICE_CLASS_ENERGY,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ENERGY_KILO_WATT_HOUR, CONF_SOURCE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .enedisgateway import MANUFACTURER, URL
from .const import DOMAIN, CONF_DETAIL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    source = config_entry.options[CONF_SOURCE]
    entities = [PowerSensor(coordinator, source, "peak_hours")]
    if config_entry.options.get(CONF_DETAIL):
        entities.append(PowerSensor(coordinator, source, "offpeak_hours"))
    async_add_entities(entities)


class PowerSensor(CoordinatorEntity, SensorEntity):
    """Sensor return power."""

    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_state_class = STATE_CLASS_TOTAL_INCREASING

    def __init__(self, coordinator, source, sensor_type):
        """Initialize the sensor."""
        super().__init__(coordinator)
        contracts = coordinator.data.get("contracts", {})
        self.sensor_type = sensor_type
        self._attr_unique_id = f"{coordinator.pdl}_{source}_{sensor_type}"
        self._attr_name = f"{source} {sensor_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.pdl)},
            name=f"Linky ({coordinator.pdl})",
            configuration_url=URL,
            manufacturer=MANUFACTURER,
            model=contracts.get("subscribed_power"),
            suggested_area="Garage",
        )

        self._attr_extra_state_attributes = {
            "offpeak hours": contracts.get("offpeak_hours"),
            "last activation date": contracts.get("last_activation_date"),
            "last tariff changedate": contracts.get(
                "last_distribution_tariff_change_date"
            ),
        }

    @property
    def native_value(self):
        """Max power."""
        value = int(self.coordinator.data.get("energy", {}).get(self.sensor_type))
        return float(value)
