"""
▀▀█▀▀ █▀▄▀█ ▀▀▀▀█ ▄▀▀▀▀ █▀▀▀▄ ▄▀▀▀▄ ▄▀▀▀▀ █▀▀▀▀ 
  █   █   █ █▀▀▀▀  ▀▀▀▄ █▀▀▀  █▀▀▀█ █     █▀▀   
  ▀   ▀   ▀ ▀▀▀▀▀ ▀▀▀▀  ▀     ▀   ▀  ▀▀▀▀ ▀▀▀▀▀ 

Utility functions for the Manha project.
"""


def calculate_checksum(data: bytes) -> int:
    """
    Calculate a simple checksum for the given data.
    
    Args:
        data: The bytes data to calculate checksum for
        
    Returns:
        int: The calculated checksum (0-255)
    """
    # Simple sum of bytes modulo 256
    checksum = 0
    for byte in data:
        checksum = (checksum + byte) % 256
    return checksum


__all__ = [
    "calculate_checksum",
]