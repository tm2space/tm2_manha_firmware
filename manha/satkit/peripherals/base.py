class ManhaSensor:
    """Base interface class for all MANHA peripheral devices.
    
    All peripheral devices should inherit from this class 
    and implement the required methods.
    """

    def read(self) -> dict:
        """Read data from the peripheral device.
        
        Returns:
            dict: Data read from the peripheral device
        """
        raise NotImplementedError("Subclasses must implement read()")

    def configure(self, **kwargs):
        """Configure the peripheral device with provided parameters.
        
        Args:
            **kwargs: Configuration parameters specific to each peripheral
        """
        raise NotImplementedError("Subclasses must implement configure()")