# apps/profiles/serializers/serializer_utils.py
"""
Utility functions and custom fields for serializers.
"""
from rest_framework import serializers
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
import requests
import os
import hashlib
from urllib.parse import urlparse

from apps.profiles.models import (
    UserProfile, VehicleServiceData, PropertyServiceData,
    SOSServiceData, ServicePortfolioImage, Wallet, WalletTransaction
)
from apps.work_categories.models import (
    WorkCategory, WorkSubCategory, UserWorkSelection,
    UserWorkSubCategory, WorkPortfolioImage
)
from apps.verification.models import AadhaarVerification, LicenseVerification


# Utility functions
def download_image_from_url(url, timeout=10):
    """Download image from URL and return ContentFile"""
    try:
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        if not filename or '.' not in filename:
            content_type = response.headers.get('content-type', '')
            ext = content_type.split('/')[-1] if '/' in content_type else 'jpg'
            filename = f'downloaded_image.{ext}'
        return ContentFile(response.content, name=filename)
    except Exception as e:
        print(f"Error downloading image from {url}: {str(e)}")
        return None


def is_url_string(value):
    """Check if value is a URL string"""
    if isinstance(value, str):
        return value.startswith('http://') or value.startswith('https://')
    return False


def get_existing_image_url(profile, image_field='profile_photo'):
    """Get existing image URL for comparison"""
    if image_field == 'profile_photo':
        if profile and profile.profile_photo:
            return profile.profile_photo.url
    return None


def get_existing_portfolio_urls(profile):
    """Get all existing portfolio image URLs"""
    if not profile:
        return []
    portfolio_images = profile.service_portfolio_images.all().order_by('image_order')
    return [img.image.url for img in portfolio_images]


def calculate_file_hash(file_obj, chunk_size=8192):
    """Calculate MD5 hash of a file object"""
    try:
        current_position = file_obj.tell() if hasattr(file_obj, 'tell') else 0
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        md5_hash = hashlib.md5()
        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            md5_hash.update(chunk)
        if hasattr(file_obj, 'seek'):
            file_obj.seek(current_position)
        return md5_hash.hexdigest()
    except Exception as e:
        print(f"Error calculating file hash: {str(e)}")
        return None


def files_are_same(file1, file2):
    """Compare two file objects by their MD5 hash"""
    if not file1 or not file2:
        return False
    hash1 = calculate_file_hash(file1)
    hash2 = calculate_file_hash(file2)
    return hash1 == hash2 if hash1 and hash2 else False


def parse_multipart_array_fields(data):
    """Convert Flutter's multipart form data format to nested structures"""
    result = {}
    array_fields = {}
    all_keys = list(data.keys())

    for key in all_keys:
        if '[' in key and ']' in key:
            parts = key.replace('[', '|').replace(']', '').split('|')

            if len(parts) == 2:
                field_name, index_str = parts
                try:
                    index = int(index_str)
                    if field_name not in array_fields:
                        array_fields[field_name] = {}
                    value = data.get(key)
                    if index in array_fields[field_name] and isinstance(array_fields[field_name][index], dict):
                        continue
                    array_fields[field_name][index] = value
                except ValueError:
                    continue

            elif len(parts) == 3:
                field_name, index_str, dict_key = parts
                try:
                    index = int(index_str)
                    if field_name not in array_fields:
                        array_fields[field_name] = {}
                    if index not in array_fields[field_name] or not isinstance(array_fields[field_name][index], dict):
                        array_fields[field_name][index] = {}
                    value = data.get(key)
                    if value == '' or value == 'null':
                        value = None
                    array_fields[field_name][index][dict_key] = value
                except ValueError:
                    continue

    for field_name, indexed_values in array_fields.items():
        sorted_indices = sorted(indexed_values.keys())
        result[field_name] = [indexed_values[i] for i in sorted_indices]

    return result


class FlexibleImageField(serializers.Field):
    """
    Custom field that accepts:
    - File uploads (ImageField behavior)
    - None/null values
    - Dict objects with 'index' and 'image' keys
    - URL strings
    """
    def to_internal_value(self, data):
        # Allow None
        if data is None or data == '':
            return None

        # Allow dict objects (for indexed operations)
        if isinstance(data, dict):
            return data

        # Allow file uploads
        if hasattr(data, 'read'):
            return data

        # Allow URL strings
        if isinstance(data, str):
            return data

        # Unknown type - return as is and let parent serializer handle
        return data

    def to_representation(self, value):
        # Not used for input, but required
        return value


class FlexibleStringField(serializers.Field):
    """
    Custom field that accepts:
    - String values
    - None/null values
    - Dict objects with 'index' and value keys (for indexed operations)

    Used for languages and sub_category_ids to support add/replace/delete operations
    """
    def to_internal_value(self, data):
        # Allow None
        if data is None or data == '':
            return None

        # Allow dict objects (for indexed operations like {"index": 0, "language": "English"})
        if isinstance(data, dict):
            return data

        # Allow string values
        if isinstance(data, str):
            return data

        # Unknown type - return as is and let parent serializer handle
        return data

    def to_representation(self, value):
        # Not used for input, but required
        return value


def download_image_from_url(url, timeout=10):
    """
    Download image from URL and return ContentFile

    Args:
        url: Image URL to download
        timeout: Request timeout in seconds

    Returns:
        ContentFile object or None if download fails
    """
    try:
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        # Get filename from URL
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)

        # If no filename, generate one
        if not filename or '.' not in filename:
            content_type = response.headers.get('content-type', '')
            ext = content_type.split('/')[-1] if '/' in content_type else 'jpg'
            filename = f'downloaded_image.{ext}'

        # Create ContentFile from response content
        return ContentFile(response.content, name=filename)
    except Exception as e:
        print(f"Error downloading image from {url}: {str(e)}")
        return None


def is_url_string(value):
    """Check if value is a URL string"""
    if isinstance(value, str):
        return value.startswith('http://') or value.startswith('https://')
    return False


def get_existing_image_url(profile, image_field='profile_photo'):
    """Get existing image URL for comparison"""
    if image_field == 'profile_photo':
        if profile and profile.profile_photo:
            return profile.profile_photo.url
    return None


def get_existing_portfolio_urls(profile):
    """Get all existing portfolio image URLs"""
    if not profile:
        return []

    portfolio_images = profile.service_portfolio_images.all().order_by('image_order')
    return [img.image.url for img in portfolio_images]


def calculate_file_hash(file_obj, chunk_size=8192):
    """
    Calculate MD5 hash of a file object

    Args:
        file_obj: File object to hash
        chunk_size: Size of chunks to read

    Returns:
        MD5 hash string or None if error
    """
    try:
        # Save current position
        current_position = file_obj.tell() if hasattr(file_obj, 'tell') else 0

        # Reset to beginning
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)

        # Calculate hash
        md5_hash = hashlib.md5()
        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            md5_hash.update(chunk)

        # Restore position
        if hasattr(file_obj, 'seek'):
            file_obj.seek(current_position)

        return md5_hash.hexdigest()
    except Exception as e:
        print(f"Error calculating file hash: {str(e)}")
        return None


def files_are_same(file1, file2):
    """
    Compare two file objects by their MD5 hash

    Args:
        file1: First file object
        file2: Second file object

    Returns:
        True if files have same content, False otherwise
    """
    if not file1 or not file2:
        return False

    hash1 = calculate_file_hash(file1)
    hash2 = calculate_file_hash(file2)

    return hash1 == hash2 if hash1 and hash2 else False


def parse_multipart_array_fields(data):
    """
    Convert Flutter's multipart form data format to nested structures.

    Flutter sends:
        portfolio_images[0][index] = 1
        portfolio_images[0][image] = null
        portfolio_images[1] = file
        languages[0] = "English"
        sub_category_ids[0][index] = 1
        sub_category_ids[0][sub_category_id] = "SS0001"

    Converts to:
        portfolio_images = [{"index": 1, "image": null}, file]
        languages = ["English"]
        sub_category_ids = [{"index": 1, "sub_category_id": "SS0001"}]
    """
    result = {}

    # Track which fields need processing
    array_fields = {}  # {field_name: {index: value or {key: value}}}

    # Iterate through all keys in the data
    all_keys = list(data.keys())

    for key in all_keys:
        # Check if it matches array pattern: field[index] or field[index][key]
        if '[' in key and ']' in key:
            # Parse the key structure
            parts = key.replace('[', '|').replace(']', '').split('|')

            if len(parts) == 2:
                # Simple array: field[0] = value
                field_name, index_str = parts
                try:
                    index = int(index_str)
                    if field_name not in array_fields:
                        array_fields[field_name] = {}

                    # Get the value (could be file, string, etc.)
                    value = data.get(key)

                    # Check if this index already has a dict (from nested keys)
                    if index in array_fields[field_name] and isinstance(array_fields[field_name][index], dict):
                        # Already has dict structure from nested keys, skip simple value
                        continue

                    array_fields[field_name][index] = value
                except ValueError:
                    continue

            elif len(parts) == 3:
                # Nested dict: field[0][key] = value
                field_name, index_str, dict_key = parts
                try:
                    index = int(index_str)
                    if field_name not in array_fields:
                        array_fields[field_name] = {}

                    # Initialize as dict if not present or if it was a simple value
                    if index not in array_fields[field_name] or not isinstance(array_fields[field_name][index], dict):
                        array_fields[field_name][index] = {}

                    # Handle special cases for image/file fields
                    value = data.get(key)
                    if value == '' or value == 'null':
                        value = None

                    array_fields[field_name][index][dict_key] = value
                except ValueError:
                    continue

    # Convert indexed dicts to sorted lists
    for field_name, indexed_values in array_fields.items():
        sorted_indices = sorted(indexed_values.keys())
        result[field_name] = [indexed_values[i] for i in sorted_indices]

    return result


