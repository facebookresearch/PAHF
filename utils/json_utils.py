import json
import os


def write_json(data, file_path, indent=4):
    """
    Write data to a JSON file.

    Args:
        data: The Python object (dict, list, etc.) to write as JSON
        file_path: Path to the output JSON file
        indent: Number of spaces for indentation (default: 4, set to None for compact JSON)

    Returns:
        bool: True if successful, False otherwise

    Example:
        >>> data = {"name": "Alex", "preferences": {"favorite_drink": "Sprite"}}
        >>> write_json(data, "persona.json")
    """
    try:
        # Create directory if it doesn't exist
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        # Write the data to the JSON file
        with open(file_path, "w") as f:
            json.dump(data, f, indent=indent)
        return True
    except Exception as e:
        print(f"Error writing JSON to {file_path}: {str(e)}")
        return False


def read_json(file_path):
    """
    Read data from a JSON file.

    Args:
        file_path: Path to the JSON file to read

    Returns:
        The Python object (dict, list, etc.) from the JSON file,
        or None if there was an error

    Example:
        >>> data = read_json("persona.json")
        >>> if data:
        >>>     print(data["name"])
    """
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading JSON from {file_path}: {str(e)}")
        return None


def append_to_json_list(item, file_path, indent=4):
    """
    Append an item to a JSON list file. If the file doesn't exist or isn't a list,
    a new list will be created with the item.

    Args:
        item: The Python object to append to the JSON list
        file_path: Path to the JSON list file
        indent: Number of spaces for indentation (default: 4)

    Returns:
        bool: True if successful, False otherwise

    Example:
        >>> new_response = {"question": "Which drink?", "answer": "Sprite"}
        >>> append_to_json_list(new_response, "conversation_history.json")
    """
    try:
        # Read existing data or create new list
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = [data]  # Convert to list if not already
                except json.JSONDecodeError:
                    data = []  # Start fresh if file is corrupted
        else:
            data = []

        # Append the new item
        data.append(item)

        # Write back to file
        with open(file_path, "w") as f:
            json.dump(data, f, indent=indent)
        return True
    except Exception as e:
        print(f"Error appending to JSON list {file_path}: {str(e)}")
        return False
