from django import template
from decimal import Decimal

register = template.Library()


@register.filter(name='czech_int')
def czech_int(value):
    """Format number as integer with space-separated thousands (Czech format)"""
    # Handle None or empty string
    if value is None:
        return '0'
    
    if isinstance(value, str) and value.strip() == '':
        return '0'
    
    try:
        # Handle Decimal objects
        if isinstance(value, Decimal):
            float_value = float(value)
        elif isinstance(value, (int, float)):
            float_value = float(value)
        elif isinstance(value, str):
            # Try to convert string to float
            float_value = float(value)
        else:
            # Try generic conversion
            float_value = float(value)
        
        # Convert to integer (rounds to nearest)
        int_value = int(round(float_value))
        
        # Handle zero case
        if int_value == 0:
            return '0'
        
        # Format with space as thousand separator
        # Reverse the string, add spaces every 3 digits, then reverse back
        str_value = str(abs(int_value))
        reversed_str = str_value[::-1]
        spaced = ' '.join(reversed_str[i:i+3] for i in range(0, len(reversed_str), 3))
        formatted = spaced[::-1]
        
        # Add minus sign if negative
        if int_value < 0:
            formatted = '-' + formatted
        
        return formatted
    except (ValueError, TypeError, AttributeError, OverflowError):
        # If conversion fails, return '0' as safe fallback
        return '0'

