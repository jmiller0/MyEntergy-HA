import logging
from datetime import datetime, timedelta
from typing import Optional
from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import Sensor, SensorInfo


class MQTTPublisher:
    """Publishes MyEntergy meter readings to Home Assistant via MQTT Discovery."""

    def __init__(self, host: str, port: int = 1883, username: Optional[str] = None,
                 password: Optional[str] = None, meter_id: Optional[str] = None):
        """Initialize MQTT publisher with broker settings.

        Args:
            host: MQTT broker hostname
            port: MQTT broker port (default: 1883)
            username: MQTT username for authentication
            password: MQTT password for authentication
            meter_id: Entergy meter ID for unique device identification (required)
        """
        self.logger = logging.getLogger(__name__)
        if not meter_id:
            raise ValueError("meter_id is required for MQTT publisher")
        self.meter_id = meter_id

        # Create short meter ID for unique IDs (last 8 chars)
        self.meter_id_short = self.meter_id[-8:]

        try:
            # Configure MQTT settings
            mqtt_settings = Settings.MQTT(
                host=host,
                port=port,
                username=username,
                password=password
            )

            # Create device info
            device_info = DeviceInfo(
                name="MyEntergy",
                identifiers=[f"myentergy_{self.meter_id_short}"],
                manufacturer="Entergy",
                model="Smart Meter",
                sw_version="1.0"
            )

            # Create meter sensor (energy reading)
            meter_sensor_info = SensorInfo(
                name="Entergy API Meter",
                device_class="energy",
                state_class="total_increasing",
                unit_of_measurement="kWh",
                unique_id=f"entergy_meter_{self.meter_id_short}",
                device=device_info
            )
            meter_settings = Settings(mqtt=mqtt_settings, entity=meter_sensor_info)
            self.meter_sensor = Sensor(meter_settings)

            # Create last seen sensor (timestamp)
            last_seen_sensor_info = SensorInfo(
                name="Entergy API Meter Last Seen",
                device_class="timestamp",
                unique_id=f"entergy_meter_last_seen_{self.meter_id_short}",
                device=device_info
            )
            last_seen_settings = Settings(mqtt=mqtt_settings, entity=last_seen_sensor_info)
            self.last_seen_sensor = Sensor(last_seen_settings)

            self.logger.info(f"✓ MQTT Publisher initialized (broker: {host}:{port})")

        except Exception as e:
            self.logger.error(f"✗ Failed to initialize MQTT Publisher: {e}")
            raise

    def publish_meter_reading(self, odr_amt: float, timestamp: datetime) -> bool:
        """Publish meter reading to MQTT.

        Args:
            odr_amt: Meter reading in kWh
            timestamp: Timestamp of the reading

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Publish meter reading
            self.meter_sensor.set_state(odr_amt)

            # Publish last seen timestamp (ISO 8601 format with timezone)
            # If timestamp is naive (no timezone), assume local timezone
            if timestamp.tzinfo is None:
                from datetime import timezone
                import time
                # Get local timezone offset
                local_offset = -time.timezone if not time.daylight else -time.altzone
                local_tz = timezone(timedelta(seconds=local_offset))
                timestamp = timestamp.replace(tzinfo=local_tz)

            iso_timestamp = timestamp.isoformat()
            self.last_seen_sensor.set_state(iso_timestamp)

            self.logger.info(f"✓ Published MQTT: {odr_amt} kWh at {iso_timestamp}")
            return True

        except Exception as e:
            self.logger.error(f"✗ Failed to publish MQTT data: {e}")
            return False

    def close(self):
        """Close MQTT connections gracefully."""
        try:
            # ha-mqtt-discoverable handles cleanup internally
            self.logger.info("MQTT Publisher closed")
        except Exception as e:
            self.logger.warning(f"Error closing MQTT Publisher: {e}")
