from manha.internals.drivers import GPSParser, NeoGPS
from .base import ManhaSensor

class GPS(ManhaSensor):
    
    _DEFAULT_LOCATION_FORMATTING = 'dd'
    
    def __init__(self, location_formatting=_DEFAULT_LOCATION_FORMATTING) -> None:
        """Initialize the GPS sensor with specified location formatting.
        
        Args:
            location_formatting (str): Format for location output. Options are 'dd', 'ddm', 'dms'.
        """
        self._gps = NeoGPS()
        self._gps_parser = GPSParser(location_formatting=location_formatting)
        
    def _update_values(self) -> bool:
        """Update the GPS values by reading from the GPS sensor and parsing the data.
        
        Returns:
            bool: True if data was successfully read and parsed, False otherwise.
        """
        g_d = self._gps.read_gps()
        if g_d is not None:
            for byte in g_d:
                _ = self._gps_parser.update(chr(byte))
                
            return True
        return False

    def read(self) -> dict:
        """Get location values from the GPS

        Returns:
            dict: dict of {lat,lng,alt,satcnt,hdop}
        """
        if not self._update_values():
            return {
                'lat': 0.0,
                'lng': 0.0,
                'alt': -1,
                'satcnt': -1,
                'hdop': -1
            }
        return {
            'lat':    self._gps_parser.latitude[0],
            'lng':    self._gps_parser.longitude[0],
            'alt':    round(self._gps_parser.altitude,2),
            'stct': self._gps_parser.satellites_in_use,
            'hdop':   round(self._gps_parser.hdop,2)
        }
    
    def configure(self, **kwargs):
        """Configure the GPS with provided parameters.

        Args:
            **kwargs: Configuration parameters specific to GPS
        """
        if 'location_formatting' in kwargs:
            self._gps_parser.location_formatting = kwargs['location_formatting']