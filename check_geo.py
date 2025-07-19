from PIL import Image
from PIL.ExifTags import TAGS
import os

def has_geotag(image_path: str) -> bool:
    """
    Checks if an image file contains GPS geotag data in its EXIF metadata.

    Args:
        image_path: The full path to the image file.

    Returns:
        True if the image has GPS data, False otherwise.
    """
    try:
        image = Image.open(image_path)
    except FileNotFoundError:
        print(f"Error: The file '{image_path}' was not found.")
        return False
    except Exception as e:
        print(f"Error opening or reading image: {e}")
        return False

    # Extract EXIF data from the image
    exif_data = image._getexif()

    # If there's no EXIF data, there's no geotag
    if not exif_data:
        return False

    # The EXIF tag for GPS information is 34853
    # We check if this key exists in the EXIF data
    for tag_id, value in exif_data.items():
        tag_name = TAGS.get(tag_id, tag_id)
        if tag_name == "GPSInfo":
            # The presence of the GPSInfo tag means it's geotagged
            return True

    # If the loop finishes without finding the GPSInfo tag
    return False


if __name__ == "__main__":
    # --- HOW TO USE ---
    # 1. Place your image in the same directory as this script.
    # 2. Change the file name below to match your image file.
    image_filename = "server\datasets\project\images\image_20250719_164911_546069.JPG" # <--- CHANGE THIS

    if not os.path.exists(image_filename):
         print(f"❌ The file '{image_filename}' does not exist in this directory.")
    else:
        if has_geotag(image_filename):
            print(f"📍 The image '{image_filename}' contains geotag data.")
        else:
            print(f"❌ The image '{image_filename}' does not contain any geotag data.")