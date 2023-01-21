"""Sensor for power energy."""
import logging

from homeassistant.components.sensor import (
    STATE_CLASS_TOTAL_INCREASING,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ENERGY_KILO_WATT_HOUR
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ACCESS,
    CONF_CONTRACT,
    CONF_ECOWATT,
    CONF_TEMPO,
    DOMAIN,
    MANUFACTURER,
    URL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = []
    for name in coordinator.data.keys():
        if name not in [ACCESS, CONF_CONTRACT, CONF_ECOWATT, CONF_TEMPO]:
            entities.append(PowerSensor(coordinator, name))
        if name == CONF_TEMPO:
            entities.append(TempoSensor(coordinator))
    async_add_entities(entities)


class PowerSensor(CoordinatorEntity, SensorEntity):
    """Sensor return power."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = ENERGY_KILO_WATT_HOUR
    _attr_state_class = STATE_CLASS_TOTAL_INCREASING
    _attr_has_entity_name = True

    def __init__(self, coordinator, sensor_name):
        """Initialize the sensor."""
        super().__init__(coordinator)
        contracts = coordinator.data.get(CONF_CONTRACT, {})
        self.sensor_mode = sensor_name
        self._attr_unique_id = f"{coordinator.pdl}_{sensor_name}"
        self._attr_name = sensor_name
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
        """Value power."""
        return round(float(self.coordinator.data.get(self.name)), 2)


class TempoSensor(CoordinatorEntity, SensorEntity):
    """Sensor return token expiration date."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_name = "Tempo day"
    _attr_has_entity_name = True

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.pdl}_tempo_day"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.pdl)})

    @property
    def options(self):
        """Return options list."""
        return ["BLUE", "WHITE", "RED"]

    @property
    def native_value(self):
        """Value power."""
        return self.coordinator.data.get(CONF_TEMPO)
