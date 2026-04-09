import scrapy

try:
    from itemloaders.processors import MapCompose, TakeFirst
except ImportError:
    # Backward compatibility with older Scrapy versions.
    from scrapy.loader.processors import MapCompose, TakeFirst
import re


def clean_address(value):
    """Remove extra whitespace and newlines from the address."""
    return value.strip() if value else "N/A"


def clean_price(value):
    """Convert price to a numerical format, standardizing currencies."""

    if not isinstance(value, str):
        return "N/A"
    value = value.replace(",", "").strip()
    match = re.search(r"(\d+\.?\d*)", value)  # Extract only numeric values
    if not match:
        return "N/A"  # Return a default value if no valid number is found

    price = float(match.group(1))

    if "£" in value:
        price *= 1.17  # Convert GBP to EUR (example rate)

    return round(price, 2)


def clean_sqft(value):
    """Extract and clean square footage or square meters."""
    if not isinstance(value, str):
        return "N/A"
    match = re.search(r"(\d+\.?\d*)", value.replace(",", ""))
    return float(match.group(1)) if match else "N/A"


class PropertyItem(scrapy.Item):
    price = scrapy.Field(
        input_processor=MapCompose(clean_price), output_processor=TakeFirst()
    )
    city = scrapy.Field(output_processor=TakeFirst())
    address = scrapy.Field(
        input_processor=MapCompose(clean_address), output_processor=TakeFirst()
    )
    property_size = scrapy.Field(
        input_processor=MapCompose(clean_sqft), output_processor=TakeFirst()
    )
    property_type = scrapy.Field(output_processor=TakeFirst())
    amenities = scrapy.Field()
    listing_url = scrapy.Field(output_processor=TakeFirst())
