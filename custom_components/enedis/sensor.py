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
from .const import CONF_PDL, COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    datas = hass.data[DOMAIN][config_entry.entry_id]
    source = config_entry.options[CONF_SOURCE]
    entities = [PowerSensor(datas[COORDINATOR], datas[CONF_PDL], source, "peak_hours")]
    if config_entry.options.get("detail"):
        entities.append(
            PowerSensor(datas[COORDINATOR], datas[CONF_PDL], source, "offpeak_hours")
        )
    async_add_entities(entities)


class PowerSensor(CoordinatorEntity, SensorEntity):
    """Sensor return power."""

    _attr_device_class = DEVICE_CLASS_ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_state_class = STATE_CLASS_TOTAL_INCREASING

    def __init__(self, coordinator, pdl, source, sensor_type):
        """Initialize the sensor."""
        self.coordinator = coordinator
        self.pdl = pdl
        self.source = source
        self.sensor_type = sensor_type

    @property
    def unique_id(self):
        """Unique_id."""
        return f"{self.pdl}_{self.source}_{self.sensor_type}"

    @property
    def name(self):
        """Name."""
        return f"{self.source} {self.sensor_type}"

    @property
    def native_value(self):
        """Max power."""
        value = int(self.coordinator.data.get("energy", {}).get(self.sensor_type))
        return float(value)

    @property
    def device_info(self):
        """Return the device info."""
        deviceinfo = DeviceInfo(
            identifiers={(DOMAIN, self.pdl)},
            name=f"Linky ({self.pdl})",
            configuration_url=URL,
            manufacturer=MANUFACTURER,
            model=self.coordinator.data.get("contracts", {}).get("subscribed_power"),
            suggested_area="Garage",
        )
        return deviceinfo

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
