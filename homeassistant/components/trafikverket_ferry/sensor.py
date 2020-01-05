"""Ferry information for departures, provided by Trafikverket."""

from datetime import date, datetime, timedelta
import logging

from pytrafikverket import TrafikverketFerry
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    CONF_API_KEY,
    CONF_NAME,
    CONF_WEEKDAY,
    DEVICE_CLASS_TIMESTAMP,
    WEEKDAYS,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)

CONF_FERRIES = "ferries"
CONF_FROM = "from"
CONF_TO = "to"
CONF_TIME = "time"

ATTR_DEPARTURE_STATE = "departure_state"
ATTR_DEPARTURE_TIME = "departure_time"
ATTR_OTHER_INFORMATION = "other_information"
ATTR_DEVIATIONS = "deviations"
ATTR_ROUTE = "route"
# ATTR_ESTIMATED_TIME = "estimated_time"

ICON = "mdi:ferry"
SCAN_INTERVAL = timedelta(minutes=5)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Required(CONF_FERRIES): [
            {
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_FROM): cv.string,
                vol.Optional(CONF_TO, default=""): cv.string,
                vol.Optional(CONF_TIME): cv.time,
                vol.Optional(CONF_WEEKDAY, default=WEEKDAYS): vol.All(
                    cv.ensure_list, [vol.In(WEEKDAYS)]
                ),
            }
        ],
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the departure sensor."""
    httpsession = async_get_clientsession(hass)
    ferry_api = TrafikverketFerry(httpsession, config[CONF_API_KEY])
    sensors = []
    for ferry in config[CONF_FERRIES]:
        sensor = FerrySensor(
            ferry_api,
            ferry[CONF_NAME],
            ferry[CONF_FROM],
            ferry[CONF_TO],
            ferry[CONF_WEEKDAY],
            ferry.get(CONF_TIME),
        )
        sensors.append(sensor)

    async_add_entities(sensors, update_before_add=True)


def next_weekday(fromdate, weekday):
    """Return the date of the next time a specific weekday happen."""
    days_ahead = weekday - fromdate.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return fromdate + timedelta(days_ahead)


def next_departuredate(departure):
    """Calculate the next departuredate from an array input of short days."""
    today_date = date.today()
    today_weekday = date.weekday(today_date)
    if WEEKDAYS[today_weekday] in departure:
        return today_date
    for day in departure:
        next_departure = WEEKDAYS.index(day)
        if next_departure > today_weekday:
            return next_weekday(today_date, next_departure)
    return next_weekday(today_date, WEEKDAYS.index(departure[0]))


class FerrySensor(Entity):
    """Contains data about a ferry depature."""

    def __init__(self, ferry_api, name, from_station, to_station, weekday, time):
        """Initialize the sensor."""
        self._ferry_api = ferry_api
        self._name = name
        self._from_station = from_station
        self._to_station = to_station
        self._weekday = weekday
        self._time = time
        self._state = None
        self._departure_state = None
        self.deviations = ""

    # async def async_update(self):
    #     """Retrieve latest state."""
    #     if self._time is not None:
    #         departure_day = next_departuredate(self._weekday)
    #         when = datetime.combine(departure_day, self._time)
    #         try:
    #             self._state = await self._ferry_api.async_get_ferry_stop(
    #                 self._from_station, self._to_station, when
    #             )
    #         except ValueError as output_error:
    #             _LOGGER.error(
    #                 "Departure %s encountered a problem: %s", when, output_error
    #             )
    #     else:
    #         when = datetime.now()
    #         self._state = await self._ferry_api.async_get_next_ferry_stop(
    #             self._from_station, self._to_station, when
    #         )
    #     self._departure_state = self._state.get_state().name

    async def async_update(self):
        """Retrieve latest state."""
        departure_day = next_departuredate(self._weekday)
        if self._time is not None:
            when = datetime.combine(departure_day, self._time)
        else:
            when = datetime.now()
        try:
            self._state = await self._ferry_api.async_get_next_ferry_stop(
                self._from_station, self._to_station, when
            )
        except ValueError as output_error:
            _LOGGER.error("Departure %s encountered a problem: %s", when, output_error)
        if self._state.deviation_id is not None:
            try:
                deviation = await self._ferry_api.async_get_deviation(
                    self._state.deviation_id
                )
                self.deviations = deviation.message
            except ValueError as output_error:
                _LOGGER.error("Deviation %s cased error: %s", when, output_error)

        self._departure_state = self._state.get_state().name

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        if self._state is None:
            return None
        state = self._state
        other_information = None
        if state.other_information is not None:
            other_information = ", ".join(state.other_information)
        deviations = None
        if self.deviations is not None:
            deviations = ", ".join(state.deviations)
        return {
            ATTR_DEPARTURE_STATE: self._departure_state,
            # ATTR_PLANNED_TIME: state.advertised_time_at_location,
            # ATTR_ESTIMATED_TIME: state.estimated_time_at_location,
            ATTR_DEVIATIONS: deviations,
            ATTR_DEPARTURE_TIME: state.departure_time,
            ATTR_OTHER_INFORMATION: other_information,
        }

    @property
    def device_class(self):
        """Return the device class."""
        return DEVICE_CLASS_TIMESTAMP

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def icon(self):
        """Return the icon for the frontend."""
        return ICON

    @property
    def state(self):
        """Return the departure state."""
        state = self._state
        if state is not None:
            if state.departure_time is not None:
                return state.departure_time
        return None
